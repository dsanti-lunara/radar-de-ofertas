from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.application.affiliate_link_service import AffiliateLinkService
from radar.application.capture_service import ManualCaptureService
from radar.application.evaluation_service import EvaluationService
from radar.application.workflow_service import WorkflowService
from radar.domain.affiliate_link import (
    AFFILIATE_LINK_OPPORTUNITY_NOT_LINKABLE,
    AffiliateLinkError,
    affiliate_link_not_found_error,
    affiliate_link_provider_unavailable_error,
)
from radar.domain.capture import CaptureIntake, CaptureSource, Marketplace
from radar.domain.errors import RadarException
from radar.domain.evaluation import ConfidenceFacts, DealFacts
from radar.domain.taxonomy import APPROVED_TAXONOMY, Brand
from radar.domain.tracking import (
    APPROVED_TRACKING_LABEL_MAPPING,
    TRACKING_MAPPING_NOT_CONFIGURED,
    build_tracking_label_mapping,
)
from radar.infrastructure.affiliate_link_provider import FakeAffiliateLinkProvider
from radar.infrastructure.affiliate_link_repository import SqlAlchemyAffiliateLinkRepository
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from radar.infrastructure.models import AffiliateLinkRow, AuditEventRow
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


class _RaisingProvider:
    name = "stub"

    def __init__(self, error: AffiliateLinkError) -> None:
        self._error = error

    def generate(self, request: Any) -> dict[str, Any]:
        raise self._error


class _CannedProvider:
    name = "stub"

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    def generate(self, request: Any) -> dict[str, Any]:
        return self._response


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
    assert value is not None
    return int(value)


def _mapping(label: str = "rbtgoffer"):
    return build_tracking_label_mapping(
        {
            "schema_version": "1.0",
            "mapping_version": "tracking-labels-test",
            "entries": [
                {
                    "internal_reference": INTERNAL_REFERENCE,
                    "marketplace": "MERCADO_LIVRE",
                    "label": label,
                }
            ],
        }
    )


def _capture(engine: Engine, clock: _Clock) -> str:
    service = ManualCaptureService(
        repository=SqlAlchemyCaptureRepository(engine=engine), clock=clock
    )
    result = service.capture(
        CaptureIntake(
            marketplace=Marketplace.MERCADO_LIVRE,
            source=CaptureSource.BROWSER_EXTENSION,
            external_id="MLB-LINK",
            current_price="80.00",
            title="Perfume",
            url="https://www.mercadolivre.com.br/p/MLB-LINK",
            category="Perfumes",
            captured_at=clock(),
        ),
        correlation_id="cid-capture",
    )
    return result.candidate_id


def _evaluate(engine: Engine, clock: _Clock, candidate_id: str, *, score: int) -> None:
    service = EvaluationService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        store=SqlAlchemyEvaluationRepository(engine=engine),
        taxonomy=APPROVED_TAXONOMY,
        clock=clock,
    )
    service.evaluate(
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


def _advance(engine: Engine, candidate_id: str) -> None:
    workflow = WorkflowService(
        store=SqlAlchemyWorkflowRepository(engine=engine),
        evaluation_store=SqlAlchemyEvaluationRepository(engine=engine),
    )
    result = workflow.advance(candidate_id, correlation_id="cid-adv")
    assert result.opportunity is not None, result.to_contract()


def _approved_candidate_with_opportunity(engine: Engine, clock: _Clock) -> str:
    candidate_id = _capture(engine, clock)
    _evaluate(engine, clock, candidate_id, score=100)
    _advance(engine, candidate_id)
    return candidate_id


def _service(
    engine: Engine,
    clock: _Clock,
    *,
    provider: Any | None = None,
    mapping: Any | None = None,
) -> AffiliateLinkService:
    repository = SqlAlchemyAffiliateLinkRepository(engine=engine)
    return AffiliateLinkService(
        repository=repository,
        capture=repository,
        evaluations=SqlAlchemyEvaluationRepository(engine=engine),
        opportunities=SqlAlchemyWorkflowRepository(engine=engine),
        tracking_labels=mapping or _mapping(),
        provider=provider or FakeAffiliateLinkProvider(),
        clock=clock,
    )


def test_link_is_persisted_with_audit_and_queryable(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate_with_opportunity(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    link = service.generate(candidate_id, correlation_id="cid-link")

    assert link.generation_method.value == "FAKE"
    assert link.productive is False
    assert link.tracking.external_label == "rbtgoffer"
    assert link.tracking.internal_reference == INTERNAL_REFERENCE
    assert "MLB-LINK" in link.affiliate_url
    assert link.original_url == "https://www.mercadolivre.com.br/p/MLB-LINK"
    assert link.correlation_id == "cid-link"

    assert _count(migrated_engine, "affiliate_link") == 1
    with Session(migrated_engine) as session:
        row = session.get(AffiliateLinkRow, link.affiliate_link_id)
        assert row is not None
        assert row.tracking_label == "rbtgoffer"
        assert row.affiliate_url == link.affiliate_url
        audit = session.get(AuditEventRow, link.audit_event_id)
        assert audit is not None
        assert audit.event_type == "AFFILIATE_LINK_GENERATED"
        assert audit.entity_id == link.affiliate_link_id
        assert audit.correlation_id == "cid-link"

    assert service.get(link.affiliate_link_id).affiliate_link_id == link.affiliate_link_id
    assert service.list(candidate_id) == (link,)


def test_generation_is_idempotent_for_the_same_opportunity_and_label(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate_with_opportunity(migrated_engine, clock)
    service = _service(migrated_engine, clock)

    first = service.generate(candidate_id, correlation_id="cid-link")
    second = service.generate(candidate_id, correlation_id="cid-link-2")

    assert first.affiliate_link_id == second.affiliate_link_id
    assert _count(migrated_engine, "affiliate_link") == 1


def test_unapproved_candidate_does_not_generate_a_link(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _capture(migrated_engine, clock)
    _evaluate(migrated_engine, clock, candidate_id, score=0)
    service = _service(migrated_engine, clock)

    with pytest.raises(RadarException) as error:
        service.generate(candidate_id, correlation_id="cid-link")

    assert error.value.error.code == AFFILIATE_LINK_OPPORTUNITY_NOT_LINKABLE
    assert _count(migrated_engine, "affiliate_link") == 0


def test_unmapped_label_blocks_without_writing(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate_with_opportunity(migrated_engine, clock)
    service = _service(migrated_engine, clock, mapping=APPROVED_TRACKING_LABEL_MAPPING)

    with pytest.raises(RadarException) as error:
        service.generate(candidate_id, correlation_id="cid-link")

    assert error.value.error.code == TRACKING_MAPPING_NOT_CONFIGURED
    assert _count(migrated_engine, "affiliate_link") == 0


def test_provider_failure_writes_nothing(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate_with_opportunity(migrated_engine, clock)
    provider = _RaisingProvider(affiliate_link_provider_unavailable_error(provider="stub"))
    service = _service(migrated_engine, clock, provider=provider)

    with pytest.raises(RadarException) as error:
        service.generate(candidate_id, correlation_id="cid-link")

    assert error.value.error.code == "RAD-LINK-006"
    assert _count(migrated_engine, "affiliate_link") == 0


def test_wrong_product_or_invalid_host_is_rejected_without_writing(
    migrated_engine: Engine,
) -> None:
    clock = _Clock(FIXED_NOW)
    candidate_id = _approved_candidate_with_opportunity(migrated_engine, clock)

    wrong_product = _CannedProvider(
        {
            "affiliate_url": "https://www.mercadolivre.com.br/social/x?matt_word=rbtgoffer",
            "source": "ML_LINK_GENERATOR",
            "product_reference": "MLB-OTHER",
        }
    )
    with pytest.raises(RadarException) as product_error:
        _service(migrated_engine, clock, provider=wrong_product).generate(
            candidate_id, correlation_id="cid-link"
        )
    assert product_error.value.error.code == "RAD-LINK-003"

    invalid_host = _CannedProvider(
        {
            "affiliate_url": "https://evil.example.com/x/MLB-LINK?matt_word=rbtgoffer",
            "source": "ML_LINK_GENERATOR",
            "product_reference": "MLB-LINK",
        }
    )
    with pytest.raises(RadarException) as host_error:
        _service(migrated_engine, clock, provider=invalid_host).generate(
            candidate_id, correlation_id="cid-link"
        )
    assert host_error.value.error.code == "RAD-LINK-003"
    assert _count(migrated_engine, "affiliate_link") == 0


def test_missing_link_returns_structured_not_found(migrated_engine: Engine) -> None:
    clock = _Clock(FIXED_NOW)
    service = _service(migrated_engine, clock)

    with pytest.raises(RadarException) as error:
        service.get("lnk_missing")
    assert error.value.error.code == affiliate_link_not_found_error("lnk_missing").error.code


def test_orphan_link_is_rejected_by_real_foreign_keys(migrated_engine: Engine) -> None:
    with pytest.raises(IntegrityError), Session(migrated_engine) as session, session.begin():
        session.execute(
            text(
                "INSERT INTO affiliate_link ("
                "id, opportunity_id, marketplace, original_url, affiliate_url, "
                "generation_method, productive, status, tracking_context_id, tracking_label, "
                "tracking_brand, tracking_internal_reference, tracking_mapping_version, "
                "tracking_mapping_hash, correlation_id, audit_event_id, schema_version, created_at"
                ") VALUES ("
                "'lnk_1', 'opp_missing', 'MERCADO_LIVRE', 'https://x', 'https://y', "
                "'FAKE', 0, 'VALIDATED', 'trk_1', 'rbtgoffer', 'RADAR_BEAUTY', "
                "'RADAR_BEAUTY:MERCADO_LIVRE', 'v1', 'hash', 'cid', 'aud_missing', '1.0', "
                "'2026-10-06T12:00:00+00:00'"
                ")"
            )
        )
