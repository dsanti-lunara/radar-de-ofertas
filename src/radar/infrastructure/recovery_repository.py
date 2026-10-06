"""SQLAlchemy persistence for startup recovery (RDR-042, AUT-229).

Every reconciliation write is atomic with its audit event: the runtime-state
upsert, the interrupted-job requeue/block and the orphan-lock clear each happen
in **one transaction** together with the ``AuditEvent`` that explains them, so a
crash can never leave the queue reconciled without its trail (AUT-010, AUT-141).

The conditional ``UPDATE``s on the job reconcile a job only while it still holds
the observed interrupted status, so two concurrent recoveries (or a recovery
racing a worker) can never overwrite each other. The Recovery Manager is
framework-free in the domain; this module only provides the persistence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.domain.audit import AuditEvent
from radar.domain.capture import IdFactory, default_id_factory
from radar.domain.job import Job, Lock
from radar.domain.recovery import (
    RECOVERY_SCHEMA_VERSION,
    RuntimeState,
    block_job,
    requeue_job,
)
from radar.infrastructure.job_repository import _job_from_row, _lock_from_row
from radar.infrastructure.models import AuditEventRow, JobLockRow, JobRow, RuntimeStateRow

#: Primary key of the single runtime-state row.
CORE_STATE_ID = "core"


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
class SqlAlchemyRecoveryRepository:
    """Persist the runtime shutdown marker and reconcile interrupted work."""

    engine: Engine
    id_factory: IdFactory = default_id_factory

    # -- Runtime state ------------------------------------------------------

    def get_runtime_state(self) -> RuntimeState | None:
        """Return the durable runtime state or ``None`` when never recorded."""

        with Session(self.engine) as session:
            row = session.get(RuntimeStateRow, CORE_STATE_ID)
            return None if row is None else _runtime_from_row(row)

    def save_runtime_state(
        self, state: RuntimeState, audit_events: tuple[AuditEvent, ...]
    ) -> RuntimeState:
        """Upsert the runtime state and append its audit events atomically."""

        updated_at = state.updated_at or datetime.now(UTC)
        with Session(self.engine) as session, session.begin():
            for event in audit_events:
                session.add(_audit_event_to_row(event))
            session.flush()
            row = session.get(RuntimeStateRow, CORE_STATE_ID)
            if row is None:
                row = RuntimeStateRow(
                    id=CORE_STATE_ID,
                    clean_shutdown=state.clean_shutdown,
                    started_at=None if state.started_at is None else _iso(state.started_at),
                    shutdown_at=None if state.shutdown_at is None else _iso(state.shutdown_at),
                    last_recovery_at=(
                        None if state.last_recovery_at is None else _iso(state.last_recovery_at)
                    ),
                    recovery_count=state.recovery_count,
                    schema_version=RECOVERY_SCHEMA_VERSION,
                    updated_at=_iso(updated_at),
                )
                session.add(row)
            else:
                row.clean_shutdown = state.clean_shutdown
                row.started_at = None if state.started_at is None else _iso(state.started_at)
                row.shutdown_at = None if state.shutdown_at is None else _iso(state.shutdown_at)
                row.last_recovery_at = (
                    None if state.last_recovery_at is None else _iso(state.last_recovery_at)
                )
                row.recovery_count = state.recovery_count
                row.updated_at = _iso(updated_at)
        return RuntimeState(
            clean_shutdown=state.clean_shutdown,
            recovery_count=state.recovery_count,
            started_at=state.started_at,
            shutdown_at=state.shutdown_at,
            last_recovery_at=state.last_recovery_at,
            updated_at=updated_at,
        )

    # -- Interrupted jobs ---------------------------------------------------

    def list_interrupted_jobs(self) -> list[Job]:
        """Return the ``CLAIMED``/``RUNNING`` jobs, oldest first."""

        statement = (
            select(JobRow)
            .where(JobRow.status.in_(("CLAIMED", "RUNNING")))
            .order_by(JobRow.created_at.asc(), JobRow.id.asc())
        )
        with Session(self.engine) as session:
            rows = session.execute(statement).scalars().all()
        return [_job_from_row(row) for row in rows]

    def requeue_job(
        self, job: Job, *, now: datetime, audit_events: tuple[AuditEvent, ...]
    ) -> Job | None:
        """Return an interrupted job to ``PENDING`` while it still matches.

        Returns ``None`` when the job changed since it was read, so a concurrent
        recovery/worker is never overwritten.
        """

        target = requeue_job(job, now=now)
        with Session(self.engine) as session, session.begin():
            updated_id = session.execute(
                update(JobRow)
                .where(JobRow.id == job.id, JobRow.status == job.status.value)
                .values(
                    status=target.status.value,
                    available_at=_iso(target.available_at),
                    locked_by=None,
                    locked_at=None,
                    lease_expires_at=None,
                    updated_at=_iso(target.updated_at),
                )
                .returning(JobRow.id)
            ).scalar_one_or_none()
            if updated_id is None:
                return None
            for event in audit_events:
                session.add(_audit_event_to_row(event))
        return target

    def block_job(
        self, job: Job, *, now: datetime, audit_events: tuple[AuditEvent, ...]
    ) -> Job | None:
        """Block an interrupted job (``DEAD``) while it still matches.

        Returns ``None`` when the job changed since it was read.
        """

        target = block_job(job, now=now)
        with Session(self.engine) as session, session.begin():
            updated_id = session.execute(
                update(JobRow)
                .where(JobRow.id == job.id, JobRow.status == job.status.value)
                .values(
                    status=target.status.value,
                    locked_by=None,
                    locked_at=None,
                    lease_expires_at=None,
                    updated_at=_iso(target.updated_at),
                )
                .returning(JobRow.id)
            ).scalar_one_or_none()
            if updated_id is None:
                return None
            for event in audit_events:
                session.add(_audit_event_to_row(event))
        return target

    # -- Orphan locks -------------------------------------------------------

    def list_locks(self) -> list[Lock]:
        """Return every logical lock, active or expired."""

        with Session(self.engine) as session:
            rows = session.execute(select(JobLockRow).order_by(JobLockRow.name)).scalars().all()
        return [_lock_from_row(row) for row in rows]

    def clear_lock(self, lock: Lock, *, audit_events: tuple[AuditEvent, ...]) -> bool:
        """Delete an orphan lock owned by ``lock.owner`` and audit it atomically.

        Returns ``False`` when the lock changed owner since it was read, so a
        concurrent owner is never released.
        """

        with Session(self.engine) as session, session.begin():
            row = session.get(JobLockRow, lock.name)
            if row is None or row.owner != lock.owner:
                return False
            session.delete(row)
            for event in audit_events:
                session.add(_audit_event_to_row(event))
        return True

    # -- Audit --------------------------------------------------------------

    def record_audit(self, audit_events: tuple[AuditEvent, ...]) -> None:
        """Append audit events without mutating the runtime state."""

        if not audit_events:
            return
        with Session(self.engine) as session, session.begin():
            for event in audit_events:
                session.add(_audit_event_to_row(event))


def _runtime_from_row(row: RuntimeStateRow) -> RuntimeState:
    return RuntimeState(
        clean_shutdown=bool(row.clean_shutdown),
        recovery_count=row.recovery_count,
        started_at=None if row.started_at is None else _parse(row.started_at),
        shutdown_at=None if row.shutdown_at is None else _parse(row.shutdown_at),
        last_recovery_at=None if row.last_recovery_at is None else _parse(row.last_recovery_at),
        schema_version=row.schema_version,
        updated_at=None if row.updated_at is None else _parse(row.updated_at),
    )


__all__ = [
    "CORE_STATE_ID",
    "SqlAlchemyRecoveryRepository",
]
