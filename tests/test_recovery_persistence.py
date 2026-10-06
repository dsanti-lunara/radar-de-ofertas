from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.application.job_service import JobService
from radar.application.recovery_service import RecoveryService
from radar.application.schedule_service import ScheduleService
from radar.domain.job import JOB_NOT_CLAIMABLE, JobError, JobStatus
from radar.infrastructure.job_repository import SqlAlchemyJobRepository
from radar.infrastructure.models import AuditEventRow, JobRow, RuntimeStateRow, ScheduleRow
from radar.infrastructure.recovery_repository import SqlAlchemyRecoveryRepository
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


def _recovery(engine: Engine, clock: _Clock, *, with_schedules: bool = True) -> RecoveryService:
    schedule_service = (
        ScheduleService(repository=SqlAlchemyScheduleRepository(engine=engine), clock=clock)
        if with_schedules
        else None
    )
    return RecoveryService(
        store=SqlAlchemyRecoveryRepository(engine=engine),
        schedule_service=schedule_service,
        clock=clock,
    )


def _jobs(engine: Engine, clock: _Clock) -> JobService:
    return JobService(repository=SqlAlchemyJobRepository(engine=engine), clock=clock)


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
    assert value is not None
    return int(value)


def _events(engine: Engine, entity_id: str) -> list[str]:
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


def _event_types(engine: Engine) -> list[str]:
    with Session(engine) as session:
        return list(session.execute(select(AuditEventRow.event_type)).scalars().all())


def test_unclean_shutdown_is_detected_and_audited(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _recovery(migrated_engine, clock)

    first = service.run_recovery(correlation_id="cid-start-1")
    assert first.unclean_shutdown is False
    assert first.state.recovery_count == 1

    # No clean shutdown happened in between, so the next startup is unclean.
    clock.advance(minutes=5)
    second = service.run_recovery(correlation_id="cid-start-2")
    assert second.unclean_shutdown is True
    assert second.state.recovery_count == 2

    events = _events(migrated_engine, "core")
    assert events.count("UNCLEAN_SHUTDOWN_DETECTED") == 1
    assert events.count("RECOVERY_STARTED") == 2
    assert events.count("RECOVERY_COMPLETED") == 2

    with Session(migrated_engine) as session:
        row = session.get(RuntimeStateRow, "core")
    assert row is not None
    assert row.clean_shutdown is False
    assert row.recovery_count == 2


def test_clean_shutdown_is_not_reported_as_unclean(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _recovery(migrated_engine, clock)
    service.run_recovery(correlation_id="cid-1")
    state = service.record_clean_shutdown(correlation_id="cid-stop")
    assert state.clean_shutdown is True

    clock.advance(minutes=1)
    restarted = service.run_recovery(correlation_id="cid-2")
    assert restarted.unclean_shutdown is False
    assert "CLEAN_SHUTDOWN_RECORDED" in _events(migrated_engine, "core")
    assert _events(migrated_engine, "core").count("UNCLEAN_SHUTDOWN_DETECTED") == 0


def test_orphan_lease_is_requeued_and_old_worker_cannot_confirm(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    service = _recovery(migrated_engine, clock)
    jobs = _jobs(migrated_engine, clock)
    job = jobs.enqueue(job_type="NORMALIZE_CAPTURE", correlation_id="cid-job")
    jobs.claim(worker_id="worker-a", lease_seconds=600)

    # Crash after the claim transaction and before any confirmation.
    clock.advance(minutes=1)
    report = service.run_recovery(correlation_id="cid-rec")
    assert report.jobs_requeued == 1
    assert report.jobs_blocked == 0

    with Session(migrated_engine) as session:
        row = session.get(JobRow, job.id)
    assert row is not None
    assert row.status == "PENDING"
    assert row.locked_by is None
    assert row.lease_expires_at is None

    # The previous worker can never confirm the recovered execution.
    with pytest.raises(JobError) as denied:
        jobs.complete(job.id, worker_id="worker-a")
    assert denied.value.error.code in ("RAD-WF-009", "RAD-WF-010")

    recovered = jobs.claim(worker_id="worker-b", lease_seconds=60)
    assert recovered.id == job.id
    assert recovered.status is JobStatus.CLAIMED
    assert _events(migrated_engine, job.id).count("RECOVERY_JOB_REQUEUED") == 1


def test_external_effect_job_is_blocked_and_never_resent(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _recovery(migrated_engine, clock)
    jobs = _jobs(migrated_engine, clock)
    job = jobs.enqueue(
        job_type="PUBLISH_TELEGRAM",
        correlation_id="cid-publish",
        entity_type="opportunity",
        entity_id="opp_1",
    )
    jobs.claim(worker_id="worker-a", lease_seconds=600)
    jobs.start(job.id, worker_id="worker-a")

    # Crash after a possible remote acceptance and before local confirmation.
    clock.advance(minutes=1)
    report = service.run_recovery(correlation_id="cid-rec")
    assert report.jobs_blocked == 1
    assert report.jobs_requeued == 0

    with Session(migrated_engine) as session:
        row = session.get(JobRow, job.id)
    assert row is not None
    assert row.status == "DEAD"
    assert row.locked_by is None
    assert row.lease_expires_at is None

    clock.advance(days=1)
    with pytest.raises(JobError) as no_resend:
        jobs.claim(worker_id="worker-b")
    assert no_resend.value.error.code == JOB_NOT_CLAIMABLE
    assert _events(migrated_engine, job.id).count("RECOVERY_JOB_BLOCKED") == 1


def test_orphan_lock_is_cleared(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _recovery(migrated_engine, clock)
    jobs = _jobs(migrated_engine, clock)
    service.run_recovery(correlation_id="cid-1")

    jobs.acquire_lock(name="schedule:nightly", owner="worker-a", ttl_seconds=600)
    assert jobs.get_lock("schedule:nightly") is not None

    clock.advance(minutes=1)
    report = service.run_recovery(correlation_id="cid-2")
    assert report.unclean_shutdown is True
    assert report.locks_cleared == 1
    assert jobs.get_lock("schedule:nightly") is None
    assert "RECOVERY_LOCK_CLEARED" in _event_types(migrated_engine)


def test_missed_schedule_is_coalesced_without_data_loss(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    schedules = ScheduleService(
        repository=SqlAlchemyScheduleRepository(engine=migrated_engine), clock=clock
    )
    service = _recovery(migrated_engine, clock)
    schedule = schedules.create(
        name="nightly-backup",
        schedule_type="INTERVAL",
        job_type="BACKUP_DATABASE",
        interval_seconds=3600,
        payload={"scope": "full"},
    )

    clock.advance(hours=12)
    report = service.run_recovery(correlation_id="cid-rec")
    assert report.schedules_coalesced == 1
    assert report.occurrences_coalesced == 12
    assert _count(migrated_engine, "job") == 1

    with Session(migrated_engine) as session:
        job = session.execute(select(JobRow)).scalar_one()
        refreshed = session.get(ScheduleRow, schedule.id)
    assert job.status == "PENDING"
    assert job.type == "BACKUP_DATABASE"
    assert '"scheduled_occurrences": 12' in job.payload
    assert refreshed is not None
    assert refreshed.last_tick_at == clock.now.isoformat()


def test_failure_injection_mid_transaction_rolls_back(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _recovery(migrated_engine, clock)

    def _boom(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        if statement.lstrip().upper().startswith("INSERT INTO RUNTIME_STATE"):
            raise RuntimeError("injected crash before commit")

    event.listen(migrated_engine, "before_cursor_execute", _boom)
    try:
        with pytest.raises(RuntimeError, match="injected crash"):
            service.run_recovery(correlation_id="cid-crash")
    finally:
        event.remove(migrated_engine, "before_cursor_execute", _boom)

    # The runtime marker and its audit trail are both rolled back.
    assert service.status() is None
    assert _count(migrated_engine, "runtime_state") == 0
    assert _count(migrated_engine, "audit_event") == 0


def test_recovery_is_idempotent_for_interrupted_jobs(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _recovery(migrated_engine, clock)
    jobs = _jobs(migrated_engine, clock)
    job = jobs.enqueue(job_type="CALCULATE_SCORES", correlation_id="cid-job")
    jobs.claim(worker_id="worker-a")

    first = service.run_recovery(correlation_id="cid-1")
    assert first.jobs_requeued == 1
    second = service.run_recovery(correlation_id="cid-2")
    assert second.jobs_requeued == 0
    assert _count(migrated_engine, "job") == 1
    assert _events(migrated_engine, job.id).count("RECOVERY_JOB_REQUEUED") == 1
