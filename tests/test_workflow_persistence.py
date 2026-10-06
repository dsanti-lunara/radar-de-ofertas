from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.application.capture_service import ManualCaptureService
from radar.application.evaluation_service import EvaluationService
from radar.application.workflow_service import WorkflowService
from radar.domain.allowed_claims import AllowedClaimsError
from radar.domain.capture import (
    CandidateState,
    CaptureIntake,
    CaptureSource,
    Marketplace,
)
from radar.domain.evaluation import ConfidenceFacts, DealFacts, Evaluation
from radar.domain.opportunity import (
    OPPORTUNITY_TRANSITION_INVALID,
    OpportunityError,
    OpportunityState,
)
from radar.domain.taxonomy import APPROVED_TAXONOMY, Brand
from radar.domain.workflow import (
    APPROVED_WORKFLOW_POLICY,
    REVALIDATION_REQUIRED,
    WorkflowError,
    WorkflowPolicy,
    build_workflow_policy,
)
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from radar.infrastructure.models import AuditEventRow, JobRow, OpportunityRow
from radar.infrastructure.opportunity_repository import SqlAlchemyWorkflowRepository

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now = self.now + timedelta(**kwargs)


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
    assert value is not None
    return int(value)


def _capture(engine: Engine, clock: _Clock, *, external_id: str = "MLB123") -> str:
    service = ManualCaptureService(
        repository=SqlAlchemyCaptureRepository(engine=engine), clock=clock
    )
    result = service.capture(
        CaptureIntake(
            marketplace=Marketplace.MERCADO_LIVRE,
            source=CaptureSource.BROWSER_EXTENSION,
            external_id=external_id,
            current_price="100.00",
            title="Produto",
            category="Perfumes",
            captured_at=clock(),
        ),
        correlation_id="cid-capture",
    )
    return result.candidate_id


def _evaluate(
    engine: Engine,
    clock: _Clock,
    candidate_id: str,
    *,
    deal: int,
    confidence: int,
) -> Evaluation:
    service = EvaluationService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        store=SqlAlchemyEvaluationRepository(engine=engine),
        taxonomy=APPROVED_TAXONOMY,
        clock=clock,
    )
    return service.evaluate(
        candidate_id,
        brand=Brand.RADAR_BEAUTY,
        deal=DealFacts(price_opportunity=deal, seller_quality=deal, demand=deal),
        confidence=ConfidenceFacts(
            source_reliability=confidence,
            freshness=confidence,
            completeness=confidence,
            price_history_depth=confidence,
            cross_validation=confidence,
        ),
        correlation_id="cid-eval",
    )


def _service(
    engine: Engine,
    clock: _Clock,
    policy: WorkflowPolicy = APPROVED_WORKFLOW_POLICY,
) -> WorkflowService:
    return WorkflowService(
        store=SqlAlchemyWorkflowRepository(engine=engine),
        evaluation_store=SqlAlchemyEvaluationRepository(engine=engine),
        policy=policy,
        clock=clock,
    )


def _approved_candidate(engine: Engine, clock: _Clock) -> str:
    candidate_id = _capture(engine, clock)
    _evaluate(engine, clock, candidate_id, deal=100, confidence=100)
    return candidate_id


def test_approved_candidate_creates_opportunity_and_next_job_atomically(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    result = service.advance(candidate_id, correlation_id="cid-adv")

    assert result.status == "OPPORTUNITY_CREATED"
    assert result.opportunity is not None
    assert result.opportunity.state is OpportunityState.LINK_PENDING
    assert result.opportunity.candidate_id == candidate_id
    assert result.next_job is not None
    assert result.next_job.type.value == "GENERATE_AFFILIATE_LINK"
    assert result.next_job.status.value == "PENDING"
    assert result.next_job.entity_type == "opportunity"
    assert result.next_job.entity_id == result.opportunity.opportunity_id
    assert result.next_job.locked_by is None

    assert _count(migrated_engine, "opportunity") == 1
    assert _count(migrated_engine, "job") == 1
    with Session(migrated_engine) as session:
        job_row = session.execute(select(JobRow)).scalar_one()
    assert job_row.status == "PENDING"
    assert job_row.locked_by is None

    opportunity, events = service.get(result.opportunity.opportunity_id)
    event_types = [event.event_type for event in events]
    assert "OPPORTUNITY_CREATED" in event_types
    assert "OPPORTUNITY_TRANSITIONED" in event_types
    assert "WORKFLOW_NEXT_JOB_ENQUEUED" in event_types
    assert all(event.correlation_id == "cid-adv" for event in events)
    assert opportunity.state is OpportunityState.LINK_PENDING


def test_rejected_candidate_never_creates_an_opportunity(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _capture(migrated_engine, clock)
    _evaluate(migrated_engine, clock, candidate_id, deal=0, confidence=100)
    service = _service(migrated_engine, clock)

    result = service.advance(candidate_id, correlation_id="cid-adv")

    assert result.status == "REJECTED"
    assert result.opportunity is None
    assert result.next_job is None
    assert _count(migrated_engine, "opportunity") == 0
    assert _count(migrated_engine, "job") == 0


def test_review_creates_human_action_and_preserves_the_old_evaluation(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _capture(migrated_engine, clock)
    review = _evaluate(migrated_engine, clock, candidate_id, deal=60, confidence=60)
    service = _service(migrated_engine, clock)

    result = service.advance(candidate_id, correlation_id="cid-review")

    assert result.status == "REVIEW_REQUIRED"
    assert result.opportunity is None
    assert result.human_action is not None
    assert result.human_action.action_type.value == "REVIEW_CANDIDATE"
    assert result.human_action.entity_id == candidate_id
    assert _count(migrated_engine, "opportunity") == 0
    assert _count(migrated_engine, "human_action") == 1

    # The old Evaluation is untouched; a later approval advances without rewriting it.
    clock.advance(seconds=1)
    approve = _evaluate(migrated_engine, clock, candidate_id, deal=100, confidence=100)
    assert approve.evaluation_id != review.evaluation_id
    advanced = service.advance(candidate_id, correlation_id="cid-adv")
    assert advanced.status == "OPPORTUNITY_CREATED"
    assert advanced.evaluation_id == approve.evaluation_id

    evaluations = SqlAlchemyEvaluationRepository(engine=migrated_engine).list_evaluations(
        candidate_id
    )
    assert [item.evaluation_id for item in evaluations] == [
        review.evaluation_id,
        approve.evaluation_id,
    ]
    assert evaluations[0].decision.value == "REVIEW"
    assert evaluations[1].decision.value == "APPROVE"


def test_invalid_transition_is_rejected_and_audited(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(migrated_engine, clock)
    service = _service(migrated_engine, clock)
    created = service.advance(candidate_id, correlation_id="cid-adv")
    assert created.opportunity is not None

    with pytest.raises(OpportunityError) as excinfo:
        service.transition(
            created.opportunity.opportunity_id,
            target_state="PUBLISHED",
            correlation_id="cid-bad",
        )
    assert excinfo.value.error.code == OPPORTUNITY_TRANSITION_INVALID

    _, events = service.get(created.opportunity.opportunity_id)
    rejected = [event for event in events if event.event_type == "OPPORTUNITY_TRANSITION_REJECTED"]
    assert len(rejected) == 1
    assert rejected[0].payload["target_state"] == "PUBLISHED"
    assert rejected[0].payload["current_state"] == "LINK_PENDING"
    assert rejected[0].correlation_id == "cid-bad"

    valid = service.transition(
        created.opportunity.opportunity_id,
        target_state="LINK_READY",
        correlation_id="cid-ok",
    )
    assert valid.state is OpportunityState.LINK_READY


def test_aged_candidate_requires_revalidation_before_the_next_step(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(migrated_engine, clock)
    policy = build_workflow_policy(
        {
            "schema_version": "1.0",
            "policy_version": "workflow-policy-ttl",
            "candidate_ttl_seconds": 3600,
        }
    )
    service = _service(migrated_engine, clock, policy)

    clock.advance(hours=2)
    with pytest.raises(WorkflowError) as excinfo:
        service.advance(candidate_id, correlation_id="cid-aged")

    assert excinfo.value.error.code == REVALIDATION_REQUIRED
    assert _count(migrated_engine, "opportunity") == 0
    assert _count(migrated_engine, "job") == 0


def test_advance_is_idempotent_for_the_same_evaluation(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    first = service.advance(candidate_id, correlation_id="cid-1")
    second = service.advance(candidate_id, correlation_id="cid-2")

    assert first.status == "OPPORTUNITY_CREATED"
    assert second.status == "OPPORTUNITY_EXISTS"
    assert first.opportunity is not None
    assert second.opportunity is not None
    assert second.opportunity.opportunity_id == first.opportunity.opportunity_id
    assert _count(migrated_engine, "opportunity") == 1
    assert _count(migrated_engine, "job") == 1


def test_advance_without_an_evaluation_fails_closed(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _capture(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    with pytest.raises(AllowedClaimsError) as excinfo:
        service.advance(candidate_id, correlation_id="cid-adv")

    assert excinfo.value.error.code == "RAD-CAP-013"
    assert _count(migrated_engine, "opportunity") == 0


def test_aged_opportunity_requires_revalidation_before_link_step(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(migrated_engine, clock)
    policy = build_workflow_policy(
        {
            "schema_version": "1.0",
            "policy_version": "workflow-policy-ttl",
            "opportunity_ttl_seconds": 3600,
        }
    )
    service = _service(migrated_engine, clock, policy)
    created = service.advance(candidate_id, correlation_id="cid-adv")
    assert created.opportunity is not None

    clock.advance(hours=2)
    with pytest.raises(WorkflowError) as excinfo:
        service.transition(
            created.opportunity.opportunity_id,
            target_state="LINK_READY",
            correlation_id="cid-aged",
        )
    assert excinfo.value.error.code == REVALIDATION_REQUIRED


def test_opportunity_foreign_keys_and_transition_audit(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(migrated_engine, clock)
    service = _service(migrated_engine, clock)
    created = service.advance(candidate_id, correlation_id="cid-adv")
    assert created.opportunity is not None

    with Session(migrated_engine) as session:
        row = session.get(OpportunityRow, created.opportunity.opportunity_id)
    assert row is not None
    assert row.candidate_id == candidate_id
    assert row.evaluation_id == created.evaluation_id
    assert row.state == "LINK_PENDING"

    with Session(migrated_engine) as session:
        audit_ids = set(
            session.execute(
                select(AuditEventRow.id).where(
                    AuditEventRow.entity_type == "opportunity",
                    AuditEventRow.entity_id == created.opportunity.opportunity_id,
                )
            )
            .scalars()
            .all()
        )
    assert row.audit_event_id in audit_ids

    # A Candidate created by the capture is never in a domain "processing" state.
    assert (
        SqlAlchemyWorkflowRepository(engine=migrated_engine).get_candidate_state(candidate_id)
        is CandidateState.NEW
    )
