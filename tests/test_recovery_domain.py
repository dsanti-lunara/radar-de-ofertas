from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from radar.domain.job import JobStatus, JobType, Lock, create_job
from radar.domain.recovery import (
    RECOVERY_SCHEMA_VERSION,
    JobRecoveryDecision,
    RecoveryAction,
    RecoveryError,
    RecoveryTrigger,
    RuntimeState,
    block_job,
    coerce_trigger,
    is_external_effect_job,
    plan_job_recovery,
    requeue_job,
    require_schema_version,
    should_clear_lock,
)

pytestmark = pytest.mark.unit

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _job(job_type: str = "NORMALIZE_CAPTURE", *, status: JobStatus = JobStatus.CLAIMED):
    base = create_job(job_type=job_type, correlation_id="cid-1", now=FIXED_NOW)
    return replace(
        base,
        status=status,
        locked_by="worker-a",
        locked_at=FIXED_NOW,
        lease_expires_at=FIXED_NOW + timedelta(seconds=60),
    )


def test_runtime_state_contract_is_versioned() -> None:
    state = RuntimeState(
        clean_shutdown=True,
        recovery_count=3,
        started_at=FIXED_NOW,
        shutdown_at=FIXED_NOW,
        last_recovery_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )
    contract = state.to_contract()
    assert contract["schema_version"] == RECOVERY_SCHEMA_VERSION
    assert contract["clean_shutdown"] is True
    assert contract["recovery_count"] == 3
    assert contract["started_at"] == FIXED_NOW.isoformat()


def test_external_effect_job_types_are_not_safe_to_retry() -> None:
    assert is_external_effect_job(JobType.PUBLISH_TELEGRAM) is True
    assert is_external_effect_job(JobType.PUBLISH_WHATSAPP) is True
    assert is_external_effect_job(JobType.GENERATE_AFFILIATE_LINK) is True
    assert is_external_effect_job(JobType.NORMALIZE_CAPTURE) is False


def test_plan_requeues_safe_job_and_blocks_side_effect_job() -> None:
    safe = plan_job_recovery(_job(), now=FIXED_NOW)
    assert safe == JobRecoveryDecision(RecoveryAction.REQUEUE, "ORPHAN_LEASE")

    side_effect = plan_job_recovery(_job("PUBLISH_TELEGRAM"), now=FIXED_NOW)
    assert side_effect.action is RecoveryAction.BLOCK
    assert side_effect.reason == "UNKNOWN_RESULT"


def test_plan_rejects_non_interrupted_job() -> None:
    with pytest.raises(RecoveryError) as error:
        plan_job_recovery(_job(status=JobStatus.PENDING), now=FIXED_NOW)
    assert error.value.error.code == "RAD-WF-019"


def test_requeue_clears_orphan_lease_and_makes_job_claimable() -> None:
    job = _job()
    requeued = requeue_job(job, now=FIXED_NOW)
    assert requeued.status is JobStatus.PENDING
    assert requeued.locked_by is None
    assert requeued.locked_at is None
    assert requeued.lease_expires_at is None
    assert requeued.available_at == FIXED_NOW
    assert requeued.is_claimable(FIXED_NOW) is True


def test_block_is_terminal_and_not_claimable() -> None:
    job = _job("PUBLISH_WHATSAPP")
    blocked = block_job(job, now=FIXED_NOW)
    assert blocked.status is JobStatus.DEAD
    assert blocked.locked_by is None
    assert blocked.lease_expires_at is None
    assert blocked.is_claimable(FIXED_NOW) is False
    assert blocked.is_claimable(FIXED_NOW + timedelta(days=1)) is False


def test_should_clear_lock_only_when_unclean_or_expired() -> None:
    active = Lock(
        name="schedule:nightly",
        owner="worker-a",
        acquired_at=FIXED_NOW,
        expires_at=FIXED_NOW + timedelta(seconds=60),
    )
    expired = Lock(
        name="schedule:nightly",
        owner="worker-a",
        acquired_at=FIXED_NOW - timedelta(seconds=120),
        expires_at=FIXED_NOW - timedelta(seconds=60),
    )
    assert should_clear_lock(active, now=FIXED_NOW, unclean_shutdown=True) is True
    assert should_clear_lock(active, now=FIXED_NOW, unclean_shutdown=False) is False
    assert should_clear_lock(expired, now=FIXED_NOW, unclean_shutdown=False) is True


def test_invalid_trigger_and_schema_version_fail_closed() -> None:
    assert coerce_trigger(None) is RecoveryTrigger.STARTUP
    assert coerce_trigger("MANUAL") is RecoveryTrigger.MANUAL
    with pytest.raises(RecoveryError) as trigger_error:
        coerce_trigger("SOMETHING")
    assert trigger_error.value.error.code == "RAD-WF-019"

    assert require_schema_version("1.0") == "1.0"
    with pytest.raises(RecoveryError) as schema_error:
        require_schema_version("2.0")
    assert schema_error.value.error.code == "RAD-WF-019"
