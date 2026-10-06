"""Operational controls orchestration: modes, kill switch and authorization.

The service drives the framework-free domain of
:mod:`radar.domain.operations` against a persistence port. It implements the
objective of TKT-17 (RDR-043, RDR-044):

* the global mode (``RUNNING``/``PAUSED``/``DRAINING``/``MAINTENANCE``) and the
  ``STOP_EXTERNAL_ACTIONS`` kill switch are persisted and audited, so the
  operator command is observable from the public boundary (AUT-149, AUT-317);
* :meth:`OperationsService.authorize` is the single gate that resolves the
  automation mode for a brand/marketplace/channel/capability slice, checks
  the blocking compliance policy and the integration health, and returns an
  allow/block decision with a Correlation ID (AUT-127, AUT-293, GRILL-001);
* integration health updates are persisted per integration so one unhealthy
  integration isolates its own scope (AUT-315).

The service is framework-free (no FastAPI/SQLAlchemy/Chrome) and never calls AI
or creates an affiliate link (AUT-397, AUT-031).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from radar.domain.audit import (
    EXTERNAL_ACTION_AUTHORIZED,
    EXTERNAL_ACTION_BLOCKED,
    EXTERNAL_ACTIONS_RESUMED,
    EXTERNAL_ACTIONS_STOPPED,
    INTEGRATION_HEALTH_CHANGED,
    OPERATIONS_MODE_CHANGED,
    AuditEvent,
)
from radar.domain.capture import IdFactory, default_id_factory
from radar.domain.operations import (
    APPROVED_AUTOMATION_POLICY,
    APPROVED_COMPLIANCE_POLICY,
    DEFAULT_OPERATIONAL_STATE,
    EXTERNAL_ACTIONS,
    MAX_OPERATIONS_TEXT_LENGTH,
    AutomationPolicy,
    ChannelCompliancePolicy,
    ExternalActionDecision,
    ExternalActionRequest,
    GlobalMode,
    IntegrationHealth,
    IntegrationState,
    OperationalState,
    decide_external_action,
    operations_input_invalid_error,
)

#: Entity id used for the single global operational state row.
ENTITY_OPERATIONS = "operations"
GLOBAL_STATE_ID = "global"

#: Provenance source recorded on operations audit events.
AUDIT_SOURCE_OPERATIONS = "operations"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OperationsStore(Protocol):
    """Persistence port for operational state and integration health."""

    def get_state(self) -> OperationalState | None: ...

    def save_state(
        self, state: OperationalState, audit_events: tuple[AuditEvent, ...]
    ) -> OperationalState: ...

    def list_integrations(self) -> list[IntegrationHealth]: ...

    def get_integration(self, name: str) -> IntegrationHealth | None: ...

    def save_integration(
        self, health: IntegrationHealth, audit_events: tuple[AuditEvent, ...]
    ) -> IntegrationHealth: ...

    def record_audit(self, audit_events: tuple[AuditEvent, ...]) -> None: ...


@dataclass(slots=True)
class OperationsService:
    """Drive global modes, the kill switch and the external-action gate."""

    store: OperationsStore
    automation_policy: AutomationPolicy = APPROVED_AUTOMATION_POLICY
    compliance_policy: ChannelCompliancePolicy = APPROVED_COMPLIANCE_POLICY
    clock: Callable[[], datetime] = _utcnow
    id_factory: IdFactory = default_id_factory

    def state(self) -> OperationalState:
        """Return the persisted operational state or the approved default."""

        return self.store.get_state() or DEFAULT_OPERATIONAL_STATE

    def set_global_mode(
        self,
        mode: object,
        *,
        reason: object = None,
        correlation_id: str,
    ) -> OperationalState:
        """Persist and audit a new global mode (AUT-149)."""

        resolved_mode = _coerce_mode(mode)
        resolved_reason = _clean_optional_text(reason, field_name="reason")
        now = self.clock()
        current = self.state()
        state = OperationalState(
            global_mode=resolved_mode,
            stop_external_actions=current.stop_external_actions,
            reason=resolved_reason,
            updated_at=now,
        )
        audit = self._audit_event(
            event_type=OPERATIONS_MODE_CHANGED,
            entity_type=ENTITY_OPERATIONS,
            entity_id=GLOBAL_STATE_ID,
            correlation_id=correlation_id,
            now=now,
            payload={
                "previous_mode": current.global_mode.value,
                "global_mode": state.global_mode.value,
                "reason": resolved_reason,
            },
        )
        return self.store.save_state(state, (audit,))

    def engage_stop(self, *, reason: object = None, correlation_id: str) -> OperationalState:
        """Engage ``STOP_EXTERNAL_ACTIONS`` while keeping safe work available."""

        return self._set_stop(True, reason=reason, correlation_id=correlation_id)

    def release_stop(self, *, reason: object = None, correlation_id: str) -> OperationalState:
        """Release ``STOP_EXTERNAL_ACTIONS``; policies still gate side effects."""

        return self._set_stop(False, reason=reason, correlation_id=correlation_id)

    def authorize(
        self, request: ExternalActionRequest, *, correlation_id: str
    ) -> ExternalActionDecision:
        """Authorize or block one action and audit external decisions."""

        now = self.clock()
        state = self.state()
        integration_health = (
            None if request.integration is None else self.store.get_integration(request.integration)
        )
        decision = decide_external_action(
            request=request,
            operational_state=state,
            automation_policy=self.automation_policy,
            compliance_policy=self.compliance_policy,
            integration_health=integration_health,
            now=now,
            correlation_id=correlation_id,
        )
        if request.action in EXTERNAL_ACTIONS:
            audit = self._audit_event(
                event_type=(
                    EXTERNAL_ACTION_AUTHORIZED if decision.allowed else EXTERNAL_ACTION_BLOCKED
                ),
                entity_type=ENTITY_OPERATIONS,
                entity_id=GLOBAL_STATE_ID,
                correlation_id=correlation_id,
                now=now,
                payload={
                    "action": decision.action.value,
                    "allowed": decision.allowed,
                    "reason_code": decision.reason_code,
                    "automation_mode": decision.automation_mode.value,
                    "compliance_status": decision.compliance_status.value,
                    "global_mode": decision.global_mode.value,
                    "integration": decision.integration,
                },
            )
            self.store.record_audit((audit,))
        return decision

    def list_integrations(self) -> list[IntegrationHealth]:
        """Return the registered integration health, ordered by name."""

        return self.store.list_integrations()

    def set_integration_health(
        self,
        name: object,
        state: object,
        *,
        summary: object = None,
        correlation_id: str,
    ) -> IntegrationHealth:
        """Persist and audit the health of one integration (RDR-044)."""

        resolved_name = _clean_required_text(name, field_name="name", max_length=32)
        resolved_state = _coerce_integration_state(state)
        resolved_summary = _clean_optional_text(summary, field_name="summary") or (
            f"Estado {resolved_state.value}"
        )
        now = self.clock()
        health = IntegrationHealth(
            name=resolved_name,
            state=resolved_state,
            summary=resolved_summary,
            updated_at=now,
        )
        audit = self._audit_event(
            event_type=INTEGRATION_HEALTH_CHANGED,
            entity_type="integration",
            entity_id=resolved_name,
            correlation_id=correlation_id,
            now=now,
            payload={"state": resolved_state.value, "summary": resolved_summary},
        )
        return self.store.save_integration(health, (audit,))

    # -- internals ----------------------------------------------------------

    def _set_stop(self, engaged: bool, *, reason: object, correlation_id: str) -> OperationalState:
        resolved_reason = _clean_optional_text(reason, field_name="reason")
        now = self.clock()
        current = self.state()
        state = OperationalState(
            global_mode=current.global_mode,
            stop_external_actions=engaged,
            reason=resolved_reason,
            updated_at=now,
        )
        audit = self._audit_event(
            event_type=EXTERNAL_ACTIONS_STOPPED if engaged else EXTERNAL_ACTIONS_RESUMED,
            entity_type=ENTITY_OPERATIONS,
            entity_id=GLOBAL_STATE_ID,
            correlation_id=correlation_id,
            now=now,
            payload={"stop_external_actions": engaged, "reason": resolved_reason},
        )
        return self.store.save_state(state, (audit,))

    def _audit_event(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        correlation_id: str,
        now: datetime,
        payload: dict[str, Any],
    ) -> AuditEvent:
        return AuditEvent(
            id=str(self.id_factory("aud")),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            source=AUDIT_SOURCE_OPERATIONS,
            correlation_id=correlation_id,
            recorded_at=now,
            payload=payload,
        )


def _coerce_mode(value: object) -> GlobalMode:
    if isinstance(value, GlobalMode):
        return value
    try:
        return GlobalMode(str(value))
    except ValueError as exc:
        raise operations_input_invalid_error(
            "global_mode inválido",
            context={"field": "global_mode", "allowed": [item.value for item in GlobalMode]},
        ) from exc


def _coerce_integration_state(value: object) -> IntegrationState:
    if isinstance(value, IntegrationState):
        return value
    try:
        return IntegrationState(str(value))
    except ValueError as exc:
        raise operations_input_invalid_error(
            "integration state inválido",
            context={
                "field": "state",
                "allowed": [item.value for item in IntegrationState],
            },
        ) from exc


def _clean_required_text(value: object, *, field_name: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise operations_input_invalid_error("valor deve ser texto", context={"field": field_name})
    cleaned = value.strip()
    if not cleaned:
        raise operations_input_invalid_error(
            "valor não pode ser vazio", context={"field": field_name}
        )
    if len(cleaned) > max_length:
        raise operations_input_invalid_error(
            "valor excede o tamanho máximo",
            context={"field": field_name, "max_length": max_length},
        )
    return cleaned


def _clean_optional_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _clean_required_text(value, field_name=field_name, max_length=MAX_OPERATIONS_TEXT_LENGTH)


__all__ = [
    "AUDIT_SOURCE_OPERATIONS",
    "ENTITY_OPERATIONS",
    "GLOBAL_STATE_ID",
    "OperationsService",
    "OperationsStore",
]
