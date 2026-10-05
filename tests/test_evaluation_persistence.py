from __future__ import annotations

import itertools
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.application.capture_service import ManualCaptureService
from radar.application.evaluation_service import EvaluationService
from radar.domain.capture import (
    CaptureIntake,
    CaptureSource,
    CaptureValidationError,
    Marketplace,
)
from radar.domain.evaluation import (
    ConfidenceFacts,
    DealFacts,
    Decision,
    MonetizationFacts,
)
from radar.domain.taxonomy import APPROVED_TAXONOMY, Brand
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from radar.infrastructure.models import AuditEventRow, EvaluationRow

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _capture_service(engine: Engine) -> ManualCaptureService:
    counter = itertools.count(1)
    return ManualCaptureService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        clock=lambda: FIXED_NOW,
        id_factory=lambda prefix: f"{prefix}_{next(counter):04d}",
    )


def _evaluation_service(engine: Engine) -> EvaluationService:
    counter = itertools.count(1)
    return EvaluationService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        store=SqlAlchemyEvaluationRepository(engine=engine),
        taxonomy=APPROVED_TAXONOMY,
        id_factory=lambda prefix: f"{prefix}_{next(counter):04d}",
        clock=lambda: FIXED_NOW,
    )


def _intake(**overrides: object) -> CaptureIntake:
    data: dict[str, object] = {
        "marketplace": Marketplace.MERCADO_LIVRE,
        "source": CaptureSource.BROWSER_EXTENSION,
        "external_id": "MLB123",
        "current_price": "79.90",
        "title": "Produto",
        "url": "https://www.mercadolivre.com.br/p/MLB123",
        "category": "Perfumes",
        "sales_count": 2300,
        "seller_name": "Loja",
        "seller_id": "SELLER-1",
    }
    data.update(overrides)
    return CaptureIntake(**data)  # type: ignore[arg-type]


def _capture_candidate(engine: Engine) -> str:
    result = _capture_service(engine).capture(_intake(), correlation_id="cid-capture")
    return result.candidate_id


def _evaluate(service: EvaluationService, candidate_id: str, **overrides):
    deal = DealFacts(price_opportunity=90, seller_quality=80, demand=70, brand_fit=None)
    confidence = ConfidenceFacts(
        source_reliability=100,
        freshness=100,
        completeness=100,
        price_history_depth=100,
        cross_validation=100,
    )
    monetization = MonetizationFacts(
        estimated_commission=90,
        effective_commission_percent=90,
        conversion_evidence=90,
        extra_commission=90,
    )
    deal = overrides.get("deal", deal)
    confidence = overrides.get("confidence", confidence)
    monetization = overrides.get("monetization", monetization)
    return service.evaluate(
        candidate_id,
        brand=overrides.get("brand", Brand.RADAR_BEAUTY),
        deal=deal,
        monetization=monetization,
        confidence=confidence,
        declared_hard_rules=overrides.get("declared_hard_rules", ()),
        correlation_id=overrides.get("correlation_id", "cid-eval"),
    )


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
    assert value is not None
    return int(value)


def test_evaluation_is_persisted_and_queryable(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _evaluation_service(migrated_engine)
    evaluation = _evaluate(service, candidate_id)

    assert evaluation.decision is Decision.APPROVE
    assert evaluation.deal_score is not None
    # Brand Fit comes from the approved taxonomy, not from the caller.
    assert evaluation.feature_snapshot["deal"]["brand_fit"] == 100
    assert evaluation.audit_event_id.startswith("aud_")
    assert _count(migrated_engine, "evaluation") == 1

    stored = service.list_evaluations(candidate_id)
    assert len(stored) == 1
    assert stored[0].evaluation_id == evaluation.evaluation_id
    assert stored[0].deal_score == evaluation.deal_score
    assert stored[0].decision is evaluation.decision
    assert stored[0].breakdown == evaluation.breakdown


def test_evaluations_are_append_only_and_immutable(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _evaluation_service(migrated_engine)
    first = _evaluate(service, candidate_id, correlation_id="cid-1")
    second = _evaluate(
        service,
        candidate_id,
        deal=DealFacts(price_opportunity=45, seller_quality=45, demand=45, brand_fit=None),
        correlation_id="cid-2",
    )

    assert first.evaluation_id != second.evaluation_id
    assert _count(migrated_engine, "evaluation") == 2

    stored = service.list_evaluations(candidate_id)
    assert [item.evaluation_id for item in stored] == [first.evaluation_id, second.evaluation_id]
    # The first evaluation is preserved exactly as written.
    assert stored[0].deal_score == first.deal_score
    assert stored[0].decision is first.decision

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE evaluation SET decision = 'APPROVE' WHERE id = :id",
            {"id": first.evaluation_id},
        )
    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.exec_driver_sql(
            "DELETE FROM evaluation WHERE id = :id", {"id": first.evaluation_id}
        )
    assert _count(migrated_engine, "evaluation") == 2


def test_failed_write_rolls_back_without_partial_records(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _evaluation_service(migrated_engine)
    evaluation = _evaluate(service, candidate_id)

    # A fresh evaluation with an unknown Candidate violates the foreign key after
    # the audit event has already been flushed: the whole transaction must roll
    # back so no partial audit record survives.
    broken = replace(
        evaluation,
        evaluation_id="eval_broken",
        audit_event_id="aud_broken",
        candidate_id="cand_missing",
    )
    with pytest.raises(IntegrityError):
        service.store.save_evaluation(broken)

    assert _count(migrated_engine, "evaluation") == 1
    assert _count(migrated_engine, "audit_event") == 2  # capture + evaluation


def test_audit_event_records_the_evaluation(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _evaluation_service(migrated_engine)
    evaluation = _evaluate(service, candidate_id, correlation_id="cid-audit")

    with Session(migrated_engine) as session:
        row = session.execute(
            select(AuditEventRow).where(AuditEventRow.id == evaluation.audit_event_id)
        ).scalar_one()

    assert row.event_type == "EVALUATION_RECORDED"
    assert row.entity_type == "candidate"
    assert row.entity_id == candidate_id
    assert row.correlation_id == "cid-audit"
    payload = json.loads(row.payload or "{}")
    assert payload["evaluation_id"] == evaluation.evaluation_id
    assert payload["decision"] == evaluation.decision.value


def test_persisted_snapshot_keeps_versions_and_breakdown(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _evaluation_service(migrated_engine)
    evaluation = _evaluate(service, candidate_id)

    with Session(migrated_engine) as session:
        row = session.execute(
            select(EvaluationRow).where(EvaluationRow.id == evaluation.evaluation_id)
        ).scalar_one()

    assert row.scoring_version == "evaluation-1.0"
    assert row.deal_scoring_version == "deal-1.0"
    assert row.monetization_scoring_version == "monetization-1.0"
    assert row.confidence_scoring_version == "confidence-1.0"
    assert row.taxonomy_version == APPROVED_TAXONOMY.taxonomy_version
    assert row.taxonomy_hash == APPROVED_TAXONOMY.content_hash
    breakdown = json.loads(row.breakdown)
    assert breakdown["deal"]["scoring_version"] == "deal-1.0"
    assert breakdown["confidence"]["level"] == "HIGH"


def test_unknown_candidate_raises_structured_error(migrated_engine: Engine) -> None:
    service = _evaluation_service(migrated_engine)
    with pytest.raises(CaptureValidationError) as excinfo:
        service.evaluate(
            "cand_missing",
            brand=Brand.RADAR_BEAUTY,
            deal=DealFacts(price_opportunity=90, seller_quality=80, demand=70, brand_fit=None),
            correlation_id="cid",
        )
    assert excinfo.value.error.code == "RAD-CAP-004"

    with pytest.raises(CaptureValidationError) as excinfo:
        service.list_evaluations("cand_missing")
    assert excinfo.value.error.code == "RAD-CAP-004"
