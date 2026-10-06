from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.application.affiliate_link_service import AffiliateLinkService
from radar.application.allowed_claims_service import AllowedClaimsService
from radar.application.capture_service import ManualCaptureService
from radar.application.content_service import ContentGenerationService
from radar.application.evaluation_service import EvaluationService
from radar.application.workflow_service import WorkflowService
from radar.domain.capture import CaptureIntake, CaptureSource, Marketplace
from radar.domain.content import (
    CONTENT_GENERATION_NOT_FOUND,
    CONTENT_INPUT_INVALID,
    CONTENT_URL_NOT_ALLOWED,
    UNSUPPORTED_NUMERIC_CLAIM,
    ContentGenerationError,
)
from radar.domain.errors import RadarException
from radar.domain.evaluation import ConfidenceFacts, DealFacts
from radar.domain.knowledge import APPROVED_KNOWLEDGE_PACK, Channel
from radar.domain.operations import APPROVED_COMPLIANCE_POLICY
from radar.domain.taxonomy import APPROVED_TAXONOMY, Brand
from radar.domain.tracking import build_tracking_label_mapping
from radar.infrastructure.affiliate_link_provider import FakeAffiliateLinkProvider
from radar.infrastructure.affiliate_link_repository import SqlAlchemyAffiliateLinkRepository
from radar.infrastructure.ai_provider import FakeAIProvider
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.content_repository import SqlAlchemyContentGenerationRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from radar.infrastructure.models import AuditEventRow, ContentGenerationRow
from radar.infrastructure.opportunity_repository import SqlAlchemyWorkflowRepository

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
INTERNAL_REFERENCE = "RADAR_BEAUTY:MERCADO_LIVRE"


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: int) -> None:
        self.now = self.now + timedelta(**kwargs)


class _CannedContentProvider:
    name = "stub"

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    def generate_content(self, request: Any) -> dict[str, Any]:
        return self._response


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
    assert value is not None
    return int(value)


def _mapping() -> Any:
    return build_tracking_label_mapping(
        {
            "schema_version": "1.0",
            "mapping_version": "tracking-labels-test",
            "entries": [
                {
                    "internal_reference": INTERNAL_REFERENCE,
                    "marketplace": "MERCADO_LIVRE",
                    "label": "rbtgoffer",
                }
            ],
        }
    )


def _capture(engine: Engine, clock: _Clock, *, price: str = "80.00") -> str:
    service = ManualCaptureService(
        repository=SqlAlchemyCaptureRepository(engine=engine), clock=clock
    )
    result = service.capture(
        CaptureIntake(
            marketplace=Marketplace.MERCADO_LIVRE,
            source=CaptureSource.BROWSER_EXTENSION,
            external_id="MLB-CT",
            current_price=price,
            title="Perfume",
            url="https://www.mercadolivre.com.br/p/MLB-CT",
            category="Perfumes",
            captured_at=clock(),
        ),
        correlation_id="cid-capture",
    )
    return result.candidate_id


def _evaluate(engine: Engine, clock: _Clock, candidate_id: str, *, score: int) -> None:
    EvaluationService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        store=SqlAlchemyEvaluationRepository(engine=engine),
        taxonomy=APPROVED_TAXONOMY,
        clock=clock,
    ).evaluate(
        candidate_id,
        brand=Brand.RADAR_BEAUTY,
        deal=DealFacts(price_opportunity=score, seller_quality=score, demand=score),
        confidence=ConfidenceFacts(
            source_reliability=score,
            freshness=score,
            completeness=score,
            price_history_depth=score,
            cross_validation=score,
        ),
        correlation_id="cid-eval",
    )


def _opportunity_id(engine: Engine, candidate_id: str) -> str:
    opportunities = SqlAlchemyWorkflowRepository(engine=engine).list_opportunities(candidate_id)
    assert opportunities
    return opportunities[-1].opportunity_id


def _link_service(engine: Engine, clock: _Clock) -> AffiliateLinkService:
    repository = SqlAlchemyAffiliateLinkRepository(engine=engine)
    return AffiliateLinkService(
        repository=repository,
        capture=repository,
        evaluations=SqlAlchemyEvaluationRepository(engine=engine),
        opportunities=SqlAlchemyWorkflowRepository(engine=engine),
        tracking_labels=_mapping(),
        provider=FakeAffiliateLinkProvider(),
        clock=clock,
    )


def _content_service(
    engine: Engine, clock: _Clock, *, provider: Any | None = None
) -> ContentGenerationService:
    capture = SqlAlchemyCaptureRepository(engine=engine)
    evaluations = SqlAlchemyEvaluationRepository(engine=engine)
    return ContentGenerationService(
        repository=SqlAlchemyContentGenerationRepository(engine=engine),
        opportunities=SqlAlchemyWorkflowRepository(engine=engine),
        capture=capture,
        evaluations=evaluations,
        claims=AllowedClaimsService(repository=capture, evaluations=evaluations),
        links=SqlAlchemyAffiliateLinkRepository(engine=engine),
        price_history=capture,
        knowledge=APPROVED_KNOWLEDGE_PACK,
        provider=provider or FakeAIProvider(),
        compliance=APPROVED_COMPLIANCE_POLICY,
        clock=clock,
    )


def _ready_opportunity(engine: Engine, clock: _Clock) -> tuple[str, str]:
    candidate_id = _capture(engine, clock)
    _evaluate(engine, clock, candidate_id, score=100)
    WorkflowService(
        store=SqlAlchemyWorkflowRepository(engine=engine),
        evaluation_store=SqlAlchemyEvaluationRepository(engine=engine),
    ).advance(candidate_id, correlation_id="cid-adv")
    opportunity_id = _opportunity_id(engine, candidate_id)
    _link_service(engine, clock).generate(candidate_id, correlation_id="cid-link")
    return candidate_id, opportunity_id


def test_content_is_persisted_with_audit_and_queryable(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id, opportunity_id = _ready_opportunity(migrated_engine, clock)
    service = _content_service(migrated_engine, clock)

    record = service.generate(opportunity_id, channel=Channel.TELEGRAM, correlation_id="cid-ctg")

    assert record.generated.headline.startswith("Radar Beauty")
    assert "80.00" in record.generated.body
    assert record.rendered.price == "80.00"
    assert record.rendered.price_display == "80,00"
    assert record.rendered.affiliate_url.endswith("matt_word=rbtgoffer")
    assert record.rendered.disclosure in record.rendered.text
    assert record.knowledge_version == APPROVED_KNOWLEDGE_PACK.knowledge_version
    assert record.correlation_id == "cid-ctg"

    assert _count(migrated_engine, "content_generation") == 1
    with Session(migrated_engine) as session:
        row = session.get(ContentGenerationRow, record.content_generation_id)
        assert row is not None
        assert row.opportunity_id == opportunity_id
        assert row.candidate_id == candidate_id
        assert row.channel == "TELEGRAM"
        assert row.status == "VALIDATED"
        audit = session.get(AuditEventRow, record.audit_event_id)
        assert audit is not None
        assert audit.event_type == "CONTENT_GENERATION_RECORDED"
        assert audit.entity_id == record.content_generation_id

    assert service.get(record.content_generation_id) == record
    assert service.list(opportunity_id) == (record,)


def test_content_is_append_only_at_the_database_level(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    _, opportunity_id = _ready_opportunity(migrated_engine, clock)
    record = _content_service(migrated_engine, clock).generate(
        opportunity_id, channel=Channel.TELEGRAM, correlation_id="cid-ctg"
    )

    with pytest.raises(IntegrityError), Session(migrated_engine) as session, session.begin():
        session.execute(
            text("UPDATE content_generation SET status = 'STALE' WHERE id = :id"),
            {"id": record.content_generation_id},
        )
    with pytest.raises(IntegrityError), Session(migrated_engine) as session, session.begin():
        session.execute(
            text("DELETE FROM content_generation WHERE id = :id"),
            {"id": record.content_generation_id},
        )


def test_content_becomes_stale_when_a_new_price_observation_appears(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    _, opportunity_id = _ready_opportunity(migrated_engine, clock)
    service = _content_service(migrated_engine, clock)
    record = service.generate(opportunity_id, channel=Channel.TELEGRAM, correlation_id="cid-ctg")

    assert service.is_stale(record) is False

    clock.advance(hours=1)
    _capture(migrated_engine, clock, price="90.00")

    assert service.is_stale(record) is True
    contract = service.get(record.content_generation_id).to_contract(stale=True)
    assert contract["status"] == "STALE"
    assert contract["publishable"] is False


def test_content_without_a_validated_link_fails_closed(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _capture(migrated_engine, clock)
    _evaluate(migrated_engine, clock, candidate_id, score=100)
    WorkflowService(
        store=SqlAlchemyWorkflowRepository(engine=migrated_engine),
        evaluation_store=SqlAlchemyEvaluationRepository(engine=migrated_engine),
    ).advance(candidate_id, correlation_id="cid-adv")
    opportunity_id = _opportunity_id(migrated_engine, candidate_id)

    with pytest.raises(ContentGenerationError) as excinfo:
        _content_service(migrated_engine, clock).generate(
            opportunity_id, channel=Channel.TELEGRAM, correlation_id="cid-ctg"
        )

    assert excinfo.value.error.code == CONTENT_INPUT_INVALID
    assert _count(migrated_engine, "content_generation") == 0


def test_numeric_hallucination_is_blocked_and_not_persisted(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    _, opportunity_id = _ready_opportunity(migrated_engine, clock)
    provider = _CannedContentProvider(
        {
            "headline": "Oferta",
            "body": "Preço especial de R$ 999,00!",
            "cta": "Compre",
            "warnings": [],
        }
    )

    with pytest.raises(ContentGenerationError) as excinfo:
        _content_service(migrated_engine, clock, provider=provider).generate(
            opportunity_id, channel=Channel.TELEGRAM, correlation_id="cid-ctg"
        )

    assert excinfo.value.error.code == UNSUPPORTED_NUMERIC_CLAIM
    assert _count(migrated_engine, "content_generation") == 0


def test_ai_url_is_rejected_and_not_persisted(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    _, opportunity_id = _ready_opportunity(migrated_engine, clock)
    provider = _CannedContentProvider(
        {
            "headline": "Oferta",
            "body": "Compre em https://evil.example.com/MLB-CT",
            "cta": "Compre",
            "warnings": [],
        }
    )

    with pytest.raises(ContentGenerationError) as excinfo:
        _content_service(migrated_engine, clock, provider=provider).generate(
            opportunity_id, channel=Channel.TELEGRAM, correlation_id="cid-ctg"
        )

    assert excinfo.value.error.code == CONTENT_URL_NOT_ALLOWED
    assert _count(migrated_engine, "content_generation") == 0


def test_missing_opportunity_and_missing_content_fail_closed(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _content_service(migrated_engine, clock)

    with pytest.raises(RadarException) as missing_opportunity:
        service.generate("opp_missing", channel=Channel.TELEGRAM, correlation_id="cid-ctg")
    assert missing_opportunity.value.error.code == "RAD-WF-014"

    with pytest.raises(RadarException) as missing_content:
        service.get("ctg_missing")
    assert missing_content.value.error.code == CONTENT_GENERATION_NOT_FOUND
