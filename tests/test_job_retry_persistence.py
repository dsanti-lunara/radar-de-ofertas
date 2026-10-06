from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.application.job_service import JobService
from radar.domain.human_action import HumanActionStatus, HumanActionType
from radar.domain.job import (
    JOB_LEASE_NOT_HELD,
    JOB_NOT_CLAIMABLE,
    JOB_STATE_INVALID,
    JobError,
    JobStatus,
)
from radar.domain.retry import build_retry_policy
from radar.infrastructure.job_repository import SqlAlchemyJobRepository
from radar.infrastructure.models import AuditEventRow, HumanActionRow, JobRow

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now = self.now + timedelta(**kwargs)


def _service(engine: Engine, clock: _Clock | None = None, **kwargs: object) -> JobService:
    return JobService(
        repository=SqlAlchemyJobRepository(engine=engine),
        clock=clock or _Clock(FIXED_NOW),
        **kwargs,  # type: ignore[arg-type]
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


def test_transient_failure_uses_configured_backoff_and_attempt_limit(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    job = service.enqueue(job_type="NORMALIZE_CAPTURE", correlation_id="cid-1", max_attempts=3)

    first = service.claim(worker_id="worker-a", lease_seconds=60)
    assert first.attempts == 1

    scheduled = service.fail(job.id, worker_id="worker-a", error_code="RAD-WF-001")
    assert scheduled.job.status is JobStatus.RETRY_WAIT
    assert scheduled.resolution.retryable is True
    assert scheduled.resolution.delay_seconds == 30
    assert scheduled.human_action is None

    # The backoff is real: the retry is not claimable before available_at.
    with pytest.raises(JobError) as early:
        service.claim(worker_id="worker-b")
    assert early.value.error.code == JOB_NOT_CLAIMABLE

    clock.advance(seconds=30)
    second = service.claim(worker_id="worker-b", lease_seconds=60)
    assert second.status is JobStatus.CLAIMED
    assert second.attempts == 2

    second_scheduled = service.fail(job.id, worker_id="worker-b", error_code="RAD-WF-001")
    assert second_scheduled.resolution.delay_seconds == 120

    clock.advance(seconds=120)
    third = service.claim(worker_id="worker-c", lease_seconds=60)
    assert third.attempts == 3

    exhausted = service.fail(job.id, worker_id="worker-c", error_code="RAD-WF-001")
    assert exhausted.job.status is JobStatus.DEAD
    assert exhausted.resolution.retryable is False
    assert exhausted.human_action is not None
    assert exhausted.human_action.action_type is HumanActionType.DEAD_JOB_REVIEW
    assert exhausted.human_action.reason == "RETRIES_EXHAUSTED"

    # No job was recreated and no further retry is possible.
    assert _count(migrated_engine, "job") == 1
    with pytest.raises(JobError) as stopped:
        service.claim(worker_id="worker-d")
    assert stopped.value.error.code == JOB_NOT_CLAIMABLE

    events = _audit_events(migrated_engine, job.id)
    assert events.count("JOB_RETRY_SCHEDULED") == 2
    assert events.count("JOB_DEAD") == 1
    assert _count(migrated_engine, "human_action") == 1


def test_configured_policy_is_used_for_backoff(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    policy = build_retry_policy(
        {"schema_version": "1.0", "policy_version": "operator", "backoff_seconds": [7, 11]}
    )
    service = _service(migrated_engine, clock, retry_policy=policy)
    job = service.enqueue(job_type="CALCULATE_SCORES", correlation_id="cid-1")
    service.claim(worker_id="worker-a")

    result = service.fail(job.id, worker_id="worker-a", error_code="RAD-WF-002")
    assert result.resolution.delay_seconds == 7
    assert result.job.available_at == FIXED_NOW + timedelta(seconds=7)


def test_permanent_failure_never_retries(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    job = service.enqueue(job_type="NORMALIZE_CAPTURE", correlation_id="cid-1")
    service.claim(worker_id="worker-a")

    result = service.fail(job.id, worker_id="worker-a", error_code="RAD-CAP-004")
    assert result.job.status is JobStatus.FAILED
    assert result.resolution.retryable is False
    assert result.resolution.delay_seconds is None
    assert result.human_action is None

    clock.advance(days=1)
    with pytest.raises(JobError) as no_retry:
        service.claim(worker_id="worker-b")
    assert no_retry.value.error.code == JOB_NOT_CLAIMABLE
    assert _audit_events(migrated_engine, job.id).count("JOB_FAILED") == 1


def test_auth_required_does_not_loop_and_raises_a_human_action(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    job = service.enqueue(job_type="AI_REVIEW", correlation_id="cid-1", max_attempts=5)
    claimed = service.claim(worker_id="worker-a")
    assert claimed.attempts == 1

    result = service.fail(job.id, worker_id="worker-a", error_code="RAD-AI-001")
    assert result.job.status is JobStatus.DEAD
    assert result.resolution.retryable is False
    assert result.resolution.delay_seconds is None
    assert result.job.attempts == 1  # no retry attempt was consumed
    assert result.human_action is not None
    assert result.human_action.action_type is HumanActionType.RESTORE_AI_AUTH

    clock.advance(days=1)
    with pytest.raises(JobError) as no_loop:
        service.claim(worker_id="worker-b")
    assert no_loop.value.error.code == JOB_NOT_CLAIMABLE
    assert "JOB_RETRY_SCHEDULED" not in _audit_events(migrated_engine, job.id)


def test_exhaustion_creates_auditable_human_action_without_recreating_the_entity(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)
    job = service.enqueue(
        job_type="PUBLISH_TELEGRAM",
        correlation_id="cid-audit",
        entity_type="candidate",
        entity_id="cand_1",
        max_attempts=1,
    )
    service.claim(worker_id="worker-a")

    result = service.fail(job.id, worker_id="worker-a", error_code="RAD-WF-001")
    assert result.job.status is JobStatus.DEAD
    action = result.human_action
    assert action is not None
    assert action.status is HumanActionStatus.OPEN
    assert action.entity_type == "candidate"
    assert action.entity_id == "cand_1"
    assert action.correlation_id == "cid-audit"
    assert action.impact and action.next_steps

    with Session(migrated_engine) as session:
        row = session.get(HumanActionRow, action.id)
    assert row is not None
    assert row.status == "OPEN"
    assert row.error_code == "RAD-WF-001"

    # The job is not recreated and a repeat report is rejected without a second action.
    assert _count(migrated_engine, "job") == 1
    with Session(migrated_engine) as session:
        assert session.get(JobRow, job.id) is not None
    with pytest.raises(JobError) as repeated:
        service.fail(job.id, worker_id="worker-a", error_code="RAD-WF-001")
    assert repeated.value.error.code in (JOB_LEASE_NOT_HELD, JOB_STATE_INVALID)
    assert _count(migrated_engine, "human_action") == 1

    job_events = _audit_events(migrated_engine, job.id)
    assert job_events.count("JOB_DEAD") == 1
    assert _audit_events(migrated_engine, action.id) == ["HUMAN_ACTION_CREATED"]


def test_fail_requires_the_lease_owner(migrated_engine: Engine) -> None:
    service = _service(migrated_engine)
    job = service.enqueue(job_type="NORMALIZE_CAPTURE", correlation_id="cid-1")
    service.claim(worker_id="worker-a")

    with pytest.raises(JobError) as denied:
        service.fail(job.id, worker_id="worker-b", error_code="RAD-WF-001")
    assert denied.value.error.code == JOB_LEASE_NOT_HELD

    with Session(migrated_engine) as session:
        row = session.get(JobRow, job.id)
    assert row is not None
    assert row.status == "CLAIMED"
    assert _count(migrated_engine, "human_action") == 0
