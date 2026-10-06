"""Editorial AI review: provider contract, structured decision and entity
(RDR-046, RDR-047, RDR-050).

This module implements the versioned *Editorial Review* of
``docs/06_AI_ENGINE.md`` (RDR-050) and the framework-free ``AIProvider`` contract
(RDR-046). The AI is an editorial component, not a scoring or compliance engine
(AUT-031, AUT-068): it receives only sanitized, structured candidate facts, the
immutable Evaluation context and the backend-sustained ``allowed_claims``
(RDR-032), and returns a structured :class:`EditorialReviewOutcome`.

Three rules are load-bearing:

* ``APPROVE`` / ``REVIEW`` / ``REJECT`` are distinct and the AI can **never**
  return ``AUTO_PUBLISH``: a blind/unknown decision is an invalid response
  (``RAD-AI-004``), and automation is an ``AutomationPolicy`` decision, not an AI
  one (AUT-059, ``docs/04_DATA_CONTRACTS.md``);
* marketplace content is untrusted, inert data (AUT-275/AUT-276): free text is
  sanitized here, raw HTML is neutralized, a sensitive field name is refused
  (``RAD-AI-007``) and money stays a decimal string (AUT-232);
* a failed/refused/invalid provider response never becomes an approval: callers
  raise a structured error before anything is persisted, so no Opportunity is
  created by blind approval.

The module is framework-free (no FastAPI/SQLAlchemy/Chrome, AUT-397), so the
domain stays independent from infrastructure and no provider is wired here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from radar.domain.capture import (
    IdFactory,
    default_id_factory,
    find_sensitive_fields,
    sanitize_single_line,
)
from radar.domain.errors import RadarError, RadarException
from radar.domain.knowledge import (
    WARNING_KNOWLEDGE_CONTEXT_NOT_CONFIGURED,
    Channel,
    KnowledgeContext,
)
from radar.domain.taxonomy import Brand

#: Version of the public AIReview contract.
AI_REVIEW_SCHEMA_VERSION = "1.0"

#: Editorial Review task name (``docs/06_AI_ENGINE.md``).
EDITORIAL_REVIEW_TASK = "EDITORIAL_REVIEW"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
AI_AUTH_REQUIRED = "RAD-AI-001"
AI_PROVIDER_UNAVAILABLE = "RAD-AI-002"
AI_USAGE_UNAVAILABLE = "RAD-AI-003"
AI_INVALID_RESPONSE = "RAD-AI-004"
AI_POLICY_VIOLATION = "RAD-AI-007"
AI_REVIEW_INPUT_INVALID = "RAD-AI-008"
AI_REVIEW_NOT_FOUND = "RAD-AI-009"
AI_REFUSAL = "RAD-AI-010"

#: Entity type recorded on the AIReview audit event.
ENTITY_AI_REVIEW = "ai_review"

#: Provenance source recorded on the AIReview audit event.
AUDIT_SOURCE_AI_REVIEW = "ai"

#: Max length of a single editorial text/reason emitted by the AI.
MAX_EDITORIAL_TEXT_LENGTH = 512
MAX_REASON_CODES = 16

_HTML_TAG = re.compile(r"<[^>]*>")


class EditorialDecision(StrEnum):
    """Editorial decisions allowed by the AI engine (``docs/06_AI_ENGINE.md``).

    ``AUTO_PUBLISH`` is deliberately absent: automation is decided by the
    AutomationPolicy, never by the AI (AUT-059).
    """

    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    REJECT = "REJECT"


class AIReviewError(RadarException):
    """Raised when an AI review cannot be produced safely."""


def ai_review_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> AIReviewError:
    """Build the structured error for invalid AIReview task input."""

    return AIReviewError(
        RadarError(
            code=AI_REVIEW_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o input do Editorial Review e enviar novamente",
            context=dict(context or {}),
        )
    )


def ai_review_not_found_error(ai_review_id: str) -> AIReviewError:
    """Build the structured not-found error for an AIReview query."""

    return AIReviewError(
        RadarError(
            code=AI_REVIEW_NOT_FOUND,
            message="AIReview não encontrada",
            retryable=False,
            action="Verificar o ai_review_id informado",
            context={"ai_review_id": ai_review_id},
        )
    )


def _provider_error(
    code: str,
    message: str,
    *,
    retryable: bool,
    action: str,
    context: Mapping[str, Any] | None = None,
) -> AIReviewError:
    return AIReviewError(
        RadarError(
            code=code,
            message=message,
            retryable=retryable,
            action=action,
            context=dict(context or {}),
        )
    )


def ai_auth_required_error(*, provider: str) -> AIReviewError:
    return _provider_error(
        AI_AUTH_REQUIRED,
        "Provider de IA exige autenticação",
        retryable=False,
        action="Restaurar a autenticação do provider de IA antes de revisar o Candidate",
        context={"provider": provider},
    )


def ai_provider_unavailable_error(*, provider: str) -> AIReviewError:
    return _provider_error(
        AI_PROVIDER_UNAVAILABLE,
        "Provider de IA indisponível",
        retryable=True,
        action="Reexecutar o Editorial Review quando o provider estiver disponível",
        context={"provider": provider},
    )


def ai_usage_unavailable_error(*, provider: str) -> AIReviewError:
    return _provider_error(
        AI_USAGE_UNAVAILABLE,
        "Capability/quota do provider de IA indisponível",
        retryable=True,
        action="Verificar quota/capability do provider e reexecutar o Editorial Review",
        context={"provider": provider},
    )


def ai_refusal_error(*, provider: str, reason: str | None = None) -> AIReviewError:
    context: dict[str, Any] = {"provider": provider}
    if reason:
        context["reason"] = sanitize_single_line(reason)
    return _provider_error(
        AI_REFUSAL,
        "Provider de IA recusou a tarefa",
        retryable=False,
        action="Revisar o contexto enviado ao provider; uma recusa nunca vira aprovação",
        context=context,
    )


def ai_invalid_response_error(
    message: str, *, provider: str | None = None, context: Mapping[str, Any] | None = None
) -> AIReviewError:
    details = dict(context or {})
    if provider:
        details["provider"] = provider
    return _provider_error(
        AI_INVALID_RESPONSE,
        message,
        retryable=False,
        action="Descartar a resposta do provider e revisar o contexto do Editorial Review",
        context=details,
    )


def ai_policy_violation_error(
    *, provider: str, context: Mapping[str, Any] | None = None
) -> AIReviewError:
    return _provider_error(
        AI_POLICY_VIOLATION,
        "Resposta do provider violou o contrato (campo sensível ou conteúdo não confiável)",
        retryable=False,
        action="Descartar a resposta e revisar o provider/contexto do Editorial Review",
        context={"provider": provider, **dict(context or {})},
    )


def coerce_editorial_decision(value: object) -> EditorialDecision:
    """Coerce a raw provider decision, refusing a blind ``AUTO_PUBLISH``."""

    if isinstance(value, EditorialDecision):
        return value
    text = str(value)
    if text == "AUTO_PUBLISH":
        raise ai_invalid_response_error(
            "A IA nunca retorna AUTO_PUBLISH",
            context={"decision": text},
        )
    try:
        return EditorialDecision(text)
    except ValueError as exc:
        raise ai_invalid_response_error(
            "decision de Editorial Review inválido",
            context={
                "allowed": [item.value for item in EditorialDecision],
            },
        ) from exc


def sanitize_ai_text(value: object, *, max_length: int = MAX_EDITORIAL_TEXT_LENGTH) -> str | None:
    """Neutralize AI/marketplace free text so it stays inert data.

    Control characters and HTML tags are removed and whitespace is collapsed; a
    value that becomes empty is ``None``. The result never carries raw HTML.
    """

    if value is None:
        return None
    if not isinstance(value, str):
        raise ai_invalid_response_error("texto do provider deve ser string")
    text = sanitize_single_line(_HTML_TAG.sub("", value))
    text = text.replace("<", "").replace(">", "")
    if not text:
        return None
    if len(text) > max_length:
        text = text[:max_length].rstrip()
    return text


@dataclass(frozen=True, slots=True)
class AIReviewWarning:
    """Explicit, non-fatal warning attached to an AI review."""

    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.context:
            payload["context"] = dict(self.context)
        return payload


@dataclass(frozen=True, slots=True)
class AIReviewProductFacts:
    """Sanitized, untrusted product facts sent to the provider."""

    external_id: str
    title: str | None = None
    category: str | None = None
    url: str | None = None

    def to_contract(self) -> dict[str, Any]:
        return {
            "external_id": self.external_id,
            "title": self.title,
            "category": self.category,
            "url": self.url,
        }


@dataclass(frozen=True, slots=True)
class AIReviewOfferFacts:
    """Sanitized offer facts (money as decimal string, AUT-232)."""

    current_price: str
    original_price: str | None = None
    sales_count: int | None = None
    seller_name: str | None = None

    def to_contract(self) -> dict[str, Any]:
        return {
            "current_price": self.current_price,
            "original_price": self.original_price,
            "sales_count": self.sales_count,
            "seller_name": self.seller_name,
        }


@dataclass(frozen=True, slots=True)
class AIReviewEvaluationFacts:
    """Immutable Evaluation context the AI may reference (never recompute)."""

    evaluation_id: str
    decision: str
    deal_score: str | None = None
    monetization_score: int | None = None
    confidence: str | None = None

    def to_contract(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "decision": self.decision,
            "deal_score": self.deal_score,
            "monetization_score": self.monetization_score,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class AIReviewInput:
    """Versioned, sanitized input handed to an :class:`AIProvider` (RDR-050)."""

    candidate_id: str
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
    warnings: tuple[AIReviewWarning, ...] = ()

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": AI_REVIEW_SCHEMA_VERSION,
            "task": self.task,
            "candidate_id": self.candidate_id,
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
class EditorialReviewOutcome:
    """Validated editorial decision returned by the provider (RDR-050)."""

    decision: EditorialDecision
    editorial_angle: str | None
    reason_codes: tuple[str, ...]
    warnings: tuple[AIReviewWarning, ...]

    def to_contract(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "editorial_angle": self.editorial_angle,
            "reason_codes": list(self.reason_codes),
            "warnings": [warning.to_contract() for warning in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class AIReview:
    """Immutable, versioned editorial review of one Candidate (RDR-050).

    It records the provider/model, the knowledge and prompt versions and the
    ``allowed_claims`` snapshot it was produced from, so a later content/decision
    can always be traced back to the exact editorial context (AUT-030, AUT-065).
    """

    ai_review_id: str
    candidate_id: str
    evaluation_id: str
    task: str
    provider: str
    model: str | None
    knowledge_version: str
    knowledge_hash: str
    prompt_version: str
    decision: EditorialDecision
    editorial_angle: str | None
    reason_codes: tuple[str, ...]
    warnings: tuple[AIReviewWarning, ...]
    allowed_claims: tuple[Mapping[str, Any], ...]
    input_snapshot: Mapping[str, Any]
    correlation_id: str
    audit_event_id: str
    created_at: datetime
    schema_version: str = AI_REVIEW_SCHEMA_VERSION

    @property
    def approval_eligible(self) -> bool:
        """Only an explicit APPROVE is eligible for the approval transition."""

        return self.decision is EditorialDecision.APPROVE

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": "OK",
            "ai_review_id": self.ai_review_id,
            "candidate_id": self.candidate_id,
            "evaluation_id": self.evaluation_id,
            "task": self.task,
            "provider": self.provider,
            "model": self.model,
            "knowledge_version": self.knowledge_version,
            "knowledge_hash": self.knowledge_hash,
            "prompt_version": self.prompt_version,
            "decision": self.decision.value,
            "editorial_angle": self.editorial_angle,
            "reason_codes": list(self.reason_codes),
            "warnings": [warning.to_contract() for warning in self.warnings],
            "allowed_claims": [dict(claim) for claim in self.allowed_claims],
            "input_snapshot": dict(self.input_snapshot),
            "approval_eligible": self.approval_eligible,
            "audit_event_id": self.audit_event_id,
            "correlation_id": self.correlation_id,
            "created_at": _to_utc(self.created_at).isoformat(),
        }


@runtime_checkable
class AIProvider(Protocol):
    """Contract every AI provider (Fake first) must satisfy (RDR-046).

    The contract is deliberately narrow for the V1 Editorial Review slice:
    ``generate_content``/``review_content``/``classify_product`` arrive with their
    own tickets (RDR-051). The provider isolates authentication and the external
    call, and returns a raw structured mapping that the domain validates before
    anything is persisted.
    """

    @property
    def name(self) -> str: ...

    def evaluate_candidate(self, request: AIReviewInput) -> Mapping[str, Any]: ...


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _warning_from_mapping(item: Mapping[str, Any]) -> AIReviewWarning:
    code = sanitize_single_line(str(item.get("code", ""))) or "AI_WARNING"
    message = sanitize_single_line(str(item.get("message", ""))) or code
    raw_context = item.get("context")
    context = dict(raw_context) if isinstance(raw_context, Mapping) else {}
    return AIReviewWarning(code=code, message=message, context=context)


def parse_editorial_review_response(raw: object, *, provider: str) -> EditorialReviewOutcome:
    """Validate a raw provider response, failing closed on any contract breach.

    A non-mapping response, a missing/unknown decision, ``AUTO_PUBLISH``, a
    sensitive field or an oversized reason list is rejected with a structured
    error; no partially valid response is ever accepted as an approval.
    """

    if not isinstance(raw, Mapping):
        raise ai_invalid_response_error("resposta do provider deve ser um objeto")
    sensitive = find_sensitive_fields(raw)
    if sensitive:
        raise ai_policy_violation_error(provider=provider, context={"fields": list(sensitive)})
    if "decision" not in raw or raw.get("decision") is None:
        raise ai_invalid_response_error("resposta do provider sem decision", provider=provider)
    decision = coerce_editorial_decision(raw.get("decision"))

    raw_reasons = raw.get("reason_codes") or ()
    if isinstance(raw_reasons, (str, bytes)) or not isinstance(raw_reasons, Sequence):
        raise ai_invalid_response_error(
            "reason_codes do provider deve ser uma lista", provider=provider
        )
    if len(raw_reasons) > MAX_REASON_CODES:
        raise ai_invalid_response_error(
            "reason_codes do provider excede o limite",
            provider=provider,
            context={"max_items": MAX_REASON_CODES},
        )
    reason_codes = tuple(
        code for item in raw_reasons if (code := sanitize_ai_text(item, max_length=64)) is not None
    )

    raw_warnings = raw.get("warnings") or ()
    if isinstance(raw_warnings, (str, bytes)) or not isinstance(raw_warnings, Sequence):
        raise ai_invalid_response_error(
            "warnings do provider deve ser uma lista", provider=provider
        )
    warnings = tuple(
        _warning_from_mapping(item) for item in raw_warnings if isinstance(item, Mapping)
    )

    angle = sanitize_ai_text(raw.get("editorial_angle"))
    return EditorialReviewOutcome(
        decision=decision,
        editorial_angle=angle,
        reason_codes=reason_codes,
        warnings=warnings,
    )


def build_ai_review_input(
    *,
    candidate_id: str,
    marketplace: str,
    product: AIReviewProductFacts,
    offer: AIReviewOfferFacts,
    evaluation: AIReviewEvaluationFacts,
    knowledge: KnowledgeContext,
    allowed_claims: Sequence[Mapping[str, Any]] = (),
    omitted_claims: Sequence[Mapping[str, Any]] = (),
    forbidden_claims: Sequence[str] = (),
) -> AIReviewInput:
    """Build the sanitized provider input and refuse any unsafe content.

    Product/offer free text is neutralized (no raw HTML, no control characters),
    the input is scanned for sensitive field names and the resulting snapshot is
    an inert structured document.
    """

    sanitized_product = AIReviewProductFacts(
        external_id=sanitize_single_line(product.external_id),
        title=sanitize_ai_text(product.title),
        category=sanitize_ai_text(product.category),
        url=sanitize_ai_text(product.url, max_length=2048),
    )
    sanitized_offer = AIReviewOfferFacts(
        current_price=sanitize_single_line(offer.current_price),
        original_price=sanitize_ai_text(offer.original_price),
        sales_count=offer.sales_count,
        seller_name=sanitize_ai_text(offer.seller_name),
    )
    warnings: list[AIReviewWarning] = []
    if knowledge.warning_code == WARNING_KNOWLEDGE_CONTEXT_NOT_CONFIGURED:
        warnings.append(
            AIReviewWarning(
                code=WARNING_KNOWLEDGE_CONTEXT_NOT_CONFIGURED,
                message=(
                    "Knowledge Pack sem contexto aprovado para brand/canal; "
                    "o AIReview preserva a versão e segue sem guidance inventada"
                ),
                context={"brand": knowledge.brand.value, "channel": knowledge.channel.value},
            )
        )
    request = AIReviewInput(
        candidate_id=sanitize_single_line(candidate_id),
        task=EDITORIAL_REVIEW_TASK,
        brand=knowledge.brand,
        channel=knowledge.channel,
        marketplace=sanitize_single_line(marketplace),
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
        raise ai_policy_violation_error(provider="radar", context={"fields": list(sensitive)})
    return request


def build_ai_review(
    *,
    request: AIReviewInput,
    outcome: EditorialReviewOutcome,
    provider: str,
    model: str | None,
    correlation_id: str,
    audit_event_id: str,
    created_at: datetime,
    ai_review_id: object | None = None,
    schema_version: object = AI_REVIEW_SCHEMA_VERSION,
    id_factory: IdFactory = default_id_factory,
) -> AIReview:
    """Assemble the immutable AIReview from a validated outcome.

    Input and outcome warnings are merged so the persisted artifact explains the
    editorial decision; ``schema_version`` is validated and the identifier is
    generated from the domain id factory when absent.
    """

    if str(schema_version) != AI_REVIEW_SCHEMA_VERSION:
        raise ai_review_input_invalid_error(
            "schema_version de AIReview não suportada",
            context={"supported": AI_REVIEW_SCHEMA_VERSION},
        )
    if not outcome.reason_codes and outcome.decision is not EditorialDecision.REJECT:
        raise ai_review_input_invalid_error(
            "AIReview exige reason_codes para a decisão editorial",
            context={"decision": outcome.decision.value},
        )
    resolved_id = (
        str(id_factory("air")) if ai_review_id is None else sanitize_single_line(str(ai_review_id))
    )
    warnings = request.warnings + outcome.warnings
    return AIReview(
        ai_review_id=resolved_id,
        candidate_id=request.candidate_id,
        evaluation_id=request.evaluation.evaluation_id,
        task=request.task,
        provider=provider,
        model=model,
        knowledge_version=request.knowledge.knowledge_version,
        knowledge_hash=request.knowledge.knowledge_hash,
        prompt_version=request.knowledge.prompt_version,
        decision=outcome.decision,
        editorial_angle=outcome.editorial_angle,
        reason_codes=outcome.reason_codes,
        warnings=warnings,
        allowed_claims=request.allowed_claims,
        input_snapshot=request.to_contract(),
        correlation_id=correlation_id,
        audit_event_id=audit_event_id,
        created_at=_to_utc(created_at),
    )


__all__ = [
    "AI_AUTH_REQUIRED",
    "AI_INVALID_RESPONSE",
    "AI_POLICY_VIOLATION",
    "AI_PROVIDER_UNAVAILABLE",
    "AI_REFUSAL",
    "AI_REVIEW_INPUT_INVALID",
    "AI_REVIEW_NOT_FOUND",
    "AI_REVIEW_SCHEMA_VERSION",
    "AI_USAGE_UNAVAILABLE",
    "AUDIT_SOURCE_AI_REVIEW",
    "EDITORIAL_REVIEW_TASK",
    "ENTITY_AI_REVIEW",
    "MAX_EDITORIAL_TEXT_LENGTH",
    "MAX_REASON_CODES",
    "AIProvider",
    "AIReview",
    "AIReviewError",
    "AIReviewEvaluationFacts",
    "AIReviewInput",
    "AIReviewOfferFacts",
    "AIReviewProductFacts",
    "AIReviewWarning",
    "EditorialDecision",
    "EditorialReviewOutcome",
    "ai_auth_required_error",
    "ai_invalid_response_error",
    "ai_policy_violation_error",
    "ai_provider_unavailable_error",
    "ai_refusal_error",
    "ai_review_input_invalid_error",
    "ai_review_not_found_error",
    "ai_usage_unavailable_error",
    "build_ai_review",
    "build_ai_review_input",
    "coerce_editorial_decision",
    "parse_editorial_review_response",
    "sanitize_ai_text",
]
