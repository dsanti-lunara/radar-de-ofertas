"""SQLAlchemy persistence for operational controls (RDR-043, RDR-044).

The global operational state and each integration health are upserted in the
**same transaction** as their audit event, so an operator command is never
partially recorded and the decision trail is always consistent with the state
that gated a side effect (AUT-010, AUT-141, AUT-263, AUT-264).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.domain.audit import AuditEvent
from radar.domain.operations import (
    OPERATIONS_SCHEMA_VERSION,
    GlobalMode,
    IntegrationHealth,
    IntegrationState,
    OperationalState,
)
from radar.infrastructure.models import (
    AuditEventRow,
    IntegrationHealthRow,
    OperationsStateRow,
)

#: Primary key of the single global operational-state row.
GLOBAL_STATE_ID = "global"


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _parse(moment: str) -> datetime:
    return datetime.fromisoformat(moment)


def _audit_event_to_row(event: AuditEvent) -> AuditEventRow:
    return AuditEventRow(
        id=event.id,
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        source=event.source,
        correlation_id=event.correlation_id,
        payload=json.dumps(dict(event.payload), ensure_ascii=False, sort_keys=True),
        recorded_at=_iso(event.recorded_at),
    )


@dataclass(slots=True)
class SqlAlchemyOperationsRepository:
    """Persist the operational state and integration health on SQLite."""

    engine: Engine

    # -- Operational state --------------------------------------------------

    def get_state(self) -> OperationalState | None:
        """Return the global operational state or ``None`` when not yet set."""

        with Session(self.engine) as session:
            row = session.get(OperationsStateRow, GLOBAL_STATE_ID)
            if row is None:
                return None
            return OperationalState(
                global_mode=GlobalMode(row.global_mode),
                stop_external_actions=bool(row.stop_external_actions),
                reason=row.reason,
                updated_at=_parse(row.updated_at),
            )

    def save_state(
        self, state: OperationalState, audit_events: tuple[AuditEvent, ...]
    ) -> OperationalState:
        """Upsert the global state and append its audit events atomically."""

        updated_at = state.updated_at or datetime.now(UTC)
        with Session(self.engine) as session, session.begin():
            for event in audit_events:
                session.add(_audit_event_to_row(event))
            session.flush()
            row = session.get(OperationsStateRow, GLOBAL_STATE_ID)
            if row is None:
                row = OperationsStateRow(
                    id=GLOBAL_STATE_ID,
                    global_mode=state.global_mode.value,
                    stop_external_actions=state.stop_external_actions,
                    reason=state.reason,
                    correlation_id=(audit_events[-1].correlation_id if audit_events else None),
                    schema_version=OPERATIONS_SCHEMA_VERSION,
                    updated_at=_iso(updated_at),
                )
                session.add(row)
            else:
                row.global_mode = state.global_mode.value
                row.stop_external_actions = state.stop_external_actions
                row.reason = state.reason
                row.correlation_id = (
                    audit_events[-1].correlation_id if audit_events else row.correlation_id
                )
                row.updated_at = _iso(updated_at)
        return OperationalState(
            global_mode=state.global_mode,
            stop_external_actions=state.stop_external_actions,
            reason=state.reason,
            updated_at=updated_at,
        )

    # -- Integration health -------------------------------------------------

    def list_integrations(self) -> list[IntegrationHealth]:
        """Return integration health, ordered by name."""

        with Session(self.engine) as session:
            rows = (
                session.execute(select(IntegrationHealthRow).order_by(IntegrationHealthRow.name))
                .scalars()
                .all()
            )
        return [_integration_from_row(row) for row in rows]

    def get_integration(self, name: str) -> IntegrationHealth | None:
        """Return one integration health or ``None`` when not registered."""

        with Session(self.engine) as session:
            row = session.get(IntegrationHealthRow, name)
            return None if row is None else _integration_from_row(row)

    def save_integration(
        self, health: IntegrationHealth, audit_events: tuple[AuditEvent, ...]
    ) -> IntegrationHealth:
        """Upsert one integration health and append its audit events atomically."""

        updated_at = health.updated_at or datetime.now(UTC)
        with Session(self.engine) as session, session.begin():
            for event in audit_events:
                session.add(_audit_event_to_row(event))
            session.flush()
            row = session.get(IntegrationHealthRow, health.name)
            if row is None:
                row = IntegrationHealthRow(
                    name=health.name,
                    state=health.state.value,
                    summary=health.summary,
                    correlation_id=(audit_events[-1].correlation_id if audit_events else None),
                    schema_version=OPERATIONS_SCHEMA_VERSION,
                    updated_at=_iso(updated_at),
                )
                session.add(row)
            else:
                row.state = health.state.value
                row.summary = health.summary
                row.correlation_id = (
                    audit_events[-1].correlation_id if audit_events else row.correlation_id
                )
                row.updated_at = _iso(updated_at)
        return IntegrationHealth(
            name=health.name,
            state=health.state,
            summary=health.summary,
            updated_at=updated_at,
        )

    # -- Audit --------------------------------------------------------------

    def record_audit(self, audit_events: tuple[AuditEvent, ...]) -> None:
        """Append audit events without mutating the operational state."""

        if not audit_events:
            return
        with Session(self.engine) as session, session.begin():
            for event in audit_events:
                session.add(_audit_event_to_row(event))


def _integration_from_row(row: IntegrationHealthRow) -> IntegrationHealth:
    return IntegrationHealth(
        name=row.name,
        state=IntegrationState(row.state),
        summary=row.summary,
        updated_at=_parse(row.updated_at),
    )


__all__ = [
    "GLOBAL_STATE_ID",
    "SqlAlchemyOperationsRepository",
]
