"""ContentGeneration, deterministic guards, renderer and AI input cache
(RDR-019, RDR-051, RDR-052, RDR-053, RDR-054, RDR-055, RDR-069).

``docs/03_DOMAIN_MODEL.md`` keeps ``ContentGeneration`` separate from
``Publication`` (AUT-034) and ``docs/06_AI_ENGINE.md`` separates ``AIReview`` from
``Content Generation`` (AUT-081). This module implements the framework-free core
of that slice (AUT-397):

* the ``Content Generation`` task contract (RDR-051): the provider returns only
  ``headline``/``body``/``cta``/``warnings``; the URL, the rendered price and the
  disclosure are inserted by the deterministic renderer, never by the AI
  (AUT-163, ``docs/04_DATA_CONTRACTS.md``);
* the local validators that precede usable content (AUT-082): schema,
  Numeric Guard (RDR-052), Claim Guard (RDR-053), channel rules and compliance
  (RDR-054). A commercial number or a claim without backend ``Evidence`` blocks a
  publishable preview instead of being persisted as valid;
* the deterministic renderer (RDR-069) that reads the validated
  :class:`~radar.domain.affiliate_link.AffiliateLink` literal URL and the
  backend-sustained ``CURRENT_PRICE`` claim, so the AI can never invent a price or
  a URL (AUT-031, AUT-164);
* generated and final content are stored separately with their own versions
  (``generation_version``/``knowledge_version``/``prompt_version``/
  ``renderer_version``), and the persisted facts are hashed so content becomes
  ``STALE`` when a relevant fact changes (``docs/08_WORKFLOW_ENGINE.md``);
* the versioned provider input is hashed canonically (``canonical_ai_input_hash``,
  RDR-055) so an equivalent input can reuse the persisted result while a change to
  product/offer, scores, warnings or Knowledge/Prompt versions invalidates it
  (``docs/06_AI_ENGINE.md`` Cache).

No AI, HTTP, SQLAlchemy or browser code lives here.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from radar.domain.ai_review import (
    AI_INVALID_RESPONSE,
    AI_POLICY_VIOLATION,
    AIReviewEvaluationFacts,
    AIReviewOfferFacts,
    AIReviewProductFacts,
    sanitize_ai_text,
)
from radar.domain.allowed_claims import (
    FORBIDDEN_CLAIMS,
    AllowedClaimsResult,
    ClaimUnit,
)
from radar.domain.capture import IdFactory, default_id_factory, find_sensitive_fields
from radar.domain.errors import RadarError, RadarException
from radar.domain.knowledge import Channel, KnowledgeContext
from radar.domain.operations import ChannelCompliancePolicy, ComplianceStatus
from radar.domain.taxonomy import Brand

#: Version of the public ContentGeneration contract.
CONTENT_SCHEMA_VERSION = "1.0"

#: Task name of the Content Generation step (``docs/06_AI_ENGINE.md``).
GENERATE_CONTENT_TASK = "GENERATE_CONTENT"

#: Versions stored on every ContentGeneration so the copy stays reproducible.
CONTENT_GENERATION_ENGINE_VERSION = "content-generation-1.0"
CONTENT_GUARD_ENGINE_VERSION = "content-guard-1.0"
CONTENT_RENDERER_VERSION = "renderer-1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
UNSUPPORTED_NUMERIC_CLAIM = "RAD-AI-005"
UNSUPPORTED_CLAIM = "RAD-AI-006"
CONTENT_GENERATION_NOT_FOUND = "RAD-AI-011"
CONTENT_INPUT_INVALID = "RAD-AI-012"
CONTENT_URL_NOT_ALLOWED = "RAD-AI-013"
CONTENT_CHANNEL_INVALID = "RAD-AI-014"
CONTENT_COMPLIANCE_BLOCKED = "RAD-AI-015"

#: Entity type/provenance recorded on the ContentGeneration audit event.
ENTITY_CONTENT_GENERATION = "content_generation"
AUDIT_SOURCE_CONTENT = "content"

#: Warning emitted when the compliance policy is not ACTIVE (preview allowed).
WARNING_COMPLIANCE_NOT_ACTIVE = "CONTENT_COMPLIANCE_NOT_ACTIVE"

#: Deterministic commercial disclosure required on every affiliate content.
DISCLOSURE_TEXT = "Conteúdo de afiliado: podemos receber comissão por compras feitas pelos links."

#: Max length of a single generated field (headline/body/cta).
MAX_CONTENT_FIELD_LENGTH = 2048

#: Documented Telegram Bot API message limit; WhatsApp uses the same conservative
#: bound until a channel-specific limit is approved (explicit gap).
CHANNEL_MESSAGE_LIMITS: Mapping[Channel, int] = {
    Channel.TELEGRAM: 4096,
    Channel.WHATSAPP: 4096,
}

#: Forbidden claims of ``docs/06_AI_ENGINE.md`` mapped to the expressions the
#: Claim Guard refuses. The list is conservative and versioned by the guard
#: engine; matching is accent/case-insensitive and word-bounded.
FORBIDDEN_EXPRESSIONS: Mapping[str, tuple[str, ...]] = {
    "BEST_PRICE_ON_THE_INTERNET": (
        "melhor preco da internet",
        "menor preco da internet",
        "preco imbatiel",
        "mais barato do brasil",
        "preco mais baixo do mercado",
    ),
    "LAST_UNITS": (
        "ultimas unidades",
        "ultima unidade",
        "ultimas pecas",
        "so restam",
    ),
    "WILL_SELL_OUT": (
        "vai esgotar",
        "vai acabar",
        "acaba rapido",
        "corre que acaba",
        "estoque acabando",
    ),
    "GUARANTEED_ORIGINAL": (
        "original garantido",
        "produto original garantido",
        "garantia de original",
        "100% original",
    ),
    "PERSONAL_EXPERIENCE": (
        "eu testei",
        "eu usei",
        "eu comprei",
        "minha experiencia",
        "recomendo porque usei",
    ),
    # UNVERIFIED_COUPON is only refused when the backend has no CONFIRMED_COUPON.
    "UNVERIFIED_COUPON": ("cupom",),
}

_ALLOWED_RESPONSE_FIELDS = frozenset({"headline", "body", "cta", "warnings"})
_URL_PATTERN = re.compile(r"(https?://|www\.)", re.IGNORECASE)
_NUMBER_TOKEN = re.compile(r"\d[\d.,]*")
_WHITESPACE = re.compile(r"\s+")


class ContentGenerationStatus(StrEnum):
    """Lifecycle status of a ContentGeneration preview.

    ``STALE`` is derived on read from the persisted fact hash, so the stored row
    is never mutated to change status (``docs/08_WORKFLOW_ENGINE.md``).
    """

    VALIDATED = "VALIDATED"
    STALE = "STALE"


class ContentGenerationError(RadarException):
    """Raised when a ContentGeneration cannot be produced safely."""


def _provider_error(
    code: str,
    message: str,
    *,
    retryable: bool,
    action: str,
    context: Mapping[str, Any] | None = None,
) -> ContentGenerationError:
    return ContentGenerationError(
        RadarError(
            code=code,
            message=message,
            retryable=retryable,
            action=action,
            context=dict(context or {}),
        )
    )


def content_generation_not_found_error(content_generation_id: str) -> ContentGenerationError:
    """Build the structured not-found error for a ContentGeneration query."""

    return ContentGenerationError(
        RadarError(
            code=CONTENT_GENERATION_NOT_FOUND,
            message="ContentGeneration não encontrada",
            retryable=False,
            action="Verificar o content_generation_id informado",
            context={"content_generation_id": content_generation_id},
        )
    )


def content_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> ContentGenerationError:
    """Build the structured error for invalid ContentGeneration input/state."""

    return ContentGenerationError(
        RadarError(
            code=CONTENT_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Gerar conteúdo apenas para Opportunity com AffiliateLink validado e canal suportado",
            context=dict(context or {}),
        )
    )


def content_url_not_allowed_error(*, field_name: str, provider: str) -> ContentGenerationError:
    """Build the structured error for a URL the AI tried to introduce."""

    return _provider_error(
        CONTENT_URL_NOT_ALLOWED,
        "Conteúdo gerado pela IA não pode conter URL; o renderer usa o link validado",
        retryable=False,
        action="Descartar a resposta e gerar novamente sem URL; o link é inserido pelo backend",
        context={"field": field_name, "provider": provider},
    )


def content_invalid_response_error(
    message: str, *, provider: str | None = None, context: Mapping[str, Any] | None = None
) -> ContentGenerationError:
    """Build the structured error for a malformed Content Generation response."""

    details = dict(context or {})
    if provider:
        details["provider"] = provider
    return _provider_error(
        AI_INVALID_RESPONSE,
        message,
        retryable=False,
        action="Descartar a resposta do provider e revisar o contexto de geração",
        context=details,
    )


def content_policy_violation_error(
    *, provider: str, context: Mapping[str, Any] | None = None
) -> ContentGenerationError:
    """Build the structured error for a response that breaches the contract."""

    return _provider_error(
        AI_POLICY_VIOLATION,
        "Resposta do provider violou o contrato (campo sensível ou conteúdo não confiável)",
        retryable=False,
        action="Descartar a resposta e revisar o provider/contexto de geração",
        context={"provider": provider, **dict(context or {})},
    )


def unsupported_numeric_claim_error(
    *, field_name: str, context: Mapping[str, Any] | None = None
) -> ContentGenerationError:
    """Build the structured error for a commercial number without Evidence."""

    return ContentGenerationError(
        RadarError(
            code=UNSUPPORTED_NUMERIC_CLAIM,
            message="Número comercial sem Evidence bloqueia a preview publicável",
            retryable=False,
            action="Remover/ajustar o número para um valor sustentado por allowed_claims",
            context={"field": field_name, **dict(context or {})},
        )
    )


def unsupported_claim_error(
    *, claim_code: str, context: Mapping[str, Any] | None = None
) -> ContentGenerationError:
    """Build the structured error for a claim without backend Evidence."""

    return ContentGenerationError(
        RadarError(
            code=UNSUPPORTED_CLAIM,
            message="Claim sem Evidence bloqueia a preview publicável",
            retryable=False,
            action="Remover o claim proibido/não sustentado e gerar novamente",
            context={"claim_code": claim_code, **dict(context or {})},
        )
    )


def content_channel_invalid_error(
    *, channel: str, context: Mapping[str, Any] | None = None
) -> ContentGenerationError:
    """Build the structured error for content that breaks the channel rules."""

    return ContentGenerationError(
        RadarError(
            code=CONTENT_CHANNEL_INVALID,
            message="Conteúdo excede as regras do canal",
            retryable=False,
            action="Reduzir o conteúdo para caber no limite do canal",
            context={"channel": channel, **dict(context or {})},
        )
    )


def content_compliance_blocked_error(
    *, context: Mapping[str, Any] | None = None
) -> ContentGenerationError:
    """Build the structured error for content blocked by compliance."""

    return ContentGenerationError(
        RadarError(
            code=CONTENT_COMPLIANCE_BLOCKED,
            message="Policy de compliance bloqueia a preview de conteúdo",
            retryable=False,
            action="Revisar a compliance policy antes de gerar conteúdo para o canal",
            context=dict(context or {}),
        )
    )


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def canonical_money(value: object) -> str:
    """Canonicalize a monetary value as a stable decimal string."""

    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise content_input_invalid_error(
            "Preço para renderer deve ser decimal", context={"value": str(value)}
        ) from exc
    if not amount.is_finite() or amount < 0:
        raise content_input_invalid_error(
            "Preço para renderer inválido", context={"value": str(value)}
        )
    return str(amount.quantize(Decimal("0.01")))


def _format_price(value: object) -> str:
    canonical = canonical_money(value)
    integral, _, decimals = canonical.partition(".")
    grouped = f"{int(integral):,}".replace(",", ".")
    return f"{grouped},{decimals}"


def _normalize_for_match(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _WHITESPACE.sub(" ", without_accents).strip()


def _contains_phrase(haystack: str, phrase: str) -> bool:
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])")
    return pattern.search(haystack) is not None


def _extract_numbers(text: str) -> tuple[str, ...]:
    return tuple(match.group(0) for match in _NUMBER_TOKEN.finditer(text))


def _numeric_value(token: str) -> Decimal | None:
    normalized = token
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _digits(token: str) -> str:
    digits = re.sub(r"\D", "", token).lstrip("0")
    return digits or "0"


@dataclass(frozen=True, slots=True)
class ContentWarning:
    """Explicit, non-fatal warning attached to a ContentGeneration."""

    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.context:
            payload["context"] = dict(self.context)
        return payload


@dataclass(frozen=True, slots=True)
class ContentGuardError:
    """One guard that refused a piece of generated content."""

    code: str
    guard: str
    message: str
    field_name: str | None = None
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "guard": self.guard,
            "message": self.message,
        }
        if self.field_name:
            payload["field"] = self.field_name
        if self.context:
            payload["context"] = dict(self.context)
        return payload


@dataclass(frozen=True, slots=True)
class ContentValidation:
    """Deterministic result of running the local content guards (AUT-082)."""

    guards: tuple[str, ...]
    errors: tuple[ContentGuardError, ...]
    warnings: tuple[ContentWarning, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_contract(self) -> dict[str, Any]:
        return {
            "guard_engine_version": CONTENT_GUARD_ENGINE_VERSION,
            "guards": list(self.guards),
            "passed": self.passed,
            "errors": [error.to_contract() for error in self.errors],
            "warnings": [warning.to_contract() for warning in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class GeneratedContent:
    """Raw ``headline``/``body``/``cta`` returned by the AI provider (RDR-051)."""

    headline: str
    body: str
    cta: str
    warnings: tuple[ContentWarning, ...] = ()

    def to_contract(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "body": self.body,
            "cta": self.cta,
            "warnings": [warning.to_contract() for warning in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class RenderedContent:
    """Deterministic final content: AI copy plus backend price/link/disclosure."""

    headline: str
    body: str
    cta: str
    price: str
    price_display: str
    affiliate_url: str
    disclosure: str
    tracking: Mapping[str, Any]
    blocks: tuple[str, ...]
    text: str
    renderer_version: str = CONTENT_RENDERER_VERSION

    def to_contract(self) -> dict[str, Any]:
        return {
            "headline": self.headline,
            "body": self.body,
            "cta": self.cta,
            "price": self.price,
            "price_display": self.price_display,
            "affiliate_url": self.affiliate_url,
            "disclosure": self.disclosure,
            "tracking": dict(self.tracking),
            "blocks": list(self.blocks),
            "text": self.text,
            "renderer_version": self.renderer_version,
        }


@dataclass(frozen=True, slots=True)
class ContentGenerationInput:
    """Versioned, sanitized input handed to a :class:`ContentProvider` (RDR-051)."""

    candidate_id: str
    opportunity_id: str
    task: str
    brand: Brand
    channel: Channel
    marketplace: str
    product: AIReviewProductFacts
    offer: AIReviewOfferFacts
    evaluation: AIReviewEvaluationFacts
    knowledge: KnowledgeContext
    allowed_claims: tuple[Mapping[str, Any], ...] = ()
    omitted_claims: tuple[Mapping[str, Any], ...] = ()
    forbidden_claims: tuple[str, ...] = ()
    warnings: tuple[ContentWarning, ...] = ()

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": CONTENT_SCHEMA_VERSION,
            "task": self.task,
            "candidate_id": self.candidate_id,
            "opportunity_id": self.opportunity_id,
            "brand": self.brand.value,
            "channel": self.channel.value,
            "marketplace": self.marketplace,
            "product": self.product.to_contract(),
            "offer": self.offer.to_contract(),
            "evaluation": self.evaluation.to_contract(),
            "knowledge": self.knowledge.to_contract(),
            "allowed_claims": [dict(claim) for claim in self.allowed_claims],
            "omitted_claims": [dict(claim) for claim in self.omitted_claims],
            "forbidden_claims": list(self.forbidden_claims),
            "warnings": [warning.to_contract() for warning in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class ContentGeneration:
    """Versioned, auditable preview generated for one Opportunity (RDR-019).

    ``generated`` (AI copy) and ``rendered`` (final content with backend
    price/link/disclosure) are stored separately with their own versions
    (AUT-034, AUT-081). ``facts`` is the hashable snapshot of the facts the copy
    depends on, so a later change makes the content ``STALE`` on read.
    """

    content_generation_id: str
    opportunity_id: str
    candidate_id: str
    brand: Brand
    channel: Channel
    generation_version: str
    knowledge_version: str
    knowledge_hash: str
    prompt_version: str
    renderer_version: str
    generated: GeneratedContent
    rendered: RenderedContent
    guards: tuple[str, ...]
    warnings: tuple[ContentWarning, ...]
    facts: Mapping[str, Any]
    fact_hash: str
    correlation_id: str
    audit_event_id: str
    created_at: datetime
    ai_input_hash: str
    status: ContentGenerationStatus = ContentGenerationStatus.VALIDATED
    schema_version: str = CONTENT_SCHEMA_VERSION

    def to_contract(self, *, stale: bool = False) -> dict[str, Any]:
        effective_status = ContentGenerationStatus.STALE if stale else self.status
        return {
            "schema_version": self.schema_version,
            "status": effective_status.value,
            "content_generation_id": self.content_generation_id,
            "opportunity_id": self.opportunity_id,
            "candidate_id": self.candidate_id,
            "brand": self.brand.value,
            "channel": self.channel.value,
            "generation_version": self.generation_version,
            "knowledge_version": self.knowledge_version,
            "knowledge_hash": self.knowledge_hash,
            "prompt_version": self.prompt_version,
            "renderer_version": self.renderer_version,
            "generated_content": self.generated.to_contract(),
            "final_content": self.rendered.to_contract(),
            "guards": list(self.guards),
            "warnings": [warning.to_contract() for warning in self.warnings],
            "publishable": effective_status is ContentGenerationStatus.VALIDATED,
            "stale": stale,
            "fact_hash": self.fact_hash,
            "facts": dict(self.facts),
            "ai_input_hash": self.ai_input_hash,
            "correlation_id": self.correlation_id,
            "audit_event_id": self.audit_event_id,
            "created_at": _to_utc(self.created_at).isoformat(),
        }


@dataclass(frozen=True, slots=True)
class ContentGenerationResolution:
    """Outcome of resolving a Content Generation request (RDR-055).

    ``cache_hit`` is ``True`` when an equivalent, still-valid persisted
    generation was reused instead of calling the provider again; the ``record``
    is always the versioned, validated :class:`ContentGeneration`.
    """

    record: ContentGeneration
    cache_hit: bool

    def to_contract(self, *, stale: bool = False) -> dict[str, Any]:
        payload = self.record.to_contract(stale=stale)
        payload["cache_hit"] = self.cache_hit
        return payload


@runtime_checkable
class ContentProvider(Protocol):
    """Contract every Content Generation provider (Fake first) must satisfy.

    The provider isolates the external call and returns a raw structured mapping
    that the domain validates before anything is persisted; the real provider
    remains gated by SPIKE-01/RDR-048 and is not implemented here.
    """

    @property
    def name(self) -> str: ...

    def generate_content(self, request: ContentGenerationInput) -> Mapping[str, Any]: ...


def _warning_from_mapping(item: Mapping[str, Any]) -> ContentWarning:
    code = sanitize_ai_text(item.get("code"), max_length=64) or "CONTENT_WARNING"
    message = sanitize_ai_text(item.get("message"), max_length=512) or code
    raw_context = item.get("context")
    context = dict(raw_context) if isinstance(raw_context, Mapping) else {}
    return ContentWarning(code=code, message=message, context=context)


def parse_generate_content_response(raw: object, *, provider: str) -> GeneratedContent:
    """Validate the provider response, failing closed on any contract breach.

    A non-mapping response, a sensitive/unknown field, a missing/oversized text or
    a URL introduced by the AI is rejected with a structured error; the returned
    content is sanitized (no HTML, no control characters) and remains inert data.
    """

    if not isinstance(raw, Mapping):
        raise content_invalid_response_error(
            "resposta do provider deve ser um objeto", provider=provider
        )
    sensitive = find_sensitive_fields(raw)
    if sensitive:
        raise content_policy_violation_error(provider=provider, context={"fields": list(sensitive)})
    unknown = sorted({str(key) for key in raw} - _ALLOWED_RESPONSE_FIELDS)
    if unknown:
        raise content_invalid_response_error(
            "resposta do provider contém campos desconhecidos",
            provider=provider,
            context={"fields": unknown},
        )

    fields: dict[str, str] = {}
    for name in ("headline", "body", "cta"):
        value = raw.get(name)
        if not isinstance(value, str):
            raise content_invalid_response_error(
                f"resposta do provider sem {name} de texto", provider=provider
            )
        if len(value) > MAX_CONTENT_FIELD_LENGTH:
            raise content_invalid_response_error(
                f"{name} do provider excede o tamanho máximo",
                provider=provider,
                context={"field": name, "max_length": MAX_CONTENT_FIELD_LENGTH},
            )
        if _URL_PATTERN.search(value):
            raise content_url_not_allowed_error(field_name=name, provider=provider)
        cleaned = sanitize_ai_text(value, max_length=MAX_CONTENT_FIELD_LENGTH)
        if cleaned is None:
            raise content_invalid_response_error(f"{name} do provider vazio", provider=provider)
        fields[name] = cleaned

    raw_warnings = raw.get("warnings") or ()
    if isinstance(raw_warnings, (str, bytes)) or not isinstance(raw_warnings, Sequence):
        raise content_invalid_response_error(
            "warnings do provider deve ser uma lista", provider=provider
        )
    warnings = tuple(
        _warning_from_mapping(item) for item in raw_warnings if isinstance(item, Mapping)
    )
    return GeneratedContent(
        headline=fields["headline"],
        body=fields["body"],
        cta=fields["cta"],
        warnings=warnings,
    )


def _numeric_claim_values(claims: AllowedClaimsResult) -> tuple[set[Decimal], set[str]]:
    values: set[Decimal] = set()
    digits: set[str] = set()
    for claim in claims.claims:
        if claim.unit not in (ClaimUnit.MONEY, ClaimUnit.PERCENT, ClaimUnit.COUNT):
            # A confirmed coupon code is not a commercial number, but its digits
            # may appear in the copy; allow them without treating the code as a
            # numeric claim.
            if claim.unit is ClaimUnit.COUPON:
                digits.add(_digits(claim.value))
            continue
        value = _numeric_value(claim.value)
        if value is not None:
            values.add(value)
        digits.add(_digits(claim.value))
    return values, digits


def numeric_guard(
    generated: GeneratedContent, *, claims: AllowedClaimsResult
) -> tuple[ContentGuardError, ...]:
    """Block any commercial number not sustained by backend Evidence (RDR-052)."""

    supported, supported_digits = _numeric_claim_values(claims)
    errors: list[ContentGuardError] = []
    for field_name in ("headline", "body", "cta"):
        text = getattr(generated, field_name)
        for token in _extract_numbers(text):
            value = _numeric_value(token)
            if value is not None and value in supported:
                continue
            if _digits(token) in supported_digits:
                continue
            errors.append(
                ContentGuardError(
                    code=UNSUPPORTED_NUMERIC_CLAIM,
                    guard="numeric",
                    message="Número comercial sem Evidence",
                    field_name=field_name,
                    context={"number": token},
                )
            )
    return tuple(errors)


def claim_guard(
    generated: GeneratedContent, *, claims: AllowedClaimsResult
) -> tuple[ContentGuardError, ...]:
    """Block forbidden claims or claims the backend does not sustain (RDR-053)."""

    claim_types = {claim.claim_type.value for claim in claims.claims}
    haystack = _normalize_for_match(f"{generated.headline} {generated.body} {generated.cta}")
    errors: list[ContentGuardError] = []
    for claim_code, phrases in FORBIDDEN_EXPRESSIONS.items():
        if claim_code == "UNVERIFIED_COUPON" and "CONFIRMED_COUPON" in claim_types:
            continue
        for phrase in phrases:
            if _contains_phrase(haystack, phrase):
                errors.append(
                    ContentGuardError(
                        code=UNSUPPORTED_CLAIM,
                        guard="claim",
                        message="Claim proibido ou não sustentado",
                        context={"claim_code": claim_code, "expression": phrase},
                    )
                )
                break
    return tuple(errors)


def channel_guard(
    generated: GeneratedContent, *, channel: Channel
) -> tuple[ContentGuardError, ...]:
    """Apply the channel content rules (RDR-054)."""

    limit = CHANNEL_MESSAGE_LIMITS.get(channel)
    if limit is None:
        return (
            ContentGuardError(
                code=CONTENT_CHANNEL_INVALID,
                guard="channel",
                message="Canal sem regra de conteúdo aprovada",
                context={"channel": channel.value},
            ),
        )
    total = len(generated.headline) + len(generated.body) + len(generated.cta)
    if total > limit:
        return (
            ContentGuardError(
                code=CONTENT_CHANNEL_INVALID,
                guard="channel",
                message="Conteúdo excede o limite do canal",
                context={"channel": channel.value, "length": total, "limit": limit},
            ),
        )
    return ()


def compliance_guard(
    policy: ChannelCompliancePolicy, *, now: datetime
) -> tuple[tuple[ContentGuardError, ...], tuple[ContentWarning, ...]]:
    """Apply the compliance guard, failing closed only on an explicit block.

    A preview is not an external side effect: ``UNKNOWN``/``REVIEW_REQUIRED`` keeps
    the preview available (SHADOW previews) but emits an explicit warning, while
    an explicit ``BLOCKED`` policy refuses the preview (AUT-295, fail closed).
    """

    if policy.status is ComplianceStatus.BLOCKED:
        return (
            (
                ContentGuardError(
                    code=CONTENT_COMPLIANCE_BLOCKED,
                    guard="compliance",
                    message="Policy de compliance BLOCKED",
                    context={"policy_version": policy.policy_version},
                ),
            ),
            (),
        )
    if policy.status is not ComplianceStatus.ACTIVE:
        warning = ContentWarning(
            code=WARNING_COMPLIANCE_NOT_ACTIVE,
            message=(
                "Policy de compliance não ACTIVE; a preview é permitida, "
                "mas o envio comercial continua bloqueado pelo gate de publicação"
            ),
            context={
                "status": policy.status.value,
                "policy_version": policy.policy_version,
            },
        )
        return (), (warning,)
    return (), ()


def validate_generated_content(
    *,
    generated: GeneratedContent,
    claims: AllowedClaimsResult,
    channel: Channel,
    compliance_policy: ChannelCompliancePolicy,
    now: datetime,
) -> ContentValidation:
    """Run the deterministic local guards that precede usable content (AUT-082)."""

    guards: list[str] = ["numeric", "claim", "channel", "compliance"]
    errors: list[ContentGuardError] = []
    errors.extend(numeric_guard(generated, claims=claims))
    errors.extend(claim_guard(generated, claims=claims))
    errors.extend(channel_guard(generated, channel=channel))
    compliance_errors, warnings = compliance_guard(compliance_policy, now=now)
    errors.extend(compliance_errors)
    return ContentValidation(
        guards=tuple(guards),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def raise_for_validation(validation: ContentValidation, *, channel: Channel) -> None:
    """Raise the structured error of the first guard that refused the content."""

    if validation.passed:
        return
    first = validation.errors[0]
    context = {
        "errors": [error.to_contract() for error in validation.errors],
        "guard_engine_version": CONTENT_GUARD_ENGINE_VERSION,
    }
    if first.guard == "numeric":
        raise unsupported_numeric_claim_error(
            field_name=first.field_name or "content", context=context
        )
    if first.guard == "claim":
        raise unsupported_claim_error(
            claim_code=str(first.context.get("claim_code", "UNSUPPORTED_CLAIM")),
            context=context,
        )
    if first.guard == "channel":
        raise content_channel_invalid_error(channel=channel.value, context=context)
    raise content_compliance_blocked_error(context=context)


def render_content(
    *,
    generated: GeneratedContent,
    price: object,
    affiliate_url: str,
    tracking: Mapping[str, Any],
    disclosure: str = DISCLOSURE_TEXT,
) -> RenderedContent:
    """Insert backend price/link/disclosure deterministically (RDR-069).

    The renderer reads only the validated link literal and the backend-sustained
    price; it never accepts a URL from the AI and never edits the link.
    """

    if _URL_PATTERN.search(generated.headline + generated.body + generated.cta):
        raise content_url_not_allowed_error(field_name="content", provider="renderer")
    if not affiliate_url:
        raise content_input_invalid_error("Renderer exige AffiliateLink validado")
    canonical_price = canonical_money(price)
    price_display = _format_price(canonical_price)
    blocks = (
        disclosure,
        generated.headline,
        generated.body,
        f"Preço: R$ {price_display}",
        generated.cta,
        affiliate_url,
    )
    return RenderedContent(
        headline=generated.headline,
        body=generated.body,
        cta=generated.cta,
        price=canonical_price,
        price_display=price_display,
        affiliate_url=affiliate_url,
        disclosure=disclosure,
        tracking=dict(tracking),
        blocks=blocks,
        text="\n".join(blocks),
    )


def build_content_generation_input(
    *,
    candidate_id: str,
    opportunity_id: str,
    marketplace: str,
    product: AIReviewProductFacts,
    offer: AIReviewOfferFacts,
    evaluation: AIReviewEvaluationFacts,
    knowledge: KnowledgeContext,
    allowed_claims: Sequence[Mapping[str, Any]] = (),
    omitted_claims: Sequence[Mapping[str, Any]] = (),
    forbidden_claims: Sequence[str] = (),
) -> ContentGenerationInput:
    """Build the sanitized provider input and refuse unsafe content."""

    sanitized_product = AIReviewProductFacts(
        external_id=sanitize_ai_text(product.external_id, max_length=128) or "",
        title=sanitize_ai_text(product.title),
        category=sanitize_ai_text(product.category),
        url=sanitize_ai_text(product.url, max_length=2048),
    )
    sanitized_offer = AIReviewOfferFacts(
        current_price=sanitize_ai_text(offer.current_price, max_length=64) or "",
        original_price=sanitize_ai_text(offer.original_price),
        sales_count=offer.sales_count,
        seller_name=sanitize_ai_text(offer.seller_name),
    )
    warnings: list[ContentWarning] = []
    if knowledge.warning_code is not None:
        warnings.append(
            ContentWarning(
                code=knowledge.warning_code,
                message=(
                    "Knowledge Pack sem contexto aprovado para brand/canal; a geração "
                    "segue sem guidance inventada"
                ),
                context={"brand": knowledge.brand.value, "channel": knowledge.channel.value},
            )
        )
    request = ContentGenerationInput(
        candidate_id=sanitize_ai_text(candidate_id, max_length=64) or "",
        opportunity_id=sanitize_ai_text(opportunity_id, max_length=64) or "",
        task=GENERATE_CONTENT_TASK,
        brand=knowledge.brand,
        channel=knowledge.channel,
        marketplace=sanitize_ai_text(marketplace, max_length=32) or "",
        product=sanitized_product,
        offer=sanitized_offer,
        evaluation=evaluation,
        knowledge=knowledge,
        allowed_claims=tuple(dict(claim) for claim in allowed_claims),
        omitted_claims=tuple(dict(claim) for claim in omitted_claims),
        forbidden_claims=tuple(str(claim) for claim in forbidden_claims),
        warnings=tuple(warnings),
    )
    sensitive = find_sensitive_fields(request.to_contract())
    if sensitive:
        raise content_policy_violation_error(provider="radar", context={"fields": list(sensitive)})
    return request


def canonical_ai_input_hash(request: ContentGenerationInput) -> str:
    """Hash the versioned provider input canonically (RDR-055).

    The hash covers the exact sanitized input handed to the provider — product,
    offer, Evaluation scores, backend-sustained claims, warnings and
    Knowledge/Prompt versions — so an equivalent input reuses the persisted result
    while any relevant change invalidates it (``docs/06_AI_ENGINE.md`` Cache).
    """

    canonical = json.dumps(
        request.to_contract(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def canonical_fact_hash(facts: Mapping[str, Any]) -> str:
    """Hash a fact snapshot canonically so staleness is deterministic."""

    canonical = json.dumps(dict(facts), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_content_generation(
    *,
    request: ContentGenerationInput,
    generated: GeneratedContent,
    rendered: RenderedContent,
    validation: ContentValidation,
    facts: Mapping[str, Any],
    correlation_id: object,
    audit_event_id: object,
    created_at: datetime,
    content_generation_id: object | None = None,
    generation_version: str = CONTENT_GENERATION_ENGINE_VERSION,
    schema_version: object = CONTENT_SCHEMA_VERSION,
    id_factory: IdFactory = default_id_factory,
) -> ContentGeneration:
    """Assemble the ContentGeneration from validated content and a fact snapshot."""

    if str(schema_version) != CONTENT_SCHEMA_VERSION:
        raise content_input_invalid_error(
            "schema_version de ContentGeneration não suportada",
            context={"supported": CONTENT_SCHEMA_VERSION},
        )
    if not validation.passed:
        raise content_input_invalid_error(
            "ContentGeneration exige validação aprovada",
            context={"errors": [error.to_contract() for error in validation.errors]},
        )
    resolved_id = (
        str(id_factory("ctg"))
        if content_generation_id is None
        else str(content_generation_id).strip()
    )
    return ContentGeneration(
        content_generation_id=resolved_id,
        opportunity_id=request.opportunity_id,
        candidate_id=request.candidate_id,
        brand=request.brand,
        channel=request.channel,
        generation_version=generation_version,
        knowledge_version=request.knowledge.knowledge_version,
        knowledge_hash=request.knowledge.knowledge_hash,
        prompt_version=request.knowledge.prompt_version,
        renderer_version=rendered.renderer_version,
        generated=generated,
        rendered=rendered,
        guards=validation.guards,
        warnings=request.warnings + validation.warnings,
        facts=dict(facts),
        fact_hash=canonical_fact_hash(facts),
        correlation_id=str(correlation_id).strip(),
        audit_event_id=str(audit_event_id).strip(),
        created_at=_to_utc(created_at),
        ai_input_hash=canonical_ai_input_hash(request),
    )


def current_price_claim_value(claims: AllowedClaimsResult) -> str | None:
    """Return the backend-sustained ``CURRENT_PRICE`` value or ``None``."""

    for claim in claims.claims:
        if claim.claim_type.value == "CURRENT_PRICE":
            return claim.value
    return None


def is_stale(record: ContentGeneration, *, current_facts: Mapping[str, Any]) -> bool:
    """Return True when the relevant facts changed after generation (SDD-08)."""

    return canonical_fact_hash(current_facts) != record.fact_hash


__all__ = [
    "AUDIT_SOURCE_CONTENT",
    "CHANNEL_MESSAGE_LIMITS",
    "CONTENT_CHANNEL_INVALID",
    "CONTENT_COMPLIANCE_BLOCKED",
    "CONTENT_GENERATION_ENGINE_VERSION",
    "CONTENT_GENERATION_NOT_FOUND",
    "CONTENT_GUARD_ENGINE_VERSION",
    "CONTENT_INPUT_INVALID",
    "CONTENT_RENDERER_VERSION",
    "CONTENT_SCHEMA_VERSION",
    "CONTENT_URL_NOT_ALLOWED",
    "DISCLOSURE_TEXT",
    "ENTITY_CONTENT_GENERATION",
    "FORBIDDEN_CLAIMS",
    "FORBIDDEN_EXPRESSIONS",
    "GENERATE_CONTENT_TASK",
    "MAX_CONTENT_FIELD_LENGTH",
    "UNSUPPORTED_CLAIM",
    "UNSUPPORTED_NUMERIC_CLAIM",
    "WARNING_COMPLIANCE_NOT_ACTIVE",
    "ContentGeneration",
    "ContentGenerationError",
    "ContentGenerationInput",
    "ContentGenerationResolution",
    "ContentGenerationStatus",
    "ContentGuardError",
    "ContentProvider",
    "ContentValidation",
    "ContentWarning",
    "GeneratedContent",
    "RenderedContent",
    "build_content_generation",
    "build_content_generation_input",
    "canonical_ai_input_hash",
    "canonical_fact_hash",
    "canonical_money",
    "channel_guard",
    "claim_guard",
    "compliance_guard",
    "content_channel_invalid_error",
    "content_compliance_blocked_error",
    "content_generation_not_found_error",
    "content_input_invalid_error",
    "content_invalid_response_error",
    "content_policy_violation_error",
    "content_url_not_allowed_error",
    "current_price_claim_value",
    "is_stale",
    "numeric_guard",
    "parse_generate_content_response",
    "raise_for_validation",
    "render_content",
    "unsupported_claim_error",
    "unsupported_numeric_claim_error",
    "validate_generated_content",
]
