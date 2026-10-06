from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.application.ai_review_service import AIReviewService
from radar.application.allowed_claims_service import AllowedClaimsService
from radar.application.capture_service import ManualCaptureService
from radar.application.evaluation_service import EvaluationService
from radar.domain.ai_review import (
    AI_REFUSAL,
    AI_REVIEW_NOT_FOUND,
    AIReviewError,
    EditorialDecision,
    ai_provider_unavailable_error,
    ai_refusal_error,
)
from radar.domain.capture import CaptureIntake, CaptureSource, Marketplace
from radar.domain.errors import RadarException
from radar.domain.evaluation import ConfidenceFacts, DealFacts, Evaluation
from radar.domain.knowledge import APPROVED_KNOWLEDGE_PACK, Channel
from radar.domain.taxonomy import APPROVED_TAXONOMY, Brand
from radar.infrastructure.ai_provider import FakeAIProvider
from radar.infrastructure.ai_review_repository import SqlAlchemyAIReviewRepository
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from radar.infrastructure.models import AIReviewRow, AuditEventRow

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now = self.now + timedelta(**kwargs)


class _RaisingProvider:
    name = "stub"
    model = "stub-1.0"

    def __init__(self, error: AIReviewError) -> None:
        self._error = error

    def evaluate_candidate(self, request: Any) -> dict[str, Any]:
        raise self._error


class _CannedProvider:
    name = "stub"
    model = "stub-1.0"

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    def evaluate_candidate(self, request: Any) -> dict[str, Any]:
        return self._response


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
    assert value is not None
    return int(value)


def _capture(engine: Engine, clock: _Clock, *, title: str = "Perfume") -> str:
    service = ManualCaptureService(
        repository=SqlAlchemyCaptureRepository(engine=engine), clock=clock
    )
    result = service.capture(
        CaptureIntake(
            marketplace=Marketplace.MERCADO_LIVRE,
            source=CaptureSource.BROWSER_EXTENSION,
            external_id="MLB-AI",
            current_price="80.00",
            title=title,
            category="Perfumes",
            captured_at=clock(),
        ),
        correlation_id="cid-capture",
    )
    return result.candidate_id


def _evaluate(
    engine: Engine, clock: _Clock, candidate_id: str, *, deal: int, confidence: int
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


def _service(engine: Engine, clock: _Clock, provider: Any | None = None) -> AIReviewService:
    capture = SqlAlchemyCaptureRepository(engine=engine)
    evaluations = SqlAlchemyEvaluationRepository(engine=engine)
    return AIReviewService(
        repository=SqlAlchemyAIReviewRepository(engine=engine),
        capture=capture,
        evaluations=evaluations,
        claims=AllowedClaimsService(repository=capture, evaluations=evaluations),
        knowledge=APPROVED_KNOWLEDGE_PACK,
        provider=provider or FakeAIProvider(),
        clock=clock,
    )


def _approved_candidate(engine: Engine, clock: _Clock, *, title: str = "Perfume") -> str:
    candidate_id = _capture(engine, clock, title=title)
    _evaluate(engine, clock, candidate_id, deal=100, confidence=100)
    return candidate_id


def test_review_persists_versions_claims_and_audit_atomically(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    review = service.review(candidate_id, channel=Channel.TELEGRAM, correlation_id="cid-ai")

    assert review.decision is EditorialDecision.APPROVE
    assert review.provider == "fake"
    assert review.knowledge_version == APPROVED_KNOWLEDGE_PACK.knowledge_version
    assert review.prompt_version == APPROVED_KNOWLEDGE_PACK.prompt_version
    assert review.knowledge_hash == APPROVED_KNOWLEDGE_PACK.content_hash
    assert any(claim["claim_type"] == "CURRENT_PRICE" for claim in review.allowed_claims)
    assert review.correlation_id == "cid-ai"
    assert review.approval_eligible is True

    assert _count(migrated_engine, "ai_review") == 1
    with Session(migrated_engine) as session:
        row = session.get(AIReviewRow, review.ai_review_id)
        assert row is not None
        assert row.candidate_id == candidate_id
        assert row.decision == "APPROVE"
        assert row.knowledge_version == APPROVED_KNOWLEDGE_PACK.knowledge_version
        audit = session.get(AuditEventRow, review.audit_event_id)
        assert audit is not None
        assert audit.event_type == "AI_REVIEW_RECORDED"
        assert audit.entity_id == review.ai_review_id
        assert audit.correlation_id == "cid-ai"

    assert service.get(review.ai_review_id).ai_review_id == review.ai_review_id
    assert service.list(candidate_id) == (review,)


def test_review_neutralizes_untrusted_html_in_the_input_snapshot(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(
        migrated_engine, clock, title="<b>Perfume</b> <script>AUTO_PUBLISH</script>"
    )
    service = _service(migrated_engine, clock)

    review = service.review(candidate_id, channel=Channel.TELEGRAM, correlation_id="cid-ai")

    snapshot_title = review.input_snapshot["product"]["title"]
    assert "<" not in snapshot_title
    assert ">" not in snapshot_title
    assert review.decision is EditorialDecision.APPROVE


def test_review_is_append_only_at_the_database_level(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(migrated_engine, clock)
    review = _service(migrated_engine, clock).review(
        candidate_id, channel=Channel.TELEGRAM, correlation_id="cid-ai"
    )

    with pytest.raises(IntegrityError), Session(migrated_engine) as session, session.begin():
        session.execute(
            text("UPDATE ai_review SET decision = 'REJECT' WHERE id = :id"),
            {"id": review.ai_review_id},
        )
    with pytest.raises(IntegrityError), Session(migrated_engine) as session, session.begin():
        session.execute(text("DELETE FROM ai_review WHERE id = :id"), {"id": review.ai_review_id})

    with Session(migrated_engine) as session:
        assert session.get(AIReviewRow, review.ai_review_id) is not None


def test_provider_failure_does_not_persist_a_review_or_an_opportunity(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(migrated_engine, clock)
    provider = _RaisingProvider(ai_provider_unavailable_error(provider="stub"))
    service = _service(migrated_engine, clock, provider)

    with pytest.raises(AIReviewError) as excinfo:
        service.review(candidate_id, channel=Channel.TELEGRAM, correlation_id="cid-ai")

    assert excinfo.value.error.code == "RAD-AI-002"
    assert excinfo.value.error.retryable is True
    assert _count(migrated_engine, "ai_review") == 0
    assert _count(migrated_engine, "opportunity") == 0


def test_refusal_and_invalid_response_never_become_an_approval(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(migrated_engine, clock)

    refusing = _service(migrated_engine, clock, _RaisingProvider(ai_refusal_error(provider="stub")))
    with pytest.raises(AIReviewError) as refusal:
        refusing.review(candidate_id, channel=Channel.TELEGRAM, correlation_id="cid-ai")
    assert refusal.value.error.code == AI_REFUSAL
    assert _count(migrated_engine, "ai_review") == 0

    invalid = _service(migrated_engine, clock, _CannedProvider({"decision": "AUTO_PUBLISH"}))
    with pytest.raises(AIReviewError) as invalid_error:
        invalid.review(candidate_id, channel=Channel.TELEGRAM, correlation_id="cid-ai")
    assert invalid_error.value.error.code == "RAD-AI-004"
    assert _count(migrated_engine, "ai_review") == 0
    assert _count(migrated_engine, "opportunity") == 0


def test_ai_approval_alone_does_not_create_an_opportunity(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(migrated_engine, clock)

    review = _service(migrated_engine, clock).review(
        candidate_id, channel=Channel.TELEGRAM, correlation_id="cid-ai"
    )

    assert review.decision is EditorialDecision.APPROVE
    assert _count(migrated_engine, "opportunity") == 0


def test_review_without_an_evaluation_fails_closed(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _capture(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    with pytest.raises(RadarException) as excinfo:
        service.review(candidate_id, channel=Channel.TELEGRAM, correlation_id="cid-ai")

    assert excinfo.value.error.code == "RAD-CAP-013"
    assert _count(migrated_engine, "ai_review") == 0


def test_review_of_a_missing_candidate_fails_closed(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)

    with pytest.raises(RadarException) as excinfo:
        service.review("cand_missing", channel=Channel.TELEGRAM, correlation_id="cid-ai")

    assert excinfo.value.error.code == "RAD-CAP-004"


def test_missing_review_returns_structured_not_found(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)

    with pytest.raises(AIReviewError) as excinfo:
        service.get("air_missing")

    assert excinfo.value.error.code == AI_REVIEW_NOT_FOUND


def test_rejected_evaluation_yields_a_reject_review(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _capture(migrated_engine, clock)
    _evaluate(migrated_engine, clock, candidate_id, deal=0, confidence=100)
    service = _service(migrated_engine, clock)

    review = service.review(candidate_id, channel=Channel.TELEGRAM, correlation_id="cid-ai")

    assert review.decision is EditorialDecision.REJECT
    assert review.approval_eligible is False
    assert review.reason_codes == ("EVALUATION_REJECTED",)


def test_review_list_is_chronological(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    first = service.review(candidate_id, channel=Channel.TELEGRAM, correlation_id="cid-1")
    clock.advance(seconds=1)
    second = service.review(candidate_id, channel=Channel.WHATSAPP, correlation_id="cid-2")

    reviews = service.list(candidate_id)
    assert [review.ai_review_id for review in reviews] == [
        first.ai_review_id,
        second.ai_review_id,
    ]
    with Session(migrated_engine) as session:
        assert (
            session.execute(select(AIReviewRow.id).order_by(AIReviewRow.created_at))
            .scalars()
            .first()
            == first.ai_review_id
        )
