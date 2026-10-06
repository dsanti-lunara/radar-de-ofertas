"""Formal human-intervention records (RDR-040, AUT-126, AUT-244).

Every situation that cannot be resolved automatically and needs an operator
converges on a :class:`HumanAction` (``docs/03_DOMAIN_MODEL.md``). The record is
framework-free (no FastAPI/SQLAlchemy/Chrome) and explains *why* intervention is
needed, its impact and the next steps, so the operator can act without reading
SQL. It is persisted and auditable, and it references the existing entity
(``entity_type``/``entity_id``) instead of recreating it.

This ticket creates the ``HumanAction`` produced by the retry/Dead Job flow
(RDR-037/RDR-038). Resolving/mutating actions belongs to the Human Actions
center ticket (RDR-063); the record already carries the resolution lifecycle so
the dependent ticket can evolve it without a contract rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from radar.domain.capture import (
    IdFactory,
    default_id_factory,
    sanitize_single_line,
)
from radar.domain.errors import RadarError, RadarException

#: Version of the public HumanAction contract (``docs/04_DATA_CONTRACTS.md``).
HUMAN_ACTION_SCHEMA_VERSION = "1.0"

#: Error code for a HumanAction query that found no record.
HUMAN_ACTION_NOT_FOUND = "RAD-WF-011"

#: Error code for resolving a HumanAction whose intervention is delegated to
#: another guarded flow (RDR-063). Resolving it here could bypass evidence.
HUMAN_ACTION_RESOLUTION_NOT_AVAILABLE = "RAD-WF-020"

#: Provenance source recorded on HumanAction audit events.
AUDIT_SOURCE_HUMAN_ACTION = "human_action"

#: Maximum length of the free-form action fields.
MAX_HUMAN_ACTION_TEXT_LENGTH = 512


class HumanActionType(StrEnum):
    """Intervention kinds defined by ``docs/03_DOMAIN_MODEL.md`` (AUT-126)."""

    AUTHENTICATE_MARKETPLACE = "AUTHENTICATE_MARKETPLACE"
    REVIEW_CANDIDATE = "REVIEW_CANDIDATE"
    REVIEW_PUBLICATION = "REVIEW_PUBLICATION"
    RESOLVE_DATA_CONFLICT = "RESOLVE_DATA_CONFLICT"
    BROWSER_DOM_CHANGED = "BROWSER_DOM_CHANGED"
    RESTORE_AI_AUTH = "RESTORE_AI_AUTH"
    BACKUP_FAILURE = "BACKUP_FAILURE"
    DEAD_JOB_REVIEW = "DEAD_JOB_REVIEW"


class HumanActionStatus(StrEnum):
    """Lifecycle of a HumanAction.

    This ticket only creates ``OPEN`` actions; the transition to ``RESOLVED``
    belongs to the Human Actions center (RDR-063), which consumes this model.
    """

    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class HumanActionResolutionMode(StrEnum):
    """How one intervention can actually be closed (RDR-063, AUT-244).

    ``OPERATOR_ACK`` is the Human Actions center's own action: the operator
    performed the intervention and records the resolution. The delegated modes
    belong to a guarded flow (Candidate review, Publication resolution with
    evidence) and must **not** be closed from here, so the center can never
    bypass an evidence/authorization gate (AUT-263, ADR 0001).
    """

    OPERATOR_ACK = "OPERATOR_ACK"
    CANDIDATE_REVIEW = "CANDIDATE_REVIEW"
    PUBLICATION_RESOLUTION = "PUBLICATION_RESOLUTION"


@dataclass(frozen=True, slots=True)
class HumanActionResolution:
    """Observable resolution guidance for one HumanAction kind (RDR-063)."""

    mode: HumanActionResolutionMode
    resolvable_via_center: bool
    delegated_to: str | None
    guidance: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "resolvable_via_center": self.resolvable_via_center,
            "delegated_to": self.delegated_to,
            "guidance": self.guidance,
        }


#: Deterministic resolution guidance per intervention kind. Delegated flows are
#: never executable from the Human Actions center (acceptance #5).
_RESOLUTION_GUIDANCE: dict[HumanActionType, HumanActionResolution] = {
    HumanActionType.AUTHENTICATE_MARKETPLACE: HumanActionResolution(
        mode=HumanActionResolutionMode.OPERATOR_ACK,
        resolvable_via_center=True,
        delegated_to=None,
        guidance="Autenticar no fluxo oficial do marketplace e registrar a resolução.",
    ),
    HumanActionType.REVIEW_CANDIDATE: HumanActionResolution(
        mode=HumanActionResolutionMode.CANDIDATE_REVIEW,
        resolvable_via_center=False,
        delegated_to="review",
        guidance="Resolver pela revisão do Candidate em Oportunidades, com motivo.",
    ),
    HumanActionType.REVIEW_PUBLICATION: HumanActionResolution(
        mode=HumanActionResolutionMode.PUBLICATION_RESOLUTION,
        resolvable_via_center=False,
        delegated_to="publications",
        guidance=(
            "Resolver pela resolução da publicação, que exige evidência; "
            "uma autorização sem corroboração não prova o resultado (ADR 0001)."
        ),
    ),
    HumanActionType.RESOLVE_DATA_CONFLICT: HumanActionResolution(
        mode=HumanActionResolutionMode.OPERATOR_ACK,
        resolvable_via_center=True,
        delegated_to=None,
        guidance="Escolher o fato correto pela proveniência e registrar a resolução.",
    ),
    HumanActionType.BROWSER_DOM_CHANGED: HumanActionResolution(
        mode=HumanActionResolutionMode.OPERATOR_ACK,
        resolvable_via_center=True,
        delegated_to=None,
        guidance=(
            "Atualizar fixtures/selectors via Browser Reconnaissance e registrar a resolução."
        ),
    ),
    HumanActionType.RESTORE_AI_AUTH: HumanActionResolution(
        mode=HumanActionResolutionMode.OPERATOR_ACK,
        resolvable_via_center=True,
        delegated_to=None,
        guidance="Restaurar a autenticação do provider de IA e registrar a resolução.",
    ),
    HumanActionType.BACKUP_FAILURE: HumanActionResolution(
        mode=HumanActionResolutionMode.OPERATOR_ACK,
        resolvable_via_center=True,
        delegated_to=None,
        guidance="Corrigir disco/permissões, executar o backup e registrar a resolução.",
    ),
    HumanActionType.DEAD_JOB_REVIEW: HumanActionResolution(
        mode=HumanActionResolutionMode.OPERATOR_ACK,
        resolvable_via_center=True,
        delegated_to=None,
        guidance="Corrigir a causa, reprocessar o job e registrar a resolução.",
    ),
}


def human_action_resolution_for(action_type: HumanActionType) -> HumanActionResolution:
    """Return the resolution guidance for one intervention kind."""

    return _RESOLUTION_GUIDANCE[action_type]


class HumanActionError(RadarException):
    """Base error raised when a HumanAction operation cannot be completed."""


def human_action_not_found_error(human_action_id: str) -> HumanActionError:
    """Build the structured not-found error for a HumanAction query."""

    return HumanActionError(
        RadarError(
            code=HUMAN_ACTION_NOT_FOUND,
            message="HumanAction não encontrada",
            retryable=False,
            action="Verificar o human_action_id informado",
            context={"human_action_id": human_action_id},
        )
    )


def human_action_resolution_not_available_error(
    human_action_id: str, resolution: HumanActionResolution
) -> HumanActionError:
    """Build the structured error for a delegated/guarded intervention."""

    return HumanActionError(
        RadarError(
            code=HUMAN_ACTION_RESOLUTION_NOT_AVAILABLE,
            message="Resolução desta HumanAction pertence a outro fluxo guardado",
            retryable=False,
            action=resolution.guidance,
            context={
                "human_action_id": human_action_id,
                "mode": resolution.mode.value,
                "delegated_to": resolution.delegated_to,
            },
        )
    )


#: Deterministic operator guidance per intervention kind: (impact, next steps).
_ACTION_GUIDANCE: dict[HumanActionType, tuple[str, str]] = {
    HumanActionType.AUTHENTICATE_MARKETPLACE: (
        "A integração do marketplace exige sessão/concessão válida e os jobs "
        "afetados ficam parados até a autenticação.",
        "Autenticar no marketplace pelo fluxo oficial e reprocessar os jobs parados.",
    ),
    HumanActionType.REVIEW_CANDIDATE: (
        "Um Candidate precisa de decisão humana antes de continuar o pipeline.",
        "Revisar o Candidate com score breakdown e Evidence e registrar a decisão.",
    ),
    HumanActionType.REVIEW_PUBLICATION: (
        "Uma publicação precisa de revisão humana antes de qualquer envio.",
        "Revisar a publicação, a evidência disponível e autorizar ou bloquear o envio.",
    ),
    HumanActionType.RESOLVE_DATA_CONFLICT: (
        "Dois fatos conflitantes impedem uma decisão automática confiável.",
        "Comparar a proveniência das evidências e escolher o fato correto.",
    ),
    HumanActionType.BROWSER_DOM_CHANGED: (
        "O DOM de uma superfície monitorada mudou e a capability foi isolada.",
        "Executar Browser Reconnaissance, atualizar fixtures/selectors e revalidar a capability.",
    ),
    HumanActionType.RESTORE_AI_AUTH: (
        "O provider de IA está sem autenticação e o pipeline de conteúdo fica parado.",
        "Restaurar a autenticação do provider de IA e retomar os jobs afetados.",
    ),
    HumanActionType.BACKUP_FAILURE: (
        "O backup falhou ou está atrasado, reduzindo a recuperabilidade do nó.",
        "Verificar disco/permissões, executar o backup e confirmar a integridade.",
    ),
    HumanActionType.DEAD_JOB_REVIEW: (
        "Um job não pode mais ser processado automaticamente e entrou na Dead Job Queue.",
        "Revisar a falha e a evidência, corrigir a causa e decidir como reprocessar.",
    ),
}


@dataclass(frozen=True, slots=True)
class HumanAction:
    """An auditable record of one required human intervention."""

    id: str
    action_type: HumanActionType
    status: HumanActionStatus
    entity_type: str
    entity_id: str
    reason: str
    error_code: str
    impact: str
    next_steps: str
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    schema_version: str = HUMAN_ACTION_SCHEMA_VERSION

    def to_contract(self) -> dict[str, Any]:
        """Return the versioned public contract for this HumanAction."""

        return {
            "schema_version": self.schema_version,
            "human_action_id": self.id,
            "action_type": self.action_type.value,
            "status": self.status.value,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "reason": self.reason,
            "error_code": self.error_code,
            "impact": self.impact,
            "next_steps": self.next_steps,
            "resolution": human_action_resolution_for(self.action_type).to_contract(),
            "correlation_id": self.correlation_id,
            "created_at": _to_utc(self.created_at).isoformat(),
            "updated_at": _to_utc(self.updated_at).isoformat(),
        }


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _require_clean_text(value: object, *, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise _input_invalid("valor deve ser texto", field=field_name)
    cleaned = sanitize_single_line(value)
    if not cleaned:
        raise _input_invalid("valor não pode ser vazio", field=field_name)
    if len(cleaned) > max_length:
        raise _input_invalid("valor excede o tamanho máximo", field=field_name)
    return cleaned


def _input_invalid(message: str, *, field: str) -> HumanActionError:
    return HumanActionError(
        RadarError(
            code="RAD-WF-006",
            message=message,
            retryable=False,
            action="Corrigir o input da HumanAction e enviar novamente",
            context={"field": field},
        )
    )


def _coerce_action_type(value: object) -> HumanActionType:
    if isinstance(value, HumanActionType):
        return value
    try:
        return HumanActionType(str(value))
    except ValueError as exc:
        raise _input_invalid("action_type inválido", field="action_type") from exc


def build_human_action(
    *,
    action_type: object,
    entity_type: object,
    entity_id: object,
    reason: object,
    error_code: object,
    correlation_id: object,
    now: datetime,
    status: HumanActionStatus = HumanActionStatus.OPEN,
    id_factory: IdFactory = default_id_factory,
    impact: object = None,
    next_steps: object = None,
) -> HumanAction:
    """Build and validate a ``HumanAction`` (AUT-126, AUT-244).

    The guidance (impact/next steps) is deterministic for the action type, so an
    operator always receives actionable context and no marketplace/worker text
    is interpreted as an instruction (AUT-275). A caller may pass explicit
    ``impact``/``next_steps`` when the intervention requires a more specific
    explanation (e.g. the evidence required to resolve an unknown send result);
    the values are still sanitized to a single line.
    """

    resolved_type = _coerce_action_type(action_type)
    resolved_entity_type = _require_clean_text(entity_type, field_name="entity_type", max_length=32)
    resolved_entity_id = _require_clean_text(entity_id, field_name="entity_id", max_length=64)
    resolved_reason = _require_clean_text(reason, field_name="reason", max_length=48)
    resolved_code = _require_clean_text(error_code, field_name="error_code", max_length=64)
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise _input_invalid("correlation_id é obrigatório", field="correlation_id")
    reference = _to_utc(now)
    default_impact, default_next_steps = _ACTION_GUIDANCE[resolved_type]
    resolved_impact = (
        default_impact
        if impact is None
        else _require_clean_text(
            impact, field_name="impact", max_length=MAX_HUMAN_ACTION_TEXT_LENGTH
        )
    )
    resolved_next_steps = (
        default_next_steps
        if next_steps is None
        else _require_clean_text(
            next_steps, field_name="next_steps", max_length=MAX_HUMAN_ACTION_TEXT_LENGTH
        )
    )
    return HumanAction(
        id=id_factory("ha"),
        action_type=resolved_type,
        status=status,
        entity_type=resolved_entity_type,
        entity_id=resolved_entity_id,
        reason=resolved_reason,
        error_code=resolved_code,
        impact=resolved_impact,
        next_steps=resolved_next_steps,
        correlation_id=correlation_id.strip(),
        created_at=reference,
        updated_at=reference,
    )


def resolve_human_action(action: HumanAction, *, reason: object, now: datetime) -> HumanAction:
    """Resolve an ``OPERATOR_ACK`` intervention, recording the operator reason.

    Resolution is auditable bookkeeping: it performs no external side effect. A
    delegated/guarded intervention (Candidate review, Publication resolution)
    and an already-resolved action fail closed: the former raises
    ``RAD-WF-020`` because closing it here would bypass evidence/authorization,
    the latter is a no-op so retries stay idempotent (RDR-063, AUT-263).
    """

    if action.status is HumanActionStatus.RESOLVED:
        return action
    resolution = human_action_resolution_for(action.action_type)
    if not resolution.resolvable_via_center:
        raise human_action_resolution_not_available_error(action.id, resolution)
    _require_clean_text(reason, field_name="reason", max_length=MAX_HUMAN_ACTION_TEXT_LENGTH)
    return replace(action, status=HumanActionStatus.RESOLVED, updated_at=_to_utc(now))


__all__ = [
    "AUDIT_SOURCE_HUMAN_ACTION",
    "HUMAN_ACTION_NOT_FOUND",
    "HUMAN_ACTION_RESOLUTION_NOT_AVAILABLE",
    "HUMAN_ACTION_SCHEMA_VERSION",
    "MAX_HUMAN_ACTION_TEXT_LENGTH",
    "HumanAction",
    "HumanActionError",
    "HumanActionResolution",
    "HumanActionResolutionMode",
    "HumanActionStatus",
    "HumanActionType",
    "build_human_action",
    "human_action_not_found_error",
    "human_action_resolution_for",
    "human_action_resolution_not_available_error",
    "resolve_human_action",
]
