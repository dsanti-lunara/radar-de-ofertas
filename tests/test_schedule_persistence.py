from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.application.schedule_service import ScheduleService
from radar.domain.schedule import (
    SCHEDULE_INPUT_INVALID,
    SCHEDULE_NOT_FOUND,
    ScheduleError,
    TickAction,
)
from radar.infrastructure.job_repository import SqlAlchemyJobRepository
from radar.infrastructure.models import AuditEventRow, JobRow, ScheduleRow
from radar.infrastructure.schedule_repository import SqlAlchemyScheduleRepository

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now = self.now + timedelta(**kwargs)


def _service(engine: Engine, clock: _Clock | None = None) -> ScheduleService:
    return ScheduleService(
        repository=SqlAlchemyScheduleRepository(engine=engine),
        clock=clock or _Clock(FIXED_NOW),
    )


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
    assert value is not None
    return int(value)


def _audit_events(engine: Engine, entity_id: str) -> list[str]:
    with Session(engine) as session:
        rows = (
            session.execute(
                select(AuditEventRow.event_type)
                .where(AuditEventRow.entity_id == entity_id)
                .order_by(AuditEventRow.recorded_at, AuditEventRow.event_type)
            )
            .scalars()
            .all()
        )
    return list(rows)


def test_create_persists_schedule_and_audit(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    schedule = service.create(
        name="nightly-backup",
        schedule_type="INTERVAL",
        job_type="BACKUP_DATABASE",
        interval_seconds=3600,
        priority=3,
        payload={"scope": "full"},
        entity_type="node",
        entity_id="local",
    )

    with Session(migrated_engine) as session:
        row = session.get(ScheduleRow, schedule.id)
    assert row is not None
    assert row.name == "nightly-backup"
    assert row.type == "INTERVAL"
    assert row.job_type == "BACKUP_DATABASE"
    assert row.interval_seconds == 3600
    assert row.enabled is True
    assert row.lock_name == "schedule:nightly-backup"
    assert row.last_tick_at == FIXED_NOW.isoformat()

    assert service.get(schedule.id).name == "nightly-backup"
    assert [item.id for item in service.list()] == [schedule.id]
    assert _audit_events(migrated_engine, schedule.id) == ["SCHEDULE_CREATED"]


def test_duplicate_name_is_rejected_without_second_row(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    service.create(
        name="unique", schedule_type="INTERVAL", job_type="BACKUP_DATABASE", interval_seconds=60
    )

    with pytest.raises(ScheduleError) as excinfo:
        service.create(
            name="unique", schedule_type="INTERVAL", job_type="BACKUP_DATABASE", interval_seconds=60
        )
    assert excinfo.value.error.code == SCHEDULE_INPUT_INVALID
    assert _count(migrated_engine, "schedule") == 1


def test_unknown_schedule_returns_structured_error(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    with pytest.raises(ScheduleError) as excinfo:
        service.get("sch_missing")
    assert excinfo.value.error.code == SCHEDULE_NOT_FOUND


def test_tick_creates_one_pending_job_and_never_executes(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    schedule = service.create(
        name="scores",
        schedule_type="INTERVAL",
        job_type="CALCULATE_SCORES",
        interval_seconds=300,
        payload={"candidate_id": "cand_1"},
    )

    clock.advance(hours=1)
    results = service.tick_due(correlation_id="cid-tick")

    assert len(results) == 1
    result = results[0]
    assert result.plan.action is TickAction.ENQUEUE
    assert result.plan.occurrence_count == 12
    assert result.job is not None
    assert result.job.status.value == "PENDING"
    assert result.job.attempts == 0

    # Exactly one Job was created for the 12 missed ticks (coalesced).
    assert _count(migrated_engine, "job") == 1
    with Session(migrated_engine) as session:
        job_row = session.execute(select(JobRow)).scalar_one()
    assert job_row.type == "CALCULATE_SCORES"
    assert job_row.status == "PENDING"
    assert job_row.attempts == 0
    assert "cand_1" in job_row.payload
    assert "scheduled_occurrences" in job_row.payload

    # The Scheduler never executed business logic: no claim/start/complete events.
    job_events = _audit_events(migrated_engine, job_row.id)
    assert job_events == ["JOB_ENQUEUED"]
    schedule_events = _audit_events(migrated_engine, schedule.id)
    assert "SCHEDULE_CREATED" in schedule_events
    assert "SCHEDULE_JOB_ENQUEUED" in schedule_events

    # The cursor advanced to the tick instant and is observable.
    updated = service.get(schedule.id)
    assert updated.last_tick_at == clock.now
    assert updated.to_contract()["next_run_at"] == (clock.now + timedelta(seconds=300)).isoformat()


def test_equivalent_lock_defers_tick_and_coalesces(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    schedule = service.create(
        name="generation",
        schedule_type="INTERVAL",
        job_type="GENERATE_CONTENT",
        interval_seconds=300,
    )
    # An equivalent execution is in progress and holds the lock.
    SqlAlchemyJobRepository(engine=migrated_engine).acquire_lock(
        name=schedule.lock_name, owner="worker-a", ttl_seconds=3600, now=FIXED_NOW
    )

    clock.advance(minutes=10)
    deferred = service.tick_due(correlation_id="cid-locked")
    assert len(deferred) == 1
    assert deferred[0].plan.action is TickAction.SKIP_LOCKED
    assert deferred[0].plan.occurrence_count == 2
    assert deferred[0].job is None
    assert _count(migrated_engine, "job") == 0
    assert service.get(schedule.id).last_tick_at == FIXED_NOW

    # The deferred ticks coalesce into a single Job once the lock is released.
    SqlAlchemyJobRepository(engine=migrated_engine).release_lock(
        schedule.lock_name, owner="worker-a", now=FIXED_NOW
    )
    clock.advance(minutes=5)
    enqueued = service.tick_due(correlation_id="cid-free")
    assert len(enqueued) == 1
    assert enqueued[0].plan.action is TickAction.ENQUEUE
    assert enqueued[0].plan.occurrence_count == 3
    assert _count(migrated_engine, "job") == 1

    skipped = [
        event
        for event in _audit_events(migrated_engine, schedule.id)
        if event == "SCHEDULE_TICK_SKIPPED"
    ]
    assert len(skipped) == 1


def test_quiet_window_defers_with_controlled_clock(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    schedule = service.create(
        name="publishing",
        schedule_type="INTERVAL",
        job_type="AGGREGATE_DAILY_METRICS",
        interval_seconds=300,
        timezone="America/Maceio",
        quiet_windows=[{"start": "22:00", "end": "07:00"}],
    )

    # 02:00 UTC == 23:00 America/Maceio, inside the quiet window.
    clock.now = datetime(2026, 10, 6, 2, 0, tzinfo=UTC)
    quiet = service.tick_due(correlation_id="cid-quiet")
    assert len(quiet) == 1
    assert quiet[0].plan.action is TickAction.SKIP_QUIET_WINDOW
    assert quiet[0].plan.occurrence_count == 168
    assert _count(migrated_engine, "job") == 0
    assert service.get(schedule.id).last_tick_at == FIXED_NOW

    # 12:00 UTC == 09:00 America/Maceio, outside the window: coalesced into one Job.
    clock.now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    allowed = service.tick_due(correlation_id="cid-allowed")
    assert len(allowed) == 1
    assert allowed[0].plan.action is TickAction.ENQUEUE
    assert allowed[0].plan.occurrence_count == 288
    assert _count(migrated_engine, "job") == 1


def test_disabled_schedule_is_never_ticked(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    schedule = service.create(
        name="disabled",
        schedule_type="INTERVAL",
        job_type="BACKUP_DATABASE",
        interval_seconds=60,
    )
    disabled = service.set_enabled(schedule.id, enabled=False)
    assert disabled.enabled is False
    assert _audit_events(migrated_engine, schedule.id)[-1] == "SCHEDULE_UPDATED"

    clock.advance(hours=1)
    assert service.tick_due(correlation_id="cid-disabled") == []
    assert _count(migrated_engine, "job") == 0

    forced = service.tick_schedule(schedule.id, correlation_id="cid-forced")
    assert forced.plan.action is TickAction.SKIP_DISABLED
    assert _count(migrated_engine, "job") == 0


def test_on_demand_schedule_only_ticks_when_forced(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    schedule = service.create(
        name="manual",
        schedule_type="ON_DEMAND",
        job_type="DISCOVER_MARKETPLACE",
    )

    due = service.tick_due(correlation_id="cid-due")
    assert len(due) == 1
    assert due[0].plan.action is TickAction.SKIP_NOT_DUE
    assert due[0].job is None
    assert _count(migrated_engine, "job") == 0

    forced = service.tick_schedule(schedule.id, correlation_id="cid-on-demand")
    assert forced.plan.action is TickAction.ENQUEUE
    assert forced.plan.reason == "FORCED"
    assert forced.plan.occurrence_count == 1
    assert _count(migrated_engine, "job") == 1


def test_repeated_tick_at_same_instant_is_idempotent(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    service.create(
        name="idempotent",
        schedule_type="INTERVAL",
        job_type="BACKUP_DATABASE",
        interval_seconds=300,
    )

    clock.advance(hours=1)
    first = service.tick_due(correlation_id="cid-1")
    assert first[0].plan.action is TickAction.ENQUEUE
    second = service.tick_due(correlation_id="cid-2")
    assert second[0].plan.action is TickAction.SKIP_NOT_DUE
    assert _count(migrated_engine, "job") == 1


def test_concurrent_ticks_never_create_overlapping_jobs(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    service.create(
        name="concurrent",
        schedule_type="INTERVAL",
        job_type="CALCULATE_SCORES",
        interval_seconds=300,
    )
    clock.advance(hours=1)

    barrier = threading.Barrier(2)
    results: list[object] = []

    def _tick(correlation_id: str) -> None:
        barrier.wait()
        try:
            results.append(service.tick_due(correlation_id=correlation_id))
        except Exception as exc:  # pragma: no cover - surfaces an unexpected failure
            results.append(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_tick, f"cid-{index}") for index in range(2)]
        for future in futures:
            future.result()

    assert all(not isinstance(item, Exception) for item in results)
    # The optimistic cursor guard lets exactly one tick enqueue the coalesced Job.
    assert _count(migrated_engine, "job") == 1


def test_cron_schedule_enqueues_coalesced_job(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    service.create(
        name="cron-scores",
        schedule_type="CRON",
        job_type="CALCULATE_SCORES",
        cron="*/5 * * * *",
    )

    clock.advance(minutes=35)
    results = service.tick_due(correlation_id="cid-cron")
    assert len(results) == 1
    assert results[0].plan.action is TickAction.ENQUEUE
    assert results[0].plan.occurrence_count == 7
    assert _count(migrated_engine, "job") == 1
