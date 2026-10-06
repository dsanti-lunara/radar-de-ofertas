"""AffiliateLink: own, auditable entity generated after Opportunity approval
(RDR-018, AUT-033, AUT-290).

``docs/03_DOMAIN_MODEL.md`` makes ``AffiliateLink`` an independent entity with its
own ``original_url``, ``affiliate_url``, ``generation_method``, ``tracking`` and
``status``. This module implements the framework-free core (AUT-397):

* a link is only built for an **approved** Opportunity and its internal
  :class:`~radar.domain.tracking.TrackingContext`; the provider is a narrow port
  so the Fake is used offline and the real marketplace adapter stays gated
  (AUT-359, AUT-421);
* the returned URL is validated before persistence and stored **literally** — the
  domain never rewrites, shortens or edits it and the AI never touches a URL
  (AUT-078, AUT-164);
* validation rejects an invalid host and a link that does not correspond to the
  expected product/catalog context (AUT-281, AUT-289, ``RECON-003``);
* a Fake link is marked ``productive=false`` and cannot be used as a productive
  link (AUT-422).

No AI, HTTP, SQLAlchemy or browser code lives here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from urllib.parse import parse_qsl, urlparse

from radar.domain.capture import (
    IdFactory,
    Marketplace,
    default_id_factory,
    find_sensitive_fields,
    sanitize_single_line,
)
from radar.domain.errors import RadarError, RadarException
from radar.domain.tracking import TrackingContext

#: Version of the public AffiliateLink contract.
AFFILIATE_LINK_SCHEMA_VERSION = "1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
AFFILIATE_LINK_INPUT_INVALID = "RAD-LINK-001"
AFFILIATE_LINK_NOT_FOUND = "RAD-LINK-002"
AFFILIATE_LINK_URL_INVALID = "RAD-LINK-003"
AFFILIATE_LINK_PROVIDER_UNAVAILABLE = "RAD-LINK-006"
AFFILIATE_LINK_OPPORTUNITY_NOT_LINKABLE = "RAD-LINK-007"
AFFILIATE_LINK_NOT_PRODUCTIVE = "RAD-LINK-008"

#: Entity type recorded on the AffiliateLink audit event.
ENTITY_AFFILIATE_LINK = "affiliate_link"

#: Provenance source recorded on the AffiliateLink audit event.
AUDIT_SOURCE_AFFILIATE_LINK = "link"

#: Default per-attempt timeout handed to a provider (``docs/04_DATA_CONTRACTS.md``).
DEFAULT_LINK_TIMEOUT_SECONDS = 60

_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})
_URL_SENSITIVE_PARAMS = frozenset({"token", "secret", "cookie", "authorization", "password"})

#: Affiliate/redirect hosts allowed per marketplace (AUT-281, RECON-003).
AFFILIATE_HOSTS: Mapping[Marketplace, frozenset[str]] = {
    Marketplace.MERCADO_LIVRE: frozenset(
        {
            "mercadolivre.com.br",
            "mercadolibre.com",
            "meli.la",
        }
    ),
    Marketplace.SHOPEE: frozenset(
        {
            "shopee.com.br",
            "shope.ee",
        }
    ),
}


class LinkGenerationMethod(StrEnum):
    """How an AffiliateLink was produced (``docs/03_DOMAIN_MODEL.md``)."""

    FAKE = "FAKE"
    ML_LINK_GENERATOR = "ML_LINK_GENERATOR"
    ML_AFFILIATE_BAR = "ML_AFFILIATE_BAR"
    SHOPEE_API = "SHOPEE_API"
    MANUAL_PORTAL = "MANUAL_PORTAL"


class AffiliateLinkStatus(StrEnum):
    """Lifecycle status of a validated AffiliateLink."""

    VALIDATED = "VALIDATED"


#: Provider ``source`` -> internal generation method. Unknown source fails closed.
_SOURCE_TO_METHOD: Mapping[str, LinkGenerationMethod] = {
    "FAKE": LinkGenerationMethod.FAKE,
    "ML_LINK_GENERATOR": LinkGenerationMethod.ML_LINK_GENERATOR,
    "ML_AFFILIATE_BAR": LinkGenerationMethod.ML_AFFILIATE_BAR,
    "SHOPEE_API": LinkGenerationMethod.SHOPEE_API,
    "MANUAL_PORTAL": LinkGenerationMethod.MANUAL_PORTAL,
}


class AffiliateLinkError(RadarException):
    """Raised when an AffiliateLink cannot be produced safely."""


def affiliate_link_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> AffiliateLinkError:
    return AffiliateLinkError(
        RadarError(
            code=AFFILIATE_LINK_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o input de geração de link e enviar novamente",
            context=dict(context or {}),
        )
    )


def affiliate_link_not_found_error(affiliate_link_id: str) -> AffiliateLinkError:
    return AffiliateLinkError(
        RadarError(
            code=AFFILIATE_LINK_NOT_FOUND,
            message="AffiliateLink não encontrado",
            retryable=False,
            action="Verificar o affiliate_link_id informado",
            context={"affiliate_link_id": affiliate_link_id},
        )
    )


def affiliate_link_url_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> AffiliateLinkError:
    return AffiliateLinkError(
        RadarError(
            code=AFFILIATE_LINK_URL_INVALID,
            message=message,
            retryable=False,
            action=(
                "Descartar o link retornado e revisar a geração; o link não é "
                "editado nem sintetizado"
            ),
            context=dict(context or {}),
        )
    )


def affiliate_link_provider_unavailable_error(*, provider: str) -> AffiliateLinkError:
    return AffiliateLinkError(
        RadarError(
            code=AFFILIATE_LINK_PROVIDER_UNAVAILABLE,
            message="Provider de link afiliado indisponível",
            retryable=True,
            action="Reexecutar a geração quando o provider estiver disponível",
            context={"provider": provider},
        )
    )


def affiliate_link_opportunity_not_linkable_error(
    *, candidate_id: str, opportunity_id: str | None = None, state: str | None = None
) -> AffiliateLinkError:
    return AffiliateLinkError(
        RadarError(
            code=AFFILIATE_LINK_OPPORTUNITY_NOT_LINKABLE,
            message="Opportunity não está em estado linkável",
            retryable=False,
            action=(
                "Gerar link apenas para uma Opportunity criada por um Candidate "
                "aprovado em LINK_PENDING/LINK_READY"
            ),
            context={
                "candidate_id": candidate_id,
                "opportunity_id": opportunity_id,
                "state": state,
            },
        )
    )


def affiliate_link_not_productive_error(affiliate_link_id: str) -> AffiliateLinkError:
    return AffiliateLinkError(
        RadarError(
            code=AFFILIATE_LINK_NOT_PRODUCTIVE,
            message="Link Fake não pode ser usado como link produtivo",
            retryable=False,
            action="Gerar um link por um provider produtivo antes de publicar",
            context={"affiliate_link_id": affiliate_link_id},
        )
    )


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _host_allowed(host: str, marketplace: Marketplace) -> bool:
    candidate = host.lower().rstrip(".")
    if not candidate:
        return False
    for allowed in AFFILIATE_HOSTS[marketplace]:
        if candidate == allowed or candidate.endswith(f".{allowed}"):
            return True
    return False


def validate_affiliate_url(url: object, *, marketplace: Marketplace) -> str:
    """Validate a returned affiliate URL, preserving it literally.

    The URL must be an absolute ``http(s)`` URL whose host belongs to the
    marketplace's affiliate host set and must not carry a sensitive query
    parameter. The value is returned **unchanged**: whitespace or separators are
    rejected instead of normalized, so the stored link is exactly what the
    provider returned (AUT-078, AUT-164).
    """

    if not isinstance(url, str):
        raise affiliate_link_url_invalid_error(
            "affiliate_url deve ser texto", context={"field": "affiliate_url"}
        )
    if not url:
        raise affiliate_link_url_invalid_error(
            "affiliate_url vazia", context={"field": "affiliate_url"}
        )
    if url != url.strip():
        raise affiliate_link_url_invalid_error(
            "affiliate_url com espaços nas bordas não é preservada literalmente",
            context={"field": "affiliate_url"},
        )
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_URL_SCHEMES or not parsed.netloc:
        raise affiliate_link_url_invalid_error(
            "affiliate_url deve ser http(s) absoluta",
            context={"field": "affiliate_url", "scheme": parsed.scheme or "missing"},
        )
    host = parsed.hostname or ""
    if not _host_allowed(host, marketplace):
        raise affiliate_link_url_invalid_error(
            "affiliate_url com host não permitido para o marketplace",
            context={"field": "affiliate_url", "marketplace": marketplace.value, "host": host},
        )
    sensitive_params = sorted(
        {
            name
            for name, _value in parse_qsl(parsed.query, keep_blank_values=True)
            if name.lower() in _URL_SENSITIVE_PARAMS
        }
    )
    if sensitive_params:
        raise affiliate_link_url_invalid_error(
            "affiliate_url contém parâmetro sensível",
            context={"field": "affiliate_url", "query_params": sensitive_params},
        )
    return url


@dataclass(frozen=True, slots=True)
class AffiliateLinkRequest:
    """Versioned, sanitized request handed to an :class:`AffiliateLinkProvider`."""

    opportunity_id: str
    marketplace: Marketplace
    original_url: str
    external_id: str
    tracking: TrackingContext
    timeout_seconds: int = DEFAULT_LINK_TIMEOUT_SECONDS

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": AFFILIATE_LINK_SCHEMA_VERSION,
            "opportunity_id": self.opportunity_id,
            "marketplace": self.marketplace.value,
            "original_url": self.original_url,
            "external_id": self.external_id,
            "tracking": self.tracking.to_contract(),
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class AffiliateLinkOutcome:
    """Validated provider result: the literal URL and how it was produced."""

    affiliate_url: str
    generation_method: LinkGenerationMethod
    product_reference: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "affiliate_url": self.affiliate_url,
            "generation_method": self.generation_method.value,
            "product_reference": self.product_reference,
        }


@dataclass(frozen=True, slots=True)
class AffiliateLink:
    """Independent, auditable affiliate link of one approved Opportunity."""

    affiliate_link_id: str
    opportunity_id: str
    marketplace: Marketplace
    original_url: str
    affiliate_url: str
    generation_method: LinkGenerationMethod
    tracking: TrackingContext
    correlation_id: str
    audit_event_id: str
    created_at: datetime
    status: AffiliateLinkStatus = AffiliateLinkStatus.VALIDATED
    schema_version: str = AFFILIATE_LINK_SCHEMA_VERSION

    @property
    def productive(self) -> bool:
        """A Fake link is never a productive link (AUT-422)."""

        return self.generation_method is not LinkGenerationMethod.FAKE

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "affiliate_link_id": self.affiliate_link_id,
            "opportunity_id": self.opportunity_id,
            "marketplace": self.marketplace.value,
            "original_url": self.original_url,
            "affiliate_url": self.affiliate_url,
            "generation_method": self.generation_method.value,
            "productive": self.productive,
            "tracking": self.tracking.to_contract(),
            "correlation_id": self.correlation_id,
            "audit_event_id": self.audit_event_id,
            "created_at": _to_utc(self.created_at).isoformat(),
        }


@runtime_checkable
class AffiliateLinkProvider(Protocol):
    """Contract every affiliate link provider (Fake first) must satisfy.

    The provider isolates the external call and returns a raw structured mapping
    that the domain validates before anything is persisted. The real marketplace
    adapters remain gated by Browser Reconnaissance/SPIKE and are not implemented
    here (AUT-354, AUT-426).
    """

    @property
    def name(self) -> str: ...

    def generate(self, request: AffiliateLinkRequest) -> Mapping[str, Any]: ...


def parse_affiliate_link_response(
    raw: object, *, provider: str, request: AffiliateLinkRequest
) -> AffiliateLinkOutcome:
    """Validate a raw provider response, failing closed on any breach.

    A non-mapping response, a sensitive field, an invalid/unknown source, a host
    outside the marketplace allowlist or a product context that does not match the
    expected ``external_id`` is rejected with ``RAD-LINK-003``; no partially valid
    response is ever persisted.
    """

    if not isinstance(raw, Mapping):
        raise affiliate_link_url_invalid_error(
            "resposta do provider deve ser um objeto", context={"provider": provider}
        )
    sensitive = find_sensitive_fields(raw)
    if sensitive:
        raise affiliate_link_url_invalid_error(
            "resposta do provider contém campo sensível",
            context={"provider": provider, "fields": list(sensitive)},
        )
    if "affiliate_url" not in raw:
        raise affiliate_link_url_invalid_error(
            "resposta do provider sem affiliate_url", context={"provider": provider}
        )
    affiliate_url = validate_affiliate_url(
        raw.get("affiliate_url"), marketplace=request.marketplace
    )

    source = raw.get("source")
    if not isinstance(source, str) or source not in _SOURCE_TO_METHOD:
        raise affiliate_link_url_invalid_error(
            "source do provider inválido",
            context={"provider": provider, "allowed": sorted(_SOURCE_TO_METHOD)},
        )
    generation_method = _SOURCE_TO_METHOD[source]

    product_reference = raw.get("product_reference")
    if not isinstance(product_reference, str) or not product_reference.strip():
        raise affiliate_link_url_invalid_error(
            "resposta do provider sem product_reference",
            context={"provider": provider},
        )
    if sanitize_single_line(product_reference) != sanitize_single_line(request.external_id):
        raise affiliate_link_url_invalid_error(
            "link retornado não corresponde ao produto/catálogo esperado",
            context={
                "provider": provider,
                "expected_product_reference": sanitize_single_line(request.external_id),
                "returned_product_reference": sanitize_single_line(product_reference),
            },
        )

    return AffiliateLinkOutcome(
        affiliate_url=affiliate_url,
        generation_method=generation_method,
        product_reference=sanitize_single_line(product_reference),
    )


def build_affiliate_link(
    *,
    request: AffiliateLinkRequest,
    outcome: AffiliateLinkOutcome,
    correlation_id: object,
    audit_event_id: object,
    created_at: datetime,
    affiliate_link_id: object | None = None,
    schema_version: object = AFFILIATE_LINK_SCHEMA_VERSION,
    id_factory: IdFactory = default_id_factory,
) -> AffiliateLink:
    """Assemble the AffiliateLink from a validated outcome.

    The caller has already validated the provider response; this function only
    validates the concrete fields and generates the identifier. A missing external
    label or ``schema_version`` fails closed.
    """

    if str(schema_version) != AFFILIATE_LINK_SCHEMA_VERSION:
        raise affiliate_link_input_invalid_error(
            "schema_version de AffiliateLink não suportada",
            context={"supported": AFFILIATE_LINK_SCHEMA_VERSION},
        )
    if not request.tracking.configured or request.tracking.external_label is None:
        raise affiliate_link_input_invalid_error(
            "AffiliateLink exige um TrackingContext com etiqueta configurada",
            context={"internal_reference": request.tracking.internal_reference},
        )
    resolved_id = (
        str(id_factory("lnk"))
        if affiliate_link_id is None
        else sanitize_single_line(str(affiliate_link_id))
    )
    return AffiliateLink(
        affiliate_link_id=resolved_id,
        opportunity_id=request.opportunity_id,
        marketplace=request.marketplace,
        original_url=request.original_url,
        affiliate_url=outcome.affiliate_url,
        generation_method=outcome.generation_method,
        tracking=request.tracking,
        correlation_id=sanitize_single_line(str(correlation_id)),
        audit_event_id=sanitize_single_line(str(audit_event_id)),
        created_at=_to_utc(created_at),
    )


def require_productive(link: AffiliateLink) -> AffiliateLink:
    """Return the link only when it may be used as a productive link."""

    if not link.productive:
        raise affiliate_link_not_productive_error(link.affiliate_link_id)
    return link


__all__ = [
    "AFFILIATE_HOSTS",
    "AFFILIATE_LINK_INPUT_INVALID",
    "AFFILIATE_LINK_NOT_FOUND",
    "AFFILIATE_LINK_NOT_PRODUCTIVE",
    "AFFILIATE_LINK_OPPORTUNITY_NOT_LINKABLE",
    "AFFILIATE_LINK_PROVIDER_UNAVAILABLE",
    "AFFILIATE_LINK_SCHEMA_VERSION",
    "AFFILIATE_LINK_URL_INVALID",
    "AUDIT_SOURCE_AFFILIATE_LINK",
    "DEFAULT_LINK_TIMEOUT_SECONDS",
    "ENTITY_AFFILIATE_LINK",
    "AffiliateLink",
    "AffiliateLinkError",
    "AffiliateLinkOutcome",
    "AffiliateLinkProvider",
    "AffiliateLinkRequest",
    "AffiliateLinkStatus",
    "LinkGenerationMethod",
    "affiliate_link_input_invalid_error",
    "affiliate_link_not_found_error",
    "affiliate_link_not_productive_error",
    "affiliate_link_opportunity_not_linkable_error",
    "affiliate_link_provider_unavailable_error",
    "affiliate_link_url_invalid_error",
    "build_affiliate_link",
    "parse_affiliate_link_response",
    "require_productive",
    "validate_affiliate_url",
]
