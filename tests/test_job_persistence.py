from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.application.job_service import JobService
from radar.domain.job import (
    JOB_INPUT_INVALID,
    JOB_LEASE_NOT_HELD,
    JOB_NOT_CLAIMABLE,
    LOCK_UNAVAILABLE,
    JobError,
    JobStatus,
)
from radar.infrastructure.job_repository import SqlAlchemyJobRepository
from radar.infrastructure.models import AuditEventRow, JobRow

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now = self.now + timedelta(**kwargs)


def _service(engine: Engine, clock: _Clock | None = None) -> JobService:
    return JobService(
        repository=SqlAlchemyJobRepository(engine=engine),
        clock=clock or _Clock(FIXED_NOW),
    )


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
    assert value is not None
    return int(value)


def test_job_persists_priority_availability_attempts_and_correlation(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    available_at = FIXED_NOW + timedelta(minutes=10)

    job = service.enqueue(
        job_type="NORMALIZE_CAPTURE",
        correlation_id="cid-pipeline",
        priority=9,
        available_at=available_at,
        entity_type="candidate",
        entity_id="cand_1",
        payload={"offer_id": "off_1"},
    )

    with Session(migrated_engine) as session:
        row = session.get(JobRow, job.id)
    assert row is not None
    assert row.type == "NORMALIZE_CAPTURE"
    assert row.status == "PENDING"
    assert row.priority == 9
    assert row.available_at == available_at.isoformat()
    assert row.attempts == 0
    assert row.max_attempts == 3
    assert row.correlation_id == "cid-pipeline"
    assert row.entity_type == "candidate"
    assert row.entity_id == "cand_1"

    # The job is not claimable before it is available.
    with pytest.raises(JobError) as early:
        service.claim(worker_id="worker-a")
    assert early.value.error.code == JOB_NOT_CLAIMABLE

    clock.now = available_at
    claimed = service.claim(worker_id="worker-a")
    assert claimed.id == job.id
    assert claimed.status is JobStatus.CLAIMED
    assert claimed.attempts == 1
    assert claimed.locked_by == "worker-a"
    assert claimed.correlation_id == "cid-pipeline"

    with Session(migrated_engine) as session:
        updated = session.get(JobRow, job.id)
    assert updated is not None
    assert updated.status == "CLAIMED"
    assert updated.attempts == 1
    assert updated.locked_by == "worker-a"
    assert updated.lease_expires_at is not None


def test_claim_grants_a_single_lease_under_concurrency(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    job = service.enqueue(job_type="CALCULATE_SCORES", correlation_id="cid-1")

    barrier = threading.Barrier(2)
    results: list[object] = []

    def _claim(worker: str) -> None:
        barrier.wait()
        try:
            results.append(service.claim(worker_id=worker))
        except JobError as exc:
            results.append(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(_claim, worker) for worker in ("worker-a", "worker-b")]
        for future in futures:
            future.result()

    claims = [item for item in results if not isinstance(item, JobError)]
    errors = [item for item in results if isinstance(item, JobError)]
    assert len(claims) == 1
    assert len(errors) == 1
    assert errors[0].error.code == JOB_NOT_CLAIMABLE
    assert errors[0].error.retryable is True

    with Session(migrated_engine) as session:
        row = session.get(JobRow, job.id)
    assert row is not None
    assert row.status == "CLAIMED"
    assert row.attempts == 1
    assert _count(migrated_engine, "job") == 1


def test_lease_expiry_lets_another_worker_recover_and_blocks_the_old_worker(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    job = service.enqueue(job_type="GENERATE_CONTENT", correlation_id="cid-1")

    first = service.claim(worker_id="worker-a", lease_seconds=30)
    assert first.locked_by == "worker-a"

    # Valid worker can confirm; an invalid worker cannot.
    with pytest.raises(JobError) as invalid:
        service.complete(job.id, worker_id="worker-b")
    assert invalid.value.error.code == JOB_LEASE_NOT_HELD

    clock.advance(seconds=31)
    recovered = service.claim(worker_id="worker-b", lease_seconds=30)
    assert recovered.locked_by == "worker-b"
    assert recovered.attempts == 2

    # The previous worker can no longer confirm the execution it lost.
    with pytest.raises(JobError) as stale:
        service.complete(job.id, worker_id="worker-a")
    assert stale.value.error.code == JOB_LEASE_NOT_HELD

    done = service.complete(job.id, worker_id="worker-b")
    assert done.status is JobStatus.SUCCESS
    assert done.attempts == 2
    assert done.lease_expires_at is None


def test_worker_cannot_start_or_complete_another_workers_job(
    migrated_engine: Engine,
) -> None:
    service = _service(migrated_engine)
    job = service.enqueue(job_type="AI_REVIEW", correlation_id="cid-1")
    service.claim(worker_id="worker-a")

    with pytest.raises(JobError) as start_denied:
        service.start(job.id, worker_id="worker-b")
    assert start_denied.value.error.code == JOB_LEASE_NOT_HELD

    with pytest.raises(JobError) as complete_denied:
        service.complete(job.id, worker_id="worker-b")
    assert complete_denied.value.error.code == JOB_LEASE_NOT_HELD

    running = service.start(job.id, worker_id="worker-a")
    assert running.status is JobStatus.RUNNING
    done = service.complete(job.id, worker_id="worker-a")
    assert done.status is JobStatus.SUCCESS


def test_invalid_job_is_rejected_without_persisting(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)

    with pytest.raises(JobError) as excinfo:
        service.enqueue(job_type="NEW", correlation_id="cid-1")
    assert excinfo.value.error.code == JOB_INPUT_INVALID
    assert _count(migrated_engine, "job") == 0

    with pytest.raises(JobError):
        service.enqueue(
            job_type="NORMALIZE_CAPTURE", correlation_id="cid-1", payload={"when": FIXED_NOW}
        )
    assert _count(migrated_engine, "job") == 0


def test_job_lifecycle_writes_audit_events(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    job = service.enqueue(job_type="PUBLISH_TELEGRAM", correlation_id="cid-audit")
    service.claim(worker_id="worker-a")
    service.start(job.id, worker_id="worker-a")
    service.complete(job.id, worker_id="worker-a")

    with Session(migrated_engine) as session:
        rows = (
            session.execute(
                select(AuditEventRow)
                .where(AuditEventRow.entity_id == job.id)
                .order_by(AuditEventRow.recorded_at, AuditEventRow.event_type)
            )
            .scalars()
            .all()
        )

    assert {row.event_type for row in rows} == {
        "JOB_ENQUEUED",
        "JOB_CLAIMED",
        "JOB_STARTED",
        "JOB_SUCCEEDED",
    }
    assert len(rows) == 4
    assert all(row.entity_type == "job" for row in rows)
    assert all(row.correlation_id == "cid-audit" for row in rows)


def test_logical_lock_is_exclusive_and_expires(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)

    acquired = service.acquire_lock(name="queue:general", owner="worker-a", ttl_seconds=30)
    assert acquired.owner == "worker-a"

    # Same owner renews; another owner fails closed while active.
    renewed = service.acquire_lock(name="queue:general", owner="worker-a", ttl_seconds=30)
    assert renewed.expires_at == FIXED_NOW + timedelta(seconds=30)

    with pytest.raises(JobError) as busy:
        service.acquire_lock(name="queue:general", owner="worker-b", ttl_seconds=30)
    assert busy.value.error.code == LOCK_UNAVAILABLE
    assert busy.value.error.retryable is True

    clock.advance(seconds=31)
    taken = service.acquire_lock(name="queue:general", owner="worker-b", ttl_seconds=30)
    assert taken.owner == "worker-b"

    # Only the owner can release.
    with pytest.raises(JobError) as release_denied:
        service.release_lock("queue:general", owner="worker-a")
    assert release_denied.value.error.code == LOCK_UNAVAILABLE

    service.release_lock("queue:general", owner="worker-b")
    assert service.get_lock("queue:general") is None


def test_lock_acquire_writes_audit_events(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    service.acquire_lock(name="marketplace:ml", owner="worker-a", ttl_seconds=30)
    service.release_lock("marketplace:ml", owner="worker-a")

    with Session(migrated_engine) as session:
        events = (
            session.execute(
                select(AuditEventRow.event_type)
                .where(AuditEventRow.entity_id == "marketplace:ml")
                .order_by(AuditEventRow.recorded_at, AuditEventRow.event_type)
            )
            .scalars()
            .all()
        )
    assert set(events) == {"LOCK_ACQUIRED", "LOCK_RELEASED"}
