"""SQLAlchemy persistence for HumanAction records (RDR-040, AUT-126, AUT-244).

The retry/Dead Job flow creates a HumanAction in the **same transaction** that
transitions the job, so the intervention is never partially recorded. This
module exposes the shared row mapping used by that transaction plus a read-only
repository for the public boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.domain.audit import HUMAN_ACTION_RESOLVED
from radar.domain.capture import IdFactory, default_id_factory
from radar.domain.human_action import (
    AUDIT_SOURCE_HUMAN_ACTION,
    HUMAN_ACTION_SCHEMA_VERSION,
    HumanAction,
    HumanActionStatus,
    HumanActionType,
)
from radar.infrastructure.models import AuditEventRow, HumanActionRow


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _parse(moment: str) -> datetime:
    return datetime.fromisoformat(moment)


def human_action_to_row(action: HumanAction) -> HumanActionRow:
    """Map a domain HumanAction to its persistence row (shared by the job flow)."""

    return HumanActionRow(
        id=action.id,
        action_type=action.action_type.value,
        status=action.status.value,
        entity_type=action.entity_type,
        entity_id=action.entity_id,
        reason=action.reason,
        error_code=action.error_code,
        impact=action.impact,
        next_steps=action.next_steps,
        correlation_id=action.correlation_id,
        schema_version=action.schema_version,
        created_at=_iso(action.created_at),
        updated_at=_iso(action.updated_at),
    )


def human_action_from_row(row: HumanActionRow) -> HumanAction:
    """Map a persistence row back to the domain HumanAction."""

    return HumanAction(
        id=row.id,
        action_type=HumanActionType(row.action_type),
        status=HumanActionStatus(row.status),
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        reason=row.reason,
        error_code=row.error_code,
        impact=row.impact,
        next_steps=row.next_steps,
        correlation_id=row.correlation_id,
        created_at=_parse(row.created_at),
        updated_at=_parse(row.updated_at),
        schema_version=row.schema_version or HUMAN_ACTION_SCHEMA_VERSION,
    )


@dataclass(slots=True)
class SqlAlchemyHumanActionRepository:
    """Read HumanAction records and resolve the operator-acknowledged kinds."""

    engine: Engine
    id_factory: IdFactory = default_id_factory

    def get(self, human_action_id: str) -> HumanAction | None:
        """Return a HumanAction by id or ``None`` when it does not exist."""

        with Session(self.engine) as session:
            row = session.get(HumanActionRow, human_action_id)
            return None if row is None else human_action_from_row(row)

    def list(self, *, status: str | None = None) -> list[HumanAction]:
        """Return HumanActions, optionally filtered by status, oldest first."""

        statement = select(HumanActionRow).order_by(
            HumanActionRow.created_at.asc(), HumanActionRow.id.asc()
        )
        if status is not None:
            statement = statement.where(HumanActionRow.status == status)
        with Session(self.engine) as session:
            rows = session.execute(statement).scalars().all()
        return [human_action_from_row(row) for row in rows]

    def resolve(
        self,
        human_action_id: str,
        *,
        now: datetime,
        correlation_id: str,
    ) -> tuple[HumanAction, bool] | None:
        """Resolve one HumanAction and audit it atomically (RDR-063).

        Returns ``(action, changed)`` or ``None`` when the action does not
        exist. An already-``RESOLVED`` action is returned unchanged with
        ``changed=False`` so the boundary stays idempotent; the row update and
        the ``HUMAN_ACTION_RESOLVED`` audit event share one transaction, so a
        resolution is never partially recorded (AUT-263).
        """

        now_iso = _iso(now)
        with Session(self.engine) as session, session.begin():
            row = session.get(HumanActionRow, human_action_id)
            if row is None:
                return None
            if HumanActionStatus(row.status) is HumanActionStatus.RESOLVED:
                return human_action_from_row(row), False
            row.status = HumanActionStatus.RESOLVED.value
            row.updated_at = now_iso
            session.add(
                AuditEventRow(
                    id=str(self.id_factory("aud")),
                    event_type=HUMAN_ACTION_RESOLVED,
                    entity_type="human_action",
                    entity_id=human_action_id,
                    source=AUDIT_SOURCE_HUMAN_ACTION,
                    correlation_id=correlation_id,
                    payload=json.dumps(
                        {"status": HumanActionStatus.RESOLVED.value},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    recorded_at=now_iso,
                )
            )
            return human_action_from_row(row), True


__all__ = [
    "SqlAlchemyHumanActionRepository",
    "human_action_from_row",
    "human_action_to_row",
]
