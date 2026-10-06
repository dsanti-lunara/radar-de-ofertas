from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from radar.domain.capture import CandidateState
from radar.domain.job import (
    DEFAULT_MAX_ATTEMPTS,
    JOB_INPUT_INVALID,
    JOB_LEASE_NOT_HELD,
    JOB_SCHEMA_VERSION,
    JOB_STATE_INVALID,
    Job,
    JobError,
    JobStatus,
    JobType,
    Lock,
    complete_job,
    create_job,
    start_job,
)

pytestmark = pytest.mark.unit

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _id_factory(prefix: str) -> str:
    return f"{prefix}_test"


def _job(**overrides: object) -> Job:
    params: dict[str, object] = {
        "job_type": JobType.NORMALIZE_CAPTURE,
        "correlation_id": "cid-1",
        "now": FIXED_NOW,
        "priority": 5,
        "entity_type": "candidate",
        "entity_id": "cand_1",
        "payload": {"offer_id": "off_1"},
        "id_factory": _id_factory,
    }
    params.update(overrides)
    return create_job(**params)  # type: ignore[arg-type]


def test_job_status_is_independent_from_domain_state() -> None:
    job_states = {state.value for state in JobStatus}
    domain_states = {state.value for state in CandidateState}
    assert "NEW" in domain_states
    assert "NEW" not in job_states
    assert job_states == {
        "PENDING",
        "CLAIMED",
        "RUNNING",
        "RETRY_WAIT",
        "SUCCESS",
        "FAILED",
        "CANCELLED",
        "DEAD",
    }
    with pytest.raises(ValueError):
        JobStatus("NEW")


def test_job_type_rejects_domain_state() -> None:
    with pytest.raises(JobError) as excinfo:
        _job(job_type="NEW")
    assert excinfo.value.error.code == JOB_INPUT_INVALID
    assert "NEW" not in {item.value for item in JobType}


def test_create_job_persists_priority_availability_attempts_and_correlation() -> None:
    job = _job(priority=7, available_at=FIXED_NOW + timedelta(minutes=5))

    assert job.id == "job_test"
    assert job.type is JobType.NORMALIZE_CAPTURE
    assert job.status is JobStatus.PENDING
    assert job.priority == 7
    assert job.attempts == 0
    assert job.max_attempts == DEFAULT_MAX_ATTEMPTS
    assert job.available_at == FIXED_NOW + timedelta(minutes=5)
    assert job.correlation_id == "cid-1"
    assert job.payload == {"offer_id": "off_1"}
    assert job.schema_version == JOB_SCHEMA_VERSION

    contract = job.to_contract()
    assert contract["status"] == "PENDING"
    assert contract["priority"] == 7
    assert contract["attempts"] == 0
    assert contract["correlation_id"] == "cid-1"
    assert contract["available_at"] == (FIXED_NOW + timedelta(minutes=5)).isoformat()


def test_invalid_schema_version_is_rejected() -> None:
    with pytest.raises(JobError) as excinfo:
        _job(schema_version="9.9")
    assert excinfo.value.error.code == JOB_INPUT_INVALID


def test_invalid_priority_and_attempt_budget_are_rejected() -> None:
    for bad_priority in (True, 1.5, "5"):
        with pytest.raises(JobError):
            _job(priority=bad_priority)
    for bad_attempts in (True, 0, -1, 1.5):
        with pytest.raises(JobError):
            _job(max_attempts=bad_attempts)


def test_payload_must_be_json_and_free_of_sensitive_fields() -> None:
    with pytest.raises(JobError) as excinfo:
        _job(payload={"password": "not-allowed"})
    assert excinfo.value.error.code == JOB_INPUT_INVALID

    with pytest.raises(JobError):
        _job(payload={"nested": {"token": "x"}})

    with pytest.raises(JobError):
        _job(payload={"when": FIXED_NOW})


def test_half_specified_entity_reference_is_rejected() -> None:
    with pytest.raises(JobError):
        _job(entity_id=None)
    with pytest.raises(JobError):
        _job(entity_type=None)


def test_pending_job_is_claimable_only_when_available() -> None:
    future = _job(available_at=FIXED_NOW + timedelta(seconds=30))
    assert future.is_claimable(FIXED_NOW) is False
    assert future.is_claimable(FIXED_NOW + timedelta(seconds=30)) is True


def test_expired_lease_is_claimable_by_another_worker() -> None:
    claimed = replace(
        _job(),
        status=JobStatus.CLAIMED,
        locked_by="worker-a",
        locked_at=FIXED_NOW,
        lease_expires_at=FIXED_NOW + timedelta(seconds=30),
        attempts=1,
    )
    assert claimed.lease_is_active(FIXED_NOW) is True
    assert claimed.is_claimable(FIXED_NOW) is False
    assert claimed.lease_is_active(FIXED_NOW + timedelta(seconds=31)) is False
    assert claimed.is_claimable(FIXED_NOW + timedelta(seconds=31)) is True


def test_start_requires_the_lease_owner() -> None:
    claimed = replace(
        _job(),
        status=JobStatus.CLAIMED,
        locked_by="worker-a",
        locked_at=FIXED_NOW,
        lease_expires_at=FIXED_NOW + timedelta(seconds=30),
        attempts=1,
    )

    running = start_job(claimed, worker_id="worker-a", now=FIXED_NOW)
    assert running.status is JobStatus.RUNNING
    # idempotent for the owner while the lease is active
    assert start_job(running, worker_id="worker-a", now=FIXED_NOW) is running

    with pytest.raises(JobError) as excinfo:
        start_job(claimed, worker_id="worker-b", now=FIXED_NOW)
    assert excinfo.value.error.code == JOB_LEASE_NOT_HELD


def test_worker_cannot_confirm_another_workers_execution() -> None:
    running = replace(
        _job(),
        status=JobStatus.RUNNING,
        locked_by="worker-a",
        locked_at=FIXED_NOW,
        lease_expires_at=FIXED_NOW + timedelta(seconds=30),
        attempts=1,
    )

    with pytest.raises(JobError) as excinfo:
        complete_job(running, worker_id="worker-b", now=FIXED_NOW)
    assert excinfo.value.error.code == JOB_LEASE_NOT_HELD

    with pytest.raises(JobError) as expired:
        complete_job(running, worker_id="worker-a", now=FIXED_NOW + timedelta(seconds=31))
    assert expired.value.error.code == JOB_LEASE_NOT_HELD

    done = complete_job(running, worker_id="worker-a", now=FIXED_NOW)
    assert done.status is JobStatus.SUCCESS
    assert done.lease_expires_at is None
    # idempotent for the same owner
    assert complete_job(done, worker_id="worker-a", now=FIXED_NOW) is done


def test_completing_a_pending_job_is_a_state_error() -> None:
    with pytest.raises(JobError) as excinfo:
        complete_job(_job(), worker_id="worker-a", now=FIXED_NOW)
    assert excinfo.value.error.code == JOB_STATE_INVALID


def test_lock_expiration_is_explicit() -> None:
    lock = Lock(
        name="queue:general",
        owner="worker-a",
        acquired_at=FIXED_NOW,
        expires_at=FIXED_NOW + timedelta(seconds=30),
    )
    assert lock.is_active(FIXED_NOW) is True
    assert lock.is_active(FIXED_NOW + timedelta(seconds=31)) is False
    contract = lock.to_contract()
    assert contract["name"] == "queue:general"
    assert contract["owner"] == "worker-a"
    assert contract["schema_version"] == JOB_SCHEMA_VERSION
