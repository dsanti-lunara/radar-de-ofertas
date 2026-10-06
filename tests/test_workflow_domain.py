from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from radar.domain.capture import CandidateState
from radar.domain.evaluation import (
    ConfidenceFacts,
    DealFacts,
    Evaluation,
    build_evaluation,
)
from radar.domain.taxonomy import Brand
from radar.domain.workflow import (
    APPROVED_WORKFLOW_POLICY,
    REVALIDATION_REQUIRED,
    WORKFLOW_POLICY_INVALID,
    WorkflowError,
    WorkflowOutcome,
    WorkflowPolicy,
    build_workflow_policy,
    plan_advance,
)

pytestmark = pytest.mark.unit

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _evaluation(
    *,
    deal: int,
    confidence: int,
    created_at: datetime = FIXED_NOW,
    evaluation_id: str = "eval_1",
) -> Evaluation:
    return build_evaluation(
        evaluation_id=evaluation_id,
        candidate_id="cand_1",
        brand=Brand.RADAR_BEAUTY,
        deal=DealFacts(
            price_opportunity=deal,
            seller_quality=deal,
            demand=deal,
            brand_fit=deal,
        ),
        confidence=ConfidenceFacts(
            source_reliability=confidence,
            freshness=confidence,
            completeness=confidence,
            price_history_depth=confidence,
            cross_validation=confidence,
        ),
        correlation_id="cid-1",
        created_at=created_at,
        audit_event_id="aud_1",
    )


def _approved(created_at: datetime = FIXED_NOW) -> Evaluation:
    evaluation = _evaluation(deal=100, confidence=100, created_at=created_at)
    assert evaluation.decision.value == "APPROVE"
    return evaluation


def test_approved_candidate_plans_opportunity_and_next_job() -> None:
    plan = plan_advance(
        candidate_state=CandidateState.NEW,
        evaluation=_approved(),
        now=FIXED_NOW,
        policy=APPROVED_WORKFLOW_POLICY,
    )

    assert plan.outcome is WorkflowOutcome.CREATE_OPPORTUNITY
    assert plan.next_job_type is not None
    assert plan.next_job_type.value == "GENERATE_AFFILIATE_LINK"
    assert plan.next_state is not None
    assert plan.next_state.value == "LINK_PENDING"


def test_rejected_evaluation_never_plans_an_opportunity() -> None:
    plan = plan_advance(
        candidate_state=CandidateState.NEW,
        evaluation=_evaluation(deal=0, confidence=100),
        now=FIXED_NOW,
    )

    assert plan.outcome is WorkflowOutcome.REJECTED
    assert plan.next_job_type is None
    assert plan.next_state is None


def test_blocked_candidate_state_never_plans_an_opportunity() -> None:
    plan = plan_advance(
        candidate_state=CandidateState.REJECTED,
        evaluation=_approved(),
        now=FIXED_NOW,
    )

    assert plan.outcome is WorkflowOutcome.REJECTED


def test_review_requires_a_human_resolution() -> None:
    evaluation = _evaluation(deal=60, confidence=60)
    assert evaluation.decision.value == "REVIEW"

    plan = plan_advance(
        candidate_state=CandidateState.NEW,
        evaluation=evaluation,
        now=FIXED_NOW,
    )

    assert plan.outcome is WorkflowOutcome.REVIEW_REQUIRED
    assert plan.next_job_type is None


def test_aged_approved_evaluation_requires_revalidation() -> None:
    policy = build_workflow_policy(
        {
            "schema_version": "1.0",
            "policy_version": "workflow-policy-ttl",
            "candidate_ttl_seconds": 3600,
        }
    )
    aged = FIXED_NOW - timedelta(hours=2)

    with pytest.raises(WorkflowError) as excinfo:
        plan_advance(
            candidate_state=CandidateState.NEW,
            evaluation=_approved(created_at=aged),
            now=FIXED_NOW,
            policy=policy,
        )

    error = excinfo.value.error
    assert error.code == REVALIDATION_REQUIRED
    assert error.retryable is False
    assert error.context["age_seconds"] == 7200
    assert error.context["ttl_seconds"] == 3600


def test_fresh_approved_evaluation_passes_the_configured_ttl() -> None:
    policy = build_workflow_policy(
        {
            "schema_version": "1.0",
            "policy_version": "workflow-policy-ttl",
            "candidate_ttl_seconds": 3600,
        }
    )

    plan = plan_advance(
        candidate_state=CandidateState.NEW,
        evaluation=_approved(created_at=FIXED_NOW - timedelta(minutes=10)),
        now=FIXED_NOW,
        policy=policy,
    )

    assert plan.outcome is WorkflowOutcome.CREATE_OPPORTUNITY
    assert plan.ttl_configured is True


def test_approved_baseline_does_not_invent_a_ttl() -> None:
    assert APPROVED_WORKFLOW_POLICY.candidate_ttl_seconds is None
    assert APPROVED_WORKFLOW_POLICY.opportunity_ttl_seconds is None
    assert APPROVED_WORKFLOW_POLICY.candidate_ttl_configured is False

    # Without a configured TTL the gate is off, so an old approval still plans.
    plan = plan_advance(
        candidate_state=CandidateState.NEW,
        evaluation=_approved(created_at=FIXED_NOW - timedelta(days=30)),
        now=FIXED_NOW,
    )
    assert plan.outcome is WorkflowOutcome.CREATE_OPPORTUNITY
    assert plan.ttl_configured is False


def test_policy_is_versioned_and_hashed() -> None:
    first = build_workflow_policy(
        {"schema_version": "1.0", "policy_version": "v1", "candidate_ttl_seconds": 3600}
    )
    second = build_workflow_policy(
        {"schema_version": "1.0", "policy_version": "v1", "candidate_ttl_seconds": 3600}
    )
    changed = build_workflow_policy(
        {"schema_version": "1.0", "policy_version": "v1", "candidate_ttl_seconds": 7200}
    )

    assert first.content_hash == second.content_hash
    assert first.content_hash != changed.content_hash
    assert first.to_contract()["candidate_ttl_seconds"] == 3600


def test_invalid_policy_fails_closed() -> None:
    with pytest.raises(WorkflowError) as missing:
        build_workflow_policy({"schema_version": "1.0"})
    assert missing.value.error.code == WORKFLOW_POLICY_INVALID

    with pytest.raises(WorkflowError) as bad_ttl:
        build_workflow_policy(
            {"schema_version": "1.0", "policy_version": "v1", "candidate_ttl_seconds": 0}
        )
    assert bad_ttl.value.error.code == WORKFLOW_POLICY_INVALID

    with pytest.raises(WorkflowError) as bad_schema:
        build_workflow_policy({"schema_version": "9.9", "policy_version": "v1"})
    assert bad_schema.value.error.code == WORKFLOW_POLICY_INVALID


def test_policy_aging_helpers_are_explicit() -> None:
    policy = WorkflowPolicy(
        policy_version="v1",
        content_hash="hash",
        candidate_ttl_seconds=60,
        opportunity_ttl_seconds=120,
    )

    assert policy.candidate_is_aged(created_at=FIXED_NOW - timedelta(seconds=61), now=FIXED_NOW)
    assert not policy.candidate_is_aged(created_at=FIXED_NOW - timedelta(seconds=60), now=FIXED_NOW)
    assert policy.opportunity_is_aged(created_at=FIXED_NOW - timedelta(seconds=121), now=FIXED_NOW)
