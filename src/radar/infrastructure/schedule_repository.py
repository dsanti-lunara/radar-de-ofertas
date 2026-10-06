"""SQLAlchemy persistence for schedules and the atomic Scheduler tick (RDR-039).

The critical write is the tick: when a schedule is due, the Scheduler inserts the
single coalesced Job, the ``JOB_ENQUEUED``/``SCHEDULE_JOB_ENQUEUED`` audit events
and advances the ``last_tick_at`` cursor in **one transaction**, so a crash can
never leave a Job without its cursor (or the cursor without its Job). A tick
deferred by an active equivalent lock or a quiet window writes a
``SCHEDULE_TICK_SKIPPED`` audit event and does **not** advance the cursor, so the
deferred ticks coalesce into the next Job (AUT-134).

The Scheduler never executes business logic; it only inserts ``PENDING`` Jobs
(AUT-117).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.domain.audit import (
    JOB_ENQUEUED,
    SCHEDULE_CREATED,
    SCHEDULE_JOB_ENQUEUED,
    SCHEDULE_TICK_SKIPPED,
    SCHEDULE_UPDATED,
)
from radar.domain.capture import IdFactory, default_id_factory
from radar.domain.job import AUDIT_SOURCE_JOB, ENTITY_JOB, Job, JobType, Lock
from radar.domain.schedule import (
    AUDIT_SOURCE_SCHEDULER,
    ENTITY_SCHEDULE,
    QuietWindow,
    Schedule,
    ScheduleType,
    TickAction,
    TickPlan,
    apply_tick,
    schedule_input_invalid_error,
    schedule_not_found_error,
)
from radar.infrastructure.job_repository import job_to_row
from radar.infrastructure.models import AuditEventRow, JobLockRow, ScheduleRow


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _parse(moment: str) -> datetime:
    return datetime.fromisoformat(moment)


@dataclass(slots=True)
class SqlAlchemyScheduleRepository:
    """Persist schedules and apply Scheduler ticks on SQLite."""

    engine: Engine
    id_factory: IdFactory = default_id_factory

    def create(self, schedule: Schedule, *, correlation_id: str | None = None) -> Schedule:
        """Persist a new schedule and its ``SCHEDULE_CREATED`` audit event."""

        try:
            with Session(self.engine) as session, session.begin():
                session.add(_schedule_to_row(schedule))
                session.add(
                    self._audit_row(
                        entity_id=schedule.id,
                        entity_type=ENTITY_SCHEDULE,
                        event_type=SCHEDULE_CREATED,
                        correlation_id=correlation_id or schedule.id,
                        recorded_at=schedule.created_at,
                        payload={
                            "name": schedule.name,
                            "type": schedule.type.value,
                            "job_type": schedule.job_type.value,
                            "enabled": schedule.enabled,
                        },
                    )
                )
        except IntegrityError as exc:
            raise schedule_input_invalid_error(
                "Já existe um schedule com este name",
                context={"field": "name", "name": schedule.name},
            ) from exc
        return schedule

    def get(self, schedule_id: str) -> Schedule | None:
        """Return a schedule by id or ``None`` when it does not exist."""

        with Session(self.engine) as session:
            row = session.get(ScheduleRow, schedule_id)
            return None if row is None else _schedule_from_row(row)

    def get_by_name(self, name: str) -> Schedule | None:
        """Return a schedule by unique name or ``None``."""

        with Session(self.engine) as session:
            row = session.execute(
                select(ScheduleRow).where(ScheduleRow.name == name)
            ).scalar_one_or_none()
            return None if row is None else _schedule_from_row(row)

    def list(self) -> list[Schedule]:
        """Return every schedule, oldest first."""

        statement = select(ScheduleRow).order_by(ScheduleRow.created_at.asc(), ScheduleRow.id.asc())
        with Session(self.engine) as session:
            rows = session.execute(statement).scalars().all()
        return [_schedule_from_row(row) for row in rows]

    def save(self, schedule: Schedule, *, correlation_id: str | None = None) -> Schedule:
        """Persist an updated schedule (enabled flag) and audit the change."""

        with Session(self.engine) as session, session.begin():
            row = session.get(ScheduleRow, schedule.id)
            if row is None:
                raise schedule_not_found_error(schedule.id)
            row.enabled = schedule.enabled
            row.updated_at = _iso(schedule.updated_at)
            session.add(
                self._audit_row(
                    entity_id=schedule.id,
                    entity_type=ENTITY_SCHEDULE,
                    event_type=SCHEDULE_UPDATED,
                    correlation_id=correlation_id or schedule.id,
                    recorded_at=schedule.updated_at,
                    payload={"enabled": schedule.enabled},
                )
            )
        return schedule

    def get_lock(self, name: str) -> Lock | None:
        """Return the equivalent logical lock row, active or expired, or ``None``."""

        with Session(self.engine) as session:
            row = session.get(JobLockRow, name)
            return None if row is None else _lock_from_row(row)

    def apply_tick(
        self,
        schedule: Schedule,
        *,
        plan: TickPlan,
        now: datetime,
        correlation_id: str,
        job: Job | None,
    ) -> tuple[Schedule, bool]:
        """Apply one tick atomically: Job + audit + cursor, or a skip audit.

        The cursor advance is an optimistic conditional ``UPDATE`` on the
        schedule's previous ``last_tick_at``, so two concurrent ticks can never
        both enqueue a Job for the same due occurrence. The loser gets
        ``(persisted, False)`` without inserting a Job.
        """

        now_utc = now.astimezone(UTC)
        with Session(self.engine) as session, session.begin():
            row = session.get(ScheduleRow, schedule.id)
            if row is None:
                raise schedule_not_found_error(schedule.id)
            applied = True
            if plan.action is TickAction.ENQUEUE:
                if job is None:  # pragma: no cover - defensive: the service always builds one
                    raise schedule_input_invalid_error(
                        "Tick de enqueue sem job", context={"field": "job"}
                    )
                expected = None if schedule.last_tick_at is None else _iso(schedule.last_tick_at)
                new_cursor = apply_tick(schedule, plan, now=now_utc).last_tick_at
                statement = update(ScheduleRow).where(ScheduleRow.id == schedule.id)
                statement = statement.where(
                    ScheduleRow.last_tick_at.is_(None)
                    if expected is None
                    else ScheduleRow.last_tick_at == expected
                )
                statement = statement.values(
                    last_tick_at=None if new_cursor is None else _iso(new_cursor),
                    updated_at=_iso(now_utc),
                ).returning(ScheduleRow.id)
                won = session.execute(statement).scalar_one_or_none()
                if won is None:
                    applied = False
                else:
                    session.add(job_to_row(job))
                    session.flush()
                    session.add(
                        self._audit_row(
                            entity_id=job.id,
                            entity_type=ENTITY_JOB,
                            event_type=JOB_ENQUEUED,
                            correlation_id=correlation_id,
                            recorded_at=now_utc,
                            payload={
                                "type": job.type.value,
                                "priority": job.priority,
                                "status": job.status.value,
                                "attempts": job.attempts,
                                "schedule_id": schedule.id,
                            },
                            source=AUDIT_SOURCE_JOB,
                        )
                    )
                    session.add(
                        self._audit_row(
                            entity_id=schedule.id,
                            entity_type=ENTITY_SCHEDULE,
                            event_type=SCHEDULE_JOB_ENQUEUED,
                            correlation_id=correlation_id,
                            recorded_at=now_utc,
                            payload={
                                "name": schedule.name,
                                "job_id": job.id,
                                "occurrence_count": plan.occurrence_count,
                                "reason": plan.reason,
                            },
                        )
                    )
            elif plan.action in (TickAction.SKIP_LOCKED, TickAction.SKIP_QUIET_WINDOW):
                session.add(
                    self._audit_row(
                        entity_id=schedule.id,
                        entity_type=ENTITY_SCHEDULE,
                        event_type=SCHEDULE_TICK_SKIPPED,
                        correlation_id=correlation_id,
                        recorded_at=now_utc,
                        payload={
                            "name": schedule.name,
                            "reason": plan.reason,
                            "occurrence_count": plan.occurrence_count,
                            "lock_name": plan.lock_name,
                        },
                    )
                )
            session.flush()
            session.refresh(row)
            persisted = _schedule_from_row(row)
        return persisted, applied

    def _audit_row(
        self,
        *,
        entity_id: str,
        entity_type: str,
        event_type: str,
        correlation_id: str,
        recorded_at: datetime,
        payload: dict[str, Any],
        source: str = AUDIT_SOURCE_SCHEDULER,
    ) -> AuditEventRow:
        return AuditEventRow(
            id=self.id_factory("aud"),
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            source=source,
            correlation_id=correlation_id,
            payload=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            recorded_at=_iso(recorded_at),
        )


def _schedule_to_row(schedule: Schedule) -> ScheduleRow:
    return ScheduleRow(
        id=schedule.id,
        name=schedule.name,
        type=schedule.type.value,
        job_type=schedule.job_type.value,
        priority=schedule.priority,
        max_attempts=schedule.max_attempts,
        enabled=schedule.enabled,
        timezone=schedule.timezone,
        interval_seconds=schedule.interval_seconds,
        cron=schedule.cron,
        quiet_windows=json.dumps(
            [window.to_contract() for window in schedule.quiet_windows],
            ensure_ascii=False,
            sort_keys=True,
        ),
        lock_name=schedule.lock_name,
        payload=json.dumps(dict(schedule.payload), ensure_ascii=False, sort_keys=True),
        entity_type=schedule.entity_type,
        entity_id=schedule.entity_id,
        last_tick_at=(None if schedule.last_tick_at is None else _iso(schedule.last_tick_at)),
        schema_version=schedule.schema_version,
        created_at=_iso(schedule.created_at),
        updated_at=_iso(schedule.updated_at),
    )


def _schedule_from_row(row: ScheduleRow) -> Schedule:
    windows = tuple(
        QuietWindow(
            start=str(item["start"]),
            end=str(item["end"]),
            days=tuple(int(day) for day in item.get("days", [])),
        )
        for item in json.loads(row.quiet_windows or "[]")
    )
    return Schedule(
        id=row.id,
        name=row.name,
        type=ScheduleType(row.type),
        job_type=JobType(row.job_type),
        priority=row.priority,
        max_attempts=row.max_attempts,
        enabled=row.enabled,
        timezone=row.timezone,
        interval_seconds=row.interval_seconds,
        cron=row.cron,
        quiet_windows=windows,
        lock_name=row.lock_name,
        payload=json.loads(row.payload),
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        last_tick_at=None if row.last_tick_at is None else _parse(row.last_tick_at),
        schema_version=row.schema_version,
        created_at=_parse(row.created_at),
        updated_at=_parse(row.updated_at),
    )


def _lock_from_row(row: JobLockRow) -> Lock:
    return Lock(
        name=row.name,
        owner=row.owner,
        acquired_at=_parse(row.acquired_at),
        expires_at=_parse(row.expires_at),
        correlation_id=row.correlation_id,
    )


__all__ = [
    "SqlAlchemyScheduleRepository",
]
