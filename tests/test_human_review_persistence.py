from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.application.ai_review_service import AIReviewService
from radar.application.allowed_claims_service import AllowedClaimsService
from radar.application.capture_service import ManualCaptureService
from radar.application.evaluation_service import EvaluationService
from radar.application.review_service import ReviewService
from radar.domain.capture import CaptureIntake, CaptureSource, Marketplace
from radar.domain.evaluation import ConfidenceFacts, DealFacts, Evaluation
from radar.domain.human_review import HumanDecision, HumanReviewError
from radar.domain.knowledge import APPROVED_KNOWLEDGE_PACK, Channel
from radar.domain.operations import (
    APPROVED_AUTOMATION_POLICY,
    DEFAULT_OPERATIONAL_STATE,
    AutomationMode,
    build_compliance_policy,
)
from radar.domain.taxonomy import APPROVED_TAXONOMY, Brand
from radar.infrastructure.ai_provider import FakeAIProvider
from radar.infrastructure.ai_review_repository import SqlAlchemyAIReviewRepository
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from radar.infrastructure.human_review_repository import SqlAlchemyHumanReviewRepository
from radar.infrastructure.models import HumanReviewRow

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

#: An ACTIVE compliance policy isolates the automation-mode decision from the
#: compliance gate, so the SHADOW block is observable on its own.
ACTIVE_COMPLIANCE_POLICY = build_compliance_policy(
    {"policy_version": "compliance-active", "status": "ACTIVE"}
)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now = self.now + timedelta(**kwargs)


def _capture(engine: Engine, clock: _Clock, *, title: str = "Perfume") -> str:
    service = ManualCaptureService(
        repository=SqlAlchemyCaptureRepository(engine=engine), clock=clock
    )
    result = service.capture(
        CaptureIntake(
            marketplace=Marketplace.MERCADO_LIVRE,
            source=CaptureSource.BROWSER_EXTENSION,
            external_id="MLB-REVIEW",
            current_price="80.00",
            title=title,
            category="Perfumes",
            captured_at=clock(),
        ),
        correlation_id="cid-capture",
    )
    return result.candidate_id


def _evaluate(engine: Engine, clock: _Clock, candidate_id: str) -> Evaluation:
    service = EvaluationService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        store=SqlAlchemyEvaluationRepository(engine=engine),
        taxonomy=APPROVED_TAXONOMY,
        clock=clock,
    )
    return service.evaluate(
        candidate_id,
        brand=Brand.RADAR_BEAUTY,
        deal=DealFacts(price_opportunity=100, seller_quality=100, demand=100),
        confidence=ConfidenceFacts(
            source_reliability=100,
            freshness=100,
            completeness=100,
            price_history_depth=100,
            cross_validation=100,
        ),
        correlation_id="cid-eval",
    )


def _ai_review(engine: Engine, clock: _Clock, candidate_id: str) -> None:
    capture = SqlAlchemyCaptureRepository(engine=engine)
    evaluations = SqlAlchemyEvaluationRepository(engine=engine)
    service = AIReviewService(
        repository=SqlAlchemyAIReviewRepository(engine=engine),
        capture=capture,
        evaluations=evaluations,
        claims=AllowedClaimsService(repository=capture, evaluations=evaluations),
        knowledge=APPROVED_KNOWLEDGE_PACK,
        provider=FakeAIProvider(),
        clock=clock,
    )
    service.review(candidate_id, channel=Channel.TELEGRAM, correlation_id="cid-ai")


def _service(engine: Engine, clock: _Clock) -> ReviewService:
    return ReviewService(
        store=SqlAlchemyHumanReviewRepository(engine=engine),
        automation_policy=APPROVED_AUTOMATION_POLICY,
        compliance_policy=ACTIVE_COMPLIANCE_POLICY,
        operational_state=lambda: DEFAULT_OPERATIONAL_STATE,
        clock=clock,
    )


def _candidate(engine: Engine, clock: _Clock) -> str:
    candidate_id = _capture(engine, clock)
    _evaluate(engine, clock, candidate_id)
    _ai_review(engine, clock, candidate_id)
    return candidate_id


def test_register_snapshots_the_latest_ai_decision_and_reason(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _candidate(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    result = service.register(
        candidate_id,
        human_decision="APPROVE",
        reason="Preço confere com a evidência",
        correlation_id="cid-review",
    )

    review = result.review
    assert review.ai_decision == "APPROVE"
    assert review.ai_review_id is not None
    assert review.human_decision is HumanDecision.APPROVE
    assert review.correlation_id == "cid-review"
    assert result.to_contract()["publication_authorized"] is False
    assert result.automation.publish_allowed is False
    assert result.automation.publish_reason_code == "SHADOW_NO_COMMERCIAL_SEND"

    with Session(migrated_engine) as session:
        row = session.get(HumanReviewRow, review.human_review_id)
        assert row is not None
        assert row.ai_decision == "APPROVE"
        assert row.human_decision == "APPROVE"
        assert row.reason == "Preço confere com a evidência"


def test_register_edit_content_persists_the_sanitized_snapshot(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _candidate(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    result = service.register(
        candidate_id,
        human_decision="EDIT_CONTENT",
        reason="Ajustar o CTA",
        edited_content={"headline": "Oferta", "body": "Corpo", "cta": "Comprar"},
        correlation_id="cid-edit",
    )

    stored = service.get_review(result.review.human_review_id)
    assert stored.human_decision is HumanDecision.EDIT_CONTENT
    assert stored.edited_content is not None
    assert stored.edited_content.cta == "Comprar"


def test_review_is_append_only_and_never_creates_a_publication(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _candidate(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    first = service.register(
        candidate_id, human_decision="APPROVE", reason="ok", correlation_id="cid-1"
    )
    clock.advance(minutes=1)
    second = service.register(
        candidate_id, human_decision="REJECT", reason="mudou", correlation_id="cid-2"
    )

    reviews = service.list_reviews(candidate_id)
    assert [item.human_review_id for item in reviews] == [
        first.review.human_review_id,
        second.review.human_review_id,
    ]

    tables = set(inspect(migrated_engine).get_table_names())
    with Session(migrated_engine) as session:
        assert session.execute(select(HumanReviewRow)).scalars().all()
    # Candidate approval is not a publication approval: no send artifact exists.
    assert "publication" in tables
    with migrated_engine.connect() as connection:
        publications = connection.exec_driver_sql("SELECT COUNT(*) FROM publication").scalar()
    assert publications == 0


def test_invalid_review_writes_nothing(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _candidate(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    with pytest.raises(HumanReviewError):
        service.register(
            candidate_id, human_decision="PUBLISH", reason="?", correlation_id="cid-bad"
        )

    with migrated_engine.connect() as connection:
        count = connection.exec_driver_sql("SELECT COUNT(*) FROM human_review").scalar()
    assert count == 0


def test_inbox_and_detail_use_real_persisted_data(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _candidate(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    inbox = service.inbox()
    assert len(inbox) == 1
    item = inbox[0]
    assert item.candidate_id == candidate_id
    assert item.marketplace == "MERCADO_LIVRE"
    assert item.current_price == "80.00"
    assert item.deal_score == "100.00"
    assert item.decision == "APPROVE"
    assert item.ai_decision == "APPROVE"
    assert item.human_decision is None

    detail = service.detail(candidate_id)
    assert detail.evaluation is not None
    assert detail.candidate["external_id"] == "MLB-REVIEW"
    assert len(detail.price_history) >= 1
    assert len(detail.evidence) >= 1
    assert detail.versions.scoring_version is not None
    assert detail.versions.ai_knowledge_version == APPROVED_KNOWLEDGE_PACK.knowledge_version
    event_types = {entry.event_type for entry in detail.timeline}
    assert {"CAPTURE_RECEIVED", "EVALUATION_RECORDED", "AI_REVIEW_RECORDED"} <= event_types


def test_detail_and_listing_fail_closed_for_unknown_candidate(migrated_engine: Engine) -> None:
    service = _service(migrated_engine, _Clock(FIXED_NOW))

    with pytest.raises(HumanReviewError) as detail_error:
        service.detail("cand_missing")
    assert detail_error.value.error.code == "RAD-UI-003"

    with pytest.raises(HumanReviewError):
        service.list_reviews("cand_missing")


def test_shadow_accepts_a_review_but_never_allows_a_send(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _candidate(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    result = service.register(
        candidate_id, human_decision="APPROVE", reason="ok", correlation_id="cid-shadow"
    )

    assert result.automation.automation_mode == AutomationMode.SHADOW.value
    assert result.automation.publish_allowed is False
    assert result.review.publication_authorized is False
    # The review itself was persisted even though the send stays blocked.
    assert service.get_review(result.review.human_review_id).human_review_id
