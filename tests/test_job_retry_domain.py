from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from radar.domain.human_action import HumanActionType
from radar.domain.job import (
    JOB_INPUT_INVALID,
    JOB_LEASE_NOT_HELD,
    JobError,
    JobStatus,
    create_job,
)
from radar.domain.retry import (
    APPROVED_RETRY_POLICY,
    JOB_DEAD,
    RETRY_POLICY_INVALID,
    FailureAction,
    FailureClass,
    RetryError,
    RetryPolicy,
    apply_failure,
    build_retry_policy,
    classify_failure,
    resolve_failure,
)

pytestmark = pytest.mark.unit

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _id_factory(prefix: str) -> str:
    return f"{prefix}_test"


def _claimed_job(*, attempts: int = 1, max_attempts: int = 3):
    job = create_job(
        job_type="NORMALIZE_CAPTURE",
        correlation_id="cid-1",
        now=FIXED_NOW,
        max_attempts=max_attempts,
        id_factory=_id_factory,
    )
    return replace(
        job,
        status=JobStatus.CLAIMED,
        attempts=attempts,
        locked_by="worker-a",
        locked_at=FIXED_NOW,
        lease_expires_at=FIXED_NOW + timedelta(seconds=60),
    )


def test_transient_uses_configured_backoff_and_attempt_limit() -> None:
    policy = APPROVED_RETRY_POLICY
    assert policy.backoff_seconds == (30, 120, 600, 1800)

    first = resolve_failure(
        _claimed_job(attempts=1), error_code="RAD-WF-001", now=FIXED_NOW, policy=policy
    )
    assert first.failure_class is FailureClass.TRANSIENT
    assert first.action is FailureAction.RETRY_WAIT
    assert first.retryable is True
    assert first.delay_seconds == 30
    assert first.available_at == FIXED_NOW + timedelta(seconds=30)
    assert first.human_action_type is None

    second = resolve_failure(
        _claimed_job(attempts=2), error_code="RAD-WF-001", now=FIXED_NOW, policy=policy
    )
    assert second.delay_seconds == 120
    assert second.available_at == FIXED_NOW + timedelta(seconds=120)


def test_transient_exhaustion_produces_dead_and_dead_job_review() -> None:
    resolution = resolve_failure(
        _claimed_job(attempts=3, max_attempts=3),
        error_code="RAD-WF-002",
        now=FIXED_NOW,
        policy=APPROVED_RETRY_POLICY,
    )
    assert resolution.failure_class is FailureClass.TRANSIENT
    assert resolution.action is FailureAction.DEAD
    assert resolution.retryable is False
    assert resolution.delay_seconds is None
    assert resolution.available_at is None
    assert resolution.human_action_type is HumanActionType.DEAD_JOB_REVIEW
    assert resolution.resolution_code == JOB_DEAD


def test_auth_required_and_human_required_do_not_loop() -> None:
    auth = resolve_failure(
        _claimed_job(attempts=1),
        error_code="RAD-AI-001",
        now=FIXED_NOW,
        policy=APPROVED_RETRY_POLICY,
    )
    assert auth.failure_class is FailureClass.HUMAN_REQUIRED
    assert auth.action is FailureAction.DEAD
    assert auth.retryable is False
    assert auth.delay_seconds is None
    assert auth.human_action_type is HumanActionType.RESTORE_AI_AUTH

    marketplace_auth = resolve_failure(
        _claimed_job(attempts=1),
        error_code="RAD-WA-001",
        now=FIXED_NOW,
        policy=APPROVED_RETRY_POLICY,
    )
    assert marketplace_auth.action is FailureAction.DEAD
    assert marketplace_auth.human_action_type is HumanActionType.AUTHENTICATE_MARKETPLACE

    human_required = resolve_failure(
        _claimed_job(attempts=1),
        error_code="RAD-CMP-002",
        now=FIXED_NOW,
        policy=APPROVED_RETRY_POLICY,
    )
    assert human_required.failure_class is FailureClass.HUMAN_REQUIRED
    assert human_required.action is FailureAction.DEAD
    assert human_required.human_action_type is HumanActionType.DEAD_JOB_REVIEW


def test_permanent_never_gets_automatic_retry() -> None:
    resolution = resolve_failure(
        _claimed_job(attempts=1),
        error_code="RAD-CAP-004",
        now=FIXED_NOW,
        policy=APPROVED_RETRY_POLICY,
    )
    assert resolution.failure_class is FailureClass.PERMANENT
    assert resolution.action is FailureAction.FAILED
    assert resolution.retryable is False
    assert resolution.delay_seconds is None
    assert resolution.human_action_type is None


def test_unknown_error_fails_closed_as_permanent() -> None:
    assert classify_failure("RAD-XX-999") is FailureClass.PERMANENT
    assert classify_failure("not-a-catalog-code") is FailureClass.PERMANENT


def test_invalid_error_code_is_rejected() -> None:
    with pytest.raises(RetryError) as excinfo:
        classify_failure("")
    assert excinfo.value.error.code == JOB_INPUT_INVALID

    with pytest.raises(RetryError):
        classify_failure(None)  # type: ignore[arg-type]


def test_retry_policy_builds_and_validates() -> None:
    policy = build_retry_policy(
        {"schema_version": "1.0", "policy_version": "p", "backoff_seconds": [5, 10]}
    )
    assert policy.delay_for(1) == 5
    assert policy.delay_for(2) == 10
    # Clamps to the last configured value; the attempt budget still bounds the loop.
    assert policy.delay_for(9) == 10
    assert policy.to_contract()["backoff_seconds"] == [5, 10]

    with pytest.raises(RetryError) as excinfo:
        build_retry_policy({"schema_version": "1.0", "policy_version": "p", "backoff_seconds": []})
    assert excinfo.value.error.code == RETRY_POLICY_INVALID

    with pytest.raises(RetryError):
        build_retry_policy({"policy_version": "p", "backoff_seconds": [0]})
    with pytest.raises(RetryError):
        build_retry_policy({"policy_version": "p", "backoff_seconds": [True]})
    with pytest.raises(RetryError):
        build_retry_policy({"schema_version": "9.9", "policy_version": "p"})
    with pytest.raises(RetryError):
        build_retry_policy({"backoff_seconds": [5]})

    empty = RetryPolicy(policy_version="p", content_hash="h", backoff_seconds=())
    with pytest.raises(RetryError):
        empty.delay_for(1)


def test_apply_failure_requires_the_lease_owner() -> None:
    job = _claimed_job(attempts=1)
    resolution = resolve_failure(
        job, error_code="RAD-WF-001", now=FIXED_NOW, policy=APPROVED_RETRY_POLICY
    )

    with pytest.raises(JobError) as excinfo:
        apply_failure(job, resolution, worker_id="worker-b", now=FIXED_NOW)
    assert excinfo.value.error.code == JOB_LEASE_NOT_HELD

    with pytest.raises(JobError) as expired:
        apply_failure(job, resolution, worker_id="worker-a", now=FIXED_NOW + timedelta(seconds=61))
    assert expired.value.error.code == JOB_LEASE_NOT_HELD

    transitioned = apply_failure(job, resolution, worker_id="worker-a", now=FIXED_NOW)
    assert transitioned.status is JobStatus.RETRY_WAIT
    assert transitioned.locked_by is None
    assert transitioned.lease_expires_at is None
    assert transitioned.available_at == FIXED_NOW + timedelta(seconds=30)
