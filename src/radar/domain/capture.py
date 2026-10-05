"""Manual capture intake, provenance and price history (RDR-011..RDR-015, RDR-013).

The manual capture path receives a versioned payload from the public boundary,
sanitizes and validates it, and materializes the distinct domain entities of the
pipeline: :class:`Product`, :class:`MarketplaceProduct`, :class:`Offer`,
:class:`PriceObservation`, :class:`RawCapture`, :class:`Evidence`,
:class:`DiscoveryEvent` and :class:`Candidate`. :class:`PriceObservation` is
append-only and reused by identity so repeated captures never overwrite history
or invent a price (AUT-028). The module is framework-free (no FastAPI, SQLAlchemy
or Chrome) so the domain stays independent from infrastructure.

Marketplace content is untrusted data, never an instruction (AUT-275, AUT-276):
free-text fields are sanitized here, HTML is never stored (AUT-203) and money is
represented with :class:`~decimal.Decimal`, never binary floating point
(AUT-232).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any
from urllib.parse import parse_qsl, urlparse

from radar.domain.audit import AuditEvent
from radar.domain.errors import RadarError, RadarException

#: Version of the public manual-capture contract (``docs/04_DATA_CONTRACTS.md``).
CAPTURE_SCHEMA_VERSION = "1.0"

#: Version of the public price-history contract (``docs/04_DATA_CONTRACTS.md``).
PRICE_HISTORY_SCHEMA_VERSION = "1.0"

#: Capture error codes (see ``docs/ERROR_CATALOG.md``).
CAPTURE_PAYLOAD_INVALID = "RAD-CAP-001"
CAPTURE_SENSITIVE_FIELD = "RAD-CAP-002"
CAPTURE_IDENTITY_CONFLICT = "RAD-CAP-003"
CANDIDATE_NOT_FOUND = "RAD-CAP-004"
MARKETPLACE_PRODUCT_NOT_FOUND = "RAD-CAP-005"

#: Entity types used by provenance (Evidence) records.
ENTITY_PRODUCT = "product"
ENTITY_MARKETPLACE_PRODUCT = "marketplace_product"
ENTITY_OFFER = "offer"
ENTITY_CANDIDATE = "candidate"

MAX_EXTERNAL_ID_LENGTH = 128
MAX_TEXT_LENGTH = 512

#: Field names that must never be accepted in a capture payload (AUT-299).
SENSITIVE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "cookies",
        "credential",
        "credentials",
        "id_token",
        "oauth_token",
        "pairing_secret",
        "password",
        "refresh_token",
        "secret",
        "token",
    }
)

_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})
#: Query parameter names that indicate a session/token captured by accident.
_URL_SENSITIVE_PARAMS = SENSITIVE_FIELD_NAMES | frozenset({"session", "sessionid"})
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


class Marketplace(StrEnum):
    """Marketplaces supported by the V1 pipeline."""

    MERCADO_LIVRE = "MERCADO_LIVRE"
    SHOPEE = "SHOPEE"


class CaptureSource(StrEnum):
    """Origin of a discovery/capture (``docs/03_DOMAIN_MODEL.md``)."""

    ML_TRENDS = "ML_TRENDS"
    ML_SEARCH = "ML_SEARCH"
    ML_AFFILIATE_PORTAL = "ML_AFFILIATE_PORTAL"
    SHOPEE_AFFILIATE_PRODUCT = "SHOPEE_AFFILIATE_PRODUCT"
    SHOPEE_CAMPAIGN = "SHOPEE_CAMPAIGN"
    BROWSER_EXTENSION = "BROWSER_EXTENSION"
    MANUAL_URL = "MANUAL_URL"


class CandidateState(StrEnum):
    """Conceptual states of a Candidate entering the pipeline."""

    NEW = "NEW"
    NORMALIZED = "NORMALIZED"
    FILTERED = "FILTERED"
    SCORING = "SCORING"
    AI_REVIEW = "AI_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    ERROR = "ERROR"


class CaptureValidationError(RadarException):
    """Raised when a capture payload is structurally or semantically invalid."""

    def __init__(
        self,
        message: str,
        *,
        code: str = CAPTURE_PAYLOAD_INVALID,
        context: Mapping[str, Any] | None = None,
        action: str | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(
            RadarError(
                code=code,
                message=message,
                retryable=retryable,
                action=action or "Corrigir o payload da captura e enviar novamente",
                context=dict(context or {}),
            )
        )


def identity_conflict_error(marketplace: Marketplace, external_id: str) -> CaptureValidationError:
    """Build the structured error for a concurrent identity race."""

    return CaptureValidationError(
        "Captura concorrente para o mesmo marketplace + external_id",
        code=CAPTURE_IDENTITY_CONFLICT,
        retryable=True,
        action="Reenviar a captura; a identidade já existe e será reutilizada",
        context={"marketplace": marketplace.value, "external_id": external_id},
    )


def candidate_not_found_error(candidate_id: str) -> CaptureValidationError:
    """Build the structured not-found error for a Candidate query."""

    return CaptureValidationError(
        "Candidate não encontrado",
        code=CANDIDATE_NOT_FOUND,
        action="Verificar o candidate_id informado",
        context={"candidate_id": candidate_id},
    )


def marketplace_product_not_found_error(marketplace_product_id: str) -> CaptureValidationError:
    """Build the structured not-found error for a price-history query."""

    return CaptureValidationError(
        "MarketplaceProduct não encontrado",
        code=MARKETPLACE_PRODUCT_NOT_FOUND,
        action="Verificar o marketplace_product_id informado",
        context={"marketplace_product_id": marketplace_product_id},
    )


def sanitize_single_line(value: str) -> str:
    """Remove control characters and collapse whitespace for single-line text.

    This keeps marketplace content as inert data and prevents newline/control
    injection from reaching persisted provenance fields (AUT-276, AUT-299).
    """

    without_controls = _CONTROL_CHARS.sub("", value)
    return _WHITESPACE.sub(" ", without_controls).strip()


def find_sensitive_fields(payload: Any, *, _prefix: str = "") -> tuple[str, ...]:
    """Recursively list object keys that match known sensitive field names.

    The result contains dotted paths (for lists, an indexed suffix) so an error
    can point at the offending field without echoing its value.
    """

    hits: list[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            name = str(key)
            path = f"{_prefix}.{name}" if _prefix else name
            if name.lower() in SENSITIVE_FIELD_NAMES:
                hits.append(path)
            hits.extend(find_sensitive_fields(value, _prefix=path))
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            hits.extend(find_sensitive_fields(item, _prefix=f"{_prefix}[{index}]"))
    return tuple(hits)


def parse_money(value: object, *, field_name: str) -> Decimal:
    """Parse a monetary value without ever using binary floating point.

    Strings and integers are accepted; ``float``/``bool`` are rejected so a
    lossy JSON number can never become a domain price (AUT-232).
    """

    if isinstance(value, (bool, float)):
        raise CaptureValidationError(
            "Valores monetários devem ser strings decimais, não números fracionários",
            context={"field": field_name},
        )
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise CaptureValidationError("Valor monetário vazio", context={"field": field_name})
        try:
            amount = Decimal(text)
        except InvalidOperation as exc:
            raise CaptureValidationError(
                "Valor monetário inválido", context={"field": field_name}
            ) from exc
    else:
        raise CaptureValidationError("Valor monetário inválido", context={"field": field_name})
    if not amount.is_finite() or amount < 0:
        raise CaptureValidationError("Valor monetário inválido", context={"field": field_name})
    return amount


def validate_source_url(url: str | None) -> str | None:
    """Reject unsafe URL schemes and non-absolute marketplace URLs.

    Mirrors the browser security boundary (AUT-281): only ``http``/``https`` are
    accepted and dangerous schemes such as ``javascript:`` fail closed.
    """

    if url is None:
        return None
    candidate = sanitize_single_line(url)
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in _ALLOWED_URL_SCHEMES or not parsed.netloc:
        raise CaptureValidationError(
            "URL de captura deve ser http(s) absoluta",
            context={"url_scheme": parsed.scheme or "missing"},
        )
    sensitive_params = sorted(
        {
            name
            for name, _value in parse_qsl(parsed.query, keep_blank_values=True)
            if name.lower() in _URL_SENSITIVE_PARAMS
        }
    )
    if sensitive_params:
        raise CaptureValidationError(
            "URL de captura contém parâmetro sensível",
            code=CAPTURE_SENSITIVE_FIELD,
            action="Remover tokens/sessão da URL antes de capturar",
            context={"query_params": sensitive_params},
        )
    return candidate


def to_utc(moment: datetime) -> datetime:
    """Normalize a timestamp to UTC, assuming naive values are already UTC."""

    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class CaptureIntake:
    """Raw, typed input received by the application service before validation.

    ``current_price``/``original_price`` carry the payload representation and are
    parsed by :func:`normalize_intake`; the domain never trusts the boundary to
    have converted money.
    """

    marketplace: Marketplace
    source: CaptureSource
    external_id: str
    current_price: object
    original_price: object | None = None
    title: str | None = None
    url: str | None = None
    category: str | None = None
    sales_count: int | None = None
    seller_name: str | None = None
    seller_id: str | None = None
    captured_at: datetime | None = None
    schema_version: str = CAPTURE_SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class NormalizedCapture:
    """Sanitized and validated capture ready to be materialized."""

    marketplace: Marketplace
    source: CaptureSource
    external_id: str
    title: str | None
    url: str | None
    current_price: Decimal
    original_price: Decimal | None
    sales_count: int | None
    seller_name: str | None
    seller_id: str | None
    captured_at: datetime | None
    schema_version: str
    category: str | None = None


def normalize_intake(intake: CaptureIntake) -> NormalizedCapture:
    """Sanitize and validate an intake, failing closed on any violation."""

    if intake.schema_version != CAPTURE_SCHEMA_VERSION:
        raise CaptureValidationError(
            "schema_version de captura não suportada",
            context={"schema_version": str(intake.schema_version)},
            action="Enviar a captura com schema_version suportada pela API",
        )

    external_id = sanitize_single_line(str(intake.external_id))
    if not external_id:
        raise CaptureValidationError("external_id é obrigatório", context={"field": "external_id"})
    if len(external_id) > MAX_EXTERNAL_ID_LENGTH:
        raise CaptureValidationError(
            "external_id excede o tamanho máximo",
            context={"field": "external_id", "max_length": MAX_EXTERNAL_ID_LENGTH},
        )

    current_price = parse_money(intake.current_price, field_name="current_price")
    if current_price <= 0:
        raise CaptureValidationError(
            "current_price deve ser maior que zero", context={"field": "current_price"}
        )
    original_price = (
        parse_money(intake.original_price, field_name="original_price")
        if intake.original_price is not None
        else None
    )

    if intake.sales_count is not None and intake.sales_count < 0:
        raise CaptureValidationError(
            "sales_count não pode ser negativo", context={"field": "sales_count"}
        )

    title = _sanitize_optional_text(intake.title, field_name="title")
    seller_name = _sanitize_optional_text(intake.seller_name, field_name="seller_name")
    seller_id = _sanitize_optional_text(intake.seller_id, field_name="seller_id")
    category = _sanitize_optional_text(intake.category, field_name="category")
    url = validate_source_url(intake.url)

    captured_at = to_utc(intake.captured_at) if intake.captured_at is not None else None

    return NormalizedCapture(
        marketplace=intake.marketplace,
        source=intake.source,
        external_id=external_id,
        title=title,
        url=url,
        current_price=current_price,
        original_price=original_price,
        sales_count=intake.sales_count,
        seller_name=seller_name,
        seller_id=seller_id,
        captured_at=captured_at,
        schema_version=CAPTURE_SCHEMA_VERSION,
        category=category,
    )


def _sanitize_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    cleaned = sanitize_single_line(str(value))
    if not cleaned:
        return None
    if len(cleaned) > MAX_TEXT_LENGTH:
        raise CaptureValidationError(
            "campo de texto excede o tamanho máximo",
            context={"field": field_name, "max_length": MAX_TEXT_LENGTH},
        )
    return cleaned


@dataclass(frozen=True, slots=True)
class Product:
    """Conceptual product (``docs/03_DOMAIN_MODEL.md``)."""

    id: str
    canonical_name: str
    created_at: datetime
    updated_at: datetime
    brand: str | None = None
    model: str | None = None
    category: str | None = None
    subcategory: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MarketplaceProduct:
    """The same product as seen inside one marketplace.

    ``marketplace + external_id`` is unique: repeated captures reuse this
    identity instead of creating a duplicate (``docs/03_DOMAIN_MODEL.md``).
    """

    id: str
    product_id: str
    marketplace: Marketplace
    external_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    url: str | None = None
    title: str | None = None
    seller_id: str | None = None
    raw_category: str | None = None


@dataclass(frozen=True, slots=True)
class Offer:
    """Commercial condition captured at a moment in time."""

    id: str
    marketplace_product_id: str
    current_price: Decimal
    captured_at: datetime
    source: CaptureSource
    correlation_id: str
    original_price: Decimal | None = None
    discount_percent: Decimal | None = None
    sales_count: int | None = None
    seller_id: str | None = None
    seller_name: str | None = None
    rating: float | None = None
    stock: int | None = None
    shipping_cost: Decimal | None = None
    coupon: str | None = None
    affiliate_commission: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PriceObservation:
    """Append-only monetary observation of a MarketplaceProduct (RDR-013).

    The documented identity of an observation is
    ``(marketplace_product_id, source, observed_at)``: a repeated capture with
    the same product, source and observed instant is the *same* observation and
    must reuse it instead of appending a duplicate or inventing a new price
    (AUT-028). Existing rows are never overwritten.
    """

    id: str
    marketplace_product_id: str
    price: Decimal
    observed_at: datetime
    source: CaptureSource
    correlation_id: str
    raw_capture_id: str
    original_price: Decimal | None = None
    shipping_cost: Decimal | None = None


def price_observation_identity(
    marketplace_product_id: str, source: CaptureSource, observed_at: datetime
) -> tuple[str, str, str]:
    """Return the documented identity of a price observation (AUT-028)."""

    return (marketplace_product_id, source.value, to_utc(observed_at).isoformat())


@dataclass(frozen=True, slots=True)
class RawCapture:
    """Structured payload preserved before normalization (AUT-027).

    Only the sanitized structured payload is stored; full HTML is never kept
    (AUT-203, AUT-204).
    """

    id: str
    marketplace: Marketplace
    source: CaptureSource
    payload: Mapping[str, Any]
    captured_at: datetime
    correlation_id: str
    schema_version: str
    source_url: str | None = None


@dataclass(frozen=True, slots=True)
class Evidence:
    """Provenance of a fact (``docs/03_DOMAIN_MODEL.md``).

    ``confidence`` stays ``None`` until the Confidence Engine (RDR-029) owns its
    calibration; this ticket must not invent scoring/calibration values.
    """

    id: str
    entity_type: str
    entity_id: str
    field_name: str
    value: str
    source_type: str
    captured_at: datetime
    raw_reference: str | None = None
    source_url: str | None = None
    confidence: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryEvent:
    """Registers the origin of a discovery (``docs/03_DOMAIN_MODEL.md``)."""

    id: str
    marketplace: Marketplace
    source: CaptureSource
    external_id: str
    raw_capture_id: str
    correlation_id: str
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class Candidate:
    """Indicates an Offer entered the evaluation pipeline."""

    id: str
    offer_id: str
    state: CandidateState
    correlation_id: str
    raw_capture_id: str
    discovery_event_id: str
    audit_event_id: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class CaptureAggregate:
    """The full graph persisted atomically for one capture.

    ``product`` is ``None`` when the marketplace identity already exists (only
    ``last_seen_at`` is refreshed); ``marketplace_product`` is then the existing
    identity.
    """

    product: Product | None
    marketplace_product: MarketplaceProduct
    create_marketplace_product: bool
    offer: Offer
    price_observation: PriceObservation
    create_price_observation: bool
    raw_capture: RawCapture
    evidence: tuple[Evidence, ...]
    discovery_event: DiscoveryEvent
    candidate: Candidate
    audit_event: AuditEvent


@dataclass(frozen=True, slots=True)
class CapturedOffer:
    """Public result of a capture and the queryable Candidate projection."""

    schema_version: str
    correlation_id: str
    candidate_id: str
    candidate_state: str
    offer_id: str
    product_id: str
    marketplace_product_id: str
    raw_capture_id: str
    discovery_event_id: str
    audit_event_id: str
    marketplace: str
    external_id: str
    source: str
    title: str | None
    captured_at: datetime
    price_observation_id: str | None = None
    duplicate_identity: bool | None = None

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "correlation_id": self.correlation_id,
            "candidate_id": self.candidate_id,
            "candidate_state": self.candidate_state,
            "offer_id": self.offer_id,
            "product_id": self.product_id,
            "marketplace_product_id": self.marketplace_product_id,
            "raw_capture_id": self.raw_capture_id,
            "discovery_event_id": self.discovery_event_id,
            "audit_event_id": self.audit_event_id,
            "marketplace": self.marketplace,
            "external_id": self.external_id,
            "source": self.source,
            "title": self.title,
            "captured_at": self.captured_at.isoformat(),
        }
        if self.price_observation_id is not None:
            payload["price_observation_id"] = self.price_observation_id
        if self.duplicate_identity is not None:
            payload["duplicate_identity"] = self.duplicate_identity
        return payload


@dataclass(frozen=True, slots=True)
class PriceHistoryPoint:
    """One observation projected into the public price-history contract."""

    price_observation_id: str
    price: Decimal
    observed_at: datetime
    source: str
    correlation_id: str
    raw_capture_id: str
    original_price: Decimal | None = None
    shipping_cost: Decimal | None = None

    def to_contract(self) -> dict[str, Any]:
        return {
            "price_observation_id": self.price_observation_id,
            "price": str(self.price),
            "original_price": None if self.original_price is None else str(self.original_price),
            "shipping_cost": None if self.shipping_cost is None else str(self.shipping_cost),
            "source": self.source,
            "observed_at": self.observed_at.isoformat(),
            "correlation_id": self.correlation_id,
            "raw_capture_id": self.raw_capture_id,
        }


@dataclass(frozen=True, slots=True)
class MarketplacePriceHistory:
    """Queryable, chronological price series for one MarketplaceProduct.

    Returned by ``GET /marketplace-products/{id}/price-history``. The series is
    read-only and append-only by construction; it never computes or infers a
    price (RDR-013).
    """

    marketplace_product_id: str
    marketplace: str
    external_id: str
    observations: tuple[PriceHistoryPoint, ...]

    def to_contract(self, *, correlation_id: str) -> dict[str, Any]:
        return {
            "schema_version": PRICE_HISTORY_SCHEMA_VERSION,
            "status": "OK",
            "correlation_id": correlation_id,
            "marketplace_product_id": self.marketplace_product_id,
            "marketplace": self.marketplace,
            "external_id": self.external_id,
            "observation_count": len(self.observations),
            "observations": [point.to_contract() for point in self.observations],
        }


def build_raw_payload(normalized: NormalizedCapture, *, captured_at: datetime) -> dict[str, Any]:
    """Build the sanitized structured RawCapture payload (no HTML, no secrets)."""

    seller: dict[str, Any] | None = None
    if normalized.seller_name is not None or normalized.seller_id is not None:
        seller = {}
        if normalized.seller_name is not None:
            seller["name"] = normalized.seller_name
        if normalized.seller_id is not None:
            seller["id"] = normalized.seller_id

    return {
        "schema_version": normalized.schema_version,
        "marketplace": normalized.marketplace.value,
        "source": normalized.source.value,
        "product": {
            "external_id": normalized.external_id,
            "title": normalized.title,
            "url": normalized.url,
            "category": normalized.category,
        },
        "offer": {
            "current_price": str(normalized.current_price),
            "original_price": (
                str(normalized.original_price) if normalized.original_price is not None else None
            ),
            "sales_count": normalized.sales_count,
            "seller": seller,
        },
        "captured_at": captured_at.isoformat(),
    }


def compute_discount_percent(
    current_price: Decimal, original_price: Decimal | None
) -> Decimal | None:
    """Deterministic discount percentage; never invents a discount."""

    if original_price is None or original_price <= 0 or original_price <= current_price:
        return None
    percent = (original_price - current_price) / original_price * Decimal(100)
    return percent.quantize(Decimal("0.01"))


#: A callable that produces a fresh identifier for a given prefix.
IdFactory = Callable[[str], str]


def default_id_factory(prefix: str) -> str:
    """Generate a readable, opaque identifier such as ``cand_ab12...``."""

    import uuid

    return f"{prefix}_{uuid.uuid4().hex}"
