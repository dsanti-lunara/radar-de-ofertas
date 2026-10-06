"""Opportunity entity and explicit state machine (RDR-017).

An :class:`Opportunity` only exists after a Candidate was **approved** (AUT-032):
it represents the accepted offer that moves through link/content/publication. This
module implements the framework-free core of ``docs/03_DOMAIN_MODEL.md``:

* the approved states of an Opportunity (``READY``, ``LINK_PENDING``,
  ``LINK_READY``, ``CONTENT_PENDING``, ``READY_TO_PUBLISH``, ``PUBLISHED``,
  ``EXPIRED``, ``CANCELLED``);
* the **allowed transitions** between those states, so the Workflow Engine (not a
  worker, AUT-119/AUT-120) can reject an invalid transition with a structured
  error that the caller audits;
* the versioned public contract returned by the boundary.

No AI, HTTP, SQLAlchemy or browser code lives here (AUT-397); persistence and the
atomic transition/audit write live in infrastructure. Creating the next Job is the
Workflow Engine's job, not this entity's.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from radar.domain.capture import IdFactory, default_id_factory
from radar.domain.errors import RadarError, RadarException
from radar.domain.taxonomy import Brand

#: Version of the public Opportunity contract (``docs/04_DATA_CONTRACTS.md``).
OPPORTUNITY_SCHEMA_VERSION = "1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
OPPORTUNITY_NOT_FOUND = "RAD-WF-014"
OPPORTUNITY_TRANSITION_INVALID = "RAD-WF-015"
OPPORTUNITY_INPUT_INVALID = "RAD-WF-016"

#: Entity type recorded on the Opportunity audit events.
ENTITY_OPPORTUNITY = "opportunity"

#: Provenance source recorded on the Opportunity audit events.
AUDIT_SOURCE_OPPORTUNITY = "workflow"


class OpportunityState(StrEnum):
    """Opportunity states of ``docs/03_DOMAIN_MODEL.md``.

    ``READY`` is the state right after an approved Candidate becomes an
    Opportunity. ``PUBLISHED``, ``EXPIRED`` and ``CANCELLED`` are terminal (only a
    published offer may still expire, AUT-173).
    """

    READY = "READY"
    LINK_PENDING = "LINK_PENDING"
    LINK_READY = "LINK_READY"
    CONTENT_PENDING = "CONTENT_PENDING"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISHED = "PUBLISHED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


#: States from which no further transition is allowed.
TERMINAL_OPPORTUNITY_STATES: frozenset[OpportunityState] = frozenset(
    {OpportunityState.EXPIRED, OpportunityState.CANCELLED}
)

#: Allowed transitions of the Opportunity state machine (SDD-08 pipeline).
ALLOWED_OPPORTUNITY_TRANSITIONS: Mapping[OpportunityState, frozenset[OpportunityState]] = {
    OpportunityState.READY: frozenset(
        {
            OpportunityState.LINK_PENDING,
            OpportunityState.EXPIRED,
            OpportunityState.CANCELLED,
        }
    ),
    OpportunityState.LINK_PENDING: frozenset(
        {
            OpportunityState.LINK_READY,
            OpportunityState.EXPIRED,
            OpportunityState.CANCELLED,
        }
    ),
    OpportunityState.LINK_READY: frozenset(
        {
            OpportunityState.CONTENT_PENDING,
            OpportunityState.EXPIRED,
            OpportunityState.CANCELLED,
        }
    ),
    OpportunityState.CONTENT_PENDING: frozenset(
        {
            OpportunityState.READY_TO_PUBLISH,
            OpportunityState.EXPIRED,
            OpportunityState.CANCELLED,
        }
    ),
    OpportunityState.READY_TO_PUBLISH: frozenset(
        {
            OpportunityState.PUBLISHED,
            OpportunityState.EXPIRED,
            OpportunityState.CANCELLED,
        }
    ),
    OpportunityState.PUBLISHED: frozenset({OpportunityState.EXPIRED}),
    OpportunityState.EXPIRED: frozenset(),
    OpportunityState.CANCELLED: frozenset(),
}


class OpportunityError(RadarException):
    """Base error raised when an Opportunity operation cannot be completed."""


def opportunity_not_found_error(opportunity_id: str) -> OpportunityError:
    """Build the structured not-found error for an Opportunity query."""

    return OpportunityError(
        RadarError(
            code=OPPORTUNITY_NOT_FOUND,
            message="Opportunity não encontrada",
            retryable=False,
            action="Verificar o opportunity_id informado",
            context={"opportunity_id": opportunity_id},
        )
    )


def opportunity_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> OpportunityError:
    """Build the structured error for an invalid Opportunity input."""

    return OpportunityError(
        RadarError(
            code=OPPORTUNITY_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o input da Opportunity e enviar novamente",
            context=dict(context or {}),
        )
    )


def opportunity_transition_invalid_error(
    opportunity_id: str,
    *,
    current: OpportunityState,
    target: OpportunityState,
    allowed: frozenset[OpportunityState] | None = None,
) -> OpportunityError:
    """Build the structured error for a transition the state machine rejects.

    The error is deterministic and carries the current state plus the allowed
    targets, so the caller can audit *why* the transition was refused.
    """

    allowed_states = allowed if allowed is not None else ALLOWED_OPPORTUNITY_TRANSITIONS[current]
    return OpportunityError(
        RadarError(
            code=OPPORTUNITY_TRANSITION_INVALID,
            message="Transição de Opportunity inválida",
            retryable=False,
            action="Consultar o estado atual e usar apenas uma transição permitida",
            context={
                "opportunity_id": opportunity_id,
                "current_state": current.value,
                "target_state": target.value,
                "allowed_states": sorted(state.value for state in allowed_states),
            },
        )
    )


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _require_clean_id(value: object, *, field_name: str, max_length: int = 64) -> str:
    if not isinstance(value, str):
        raise opportunity_input_invalid_error("valor deve ser texto", context={"field": field_name})
    cleaned = value.strip()
    if not cleaned:
        raise opportunity_input_invalid_error(
            "valor não pode ser vazio", context={"field": field_name}
        )
    if len(cleaned) > max_length:
        raise opportunity_input_invalid_error(
            "valor excede o tamanho máximo",
            context={"field": field_name, "max_length": max_length},
        )
    return cleaned


def coerce_opportunity_state(value: object) -> OpportunityState:
    """Coerce a public value into a known Opportunity state, failing closed."""

    if isinstance(value, OpportunityState):
        return value
    try:
        return OpportunityState(str(value))
    except ValueError as exc:
        raise opportunity_input_invalid_error(
            "target_state de Opportunity inválido",
            context={
                "field": "target_state",
                "allowed": [state.value for state in OpportunityState],
            },
        ) from exc


@dataclass(frozen=True, slots=True)
class Opportunity:
    """An approved offer that moves through the Opportunity pipeline (RDR-017)."""

    opportunity_id: str
    candidate_id: str
    evaluation_id: str
    brand: Brand
    state: OpportunityState
    priority: int
    correlation_id: str
    audit_event_id: str
    created_at: datetime
    updated_at: datetime
    schema_version: str = OPPORTUNITY_SCHEMA_VERSION

    def allowed_transitions(self) -> frozenset[OpportunityState]:
        """Return the states this Opportunity may transition to."""

        return ALLOWED_OPPORTUNITY_TRANSITIONS[self.state]

    def to_contract(self) -> dict[str, Any]:
        """Return the versioned public contract for this Opportunity."""

        return {
            "schema_version": self.schema_version,
            "status": self.state.value,
            "opportunity_id": self.opportunity_id,
            "candidate_id": self.candidate_id,
            "evaluation_id": self.evaluation_id,
            "brand": self.brand.value,
            "priority": self.priority,
            "state": self.state.value,
            "allowed_transitions": sorted(
                state.value for state in ALLOWED_OPPORTUNITY_TRANSITIONS[self.state]
            ),
            "correlation_id": self.correlation_id,
            "audit_event_id": self.audit_event_id,
            "created_at": _to_utc(self.created_at).isoformat(),
            "updated_at": _to_utc(self.updated_at).isoformat(),
        }


def create_opportunity(
    *,
    candidate_id: object,
    evaluation_id: object,
    brand: Brand,
    correlation_id: object,
    now: datetime,
    audit_event_id: object,
    priority: object = 0,
    opportunity_id: object | None = None,
    schema_version: object = OPPORTUNITY_SCHEMA_VERSION,
    id_factory: IdFactory = default_id_factory,
) -> Opportunity:
    """Build a ``READY`` Opportunity for an approved Candidate (AUT-032).

    The caller (the Workflow Engine) is responsible for the approval gate: this
    function only validates the concrete fields and starts the state machine in
    ``READY``. An unsupported ``schema_version``, an unknown ``brand`` or a
    non-integer priority fails closed with ``RAD-WF-016``.
    """

    if str(schema_version) != OPPORTUNITY_SCHEMA_VERSION:
        raise opportunity_input_invalid_error(
            "schema_version de Opportunity não suportada",
            context={"field": "schema_version", "supported": OPPORTUNITY_SCHEMA_VERSION},
        )
    if not isinstance(brand, Brand):
        raise opportunity_input_invalid_error(
            "brand inválida para a Opportunity",
            context={"field": "brand", "allowed": [item.value for item in Brand]},
        )
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise opportunity_input_invalid_error(
            "priority deve ser um inteiro", context={"field": "priority"}
        )
    reference = _to_utc(now)
    return Opportunity(
        opportunity_id=(
            id_factory("opp")
            if opportunity_id is None
            else _require_clean_id(opportunity_id, field_name="opportunity_id")
        ),
        candidate_id=_require_clean_id(candidate_id, field_name="candidate_id"),
        evaluation_id=_require_clean_id(evaluation_id, field_name="evaluation_id"),
        brand=brand,
        state=OpportunityState.READY,
        priority=priority,
        correlation_id=_require_clean_id(correlation_id, field_name="correlation_id"),
        audit_event_id=_require_clean_id(audit_event_id, field_name="audit_event_id"),
        created_at=reference,
        updated_at=reference,
    )


def transition_opportunity(
    opportunity: Opportunity, *, target: OpportunityState | str, now: datetime
) -> Opportunity:
    """Return the Opportunity transitioned to ``target`` or fail closed.

    Only transitions declared in :data:`ALLOWED_OPPORTUNITY_TRANSITIONS` are
    accepted; a no-op (``target == current``) and any unknown/terminal transition
    raise ``RAD-WF-015`` so an invalid transition is never persisted silently.
    """

    resolved_target = coerce_opportunity_state(target)
    allowed = ALLOWED_OPPORTUNITY_TRANSITIONS[opportunity.state]
    if resolved_target is opportunity.state or resolved_target not in allowed:
        raise opportunity_transition_invalid_error(
            opportunity.opportunity_id,
            current=opportunity.state,
            target=resolved_target,
            allowed=allowed,
        )
    return replace(opportunity, state=resolved_target, updated_at=_to_utc(now))


__all__ = [
    "ALLOWED_OPPORTUNITY_TRANSITIONS",
    "AUDIT_SOURCE_OPPORTUNITY",
    "ENTITY_OPPORTUNITY",
    "OPPORTUNITY_INPUT_INVALID",
    "OPPORTUNITY_NOT_FOUND",
    "OPPORTUNITY_SCHEMA_VERSION",
    "OPPORTUNITY_TRANSITION_INVALID",
    "TERMINAL_OPPORTUNITY_STATES",
    "Opportunity",
    "OpportunityError",
    "OpportunityState",
    "coerce_opportunity_state",
    "create_opportunity",
    "opportunity_input_invalid_error",
    "opportunity_not_found_error",
    "opportunity_transition_invalid_error",
    "transition_opportunity",
]
