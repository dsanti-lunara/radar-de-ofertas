from __future__ import annotations

import itertools
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.application.capture_service import ManualCaptureService
from radar.application.repost_service import RepostService
from radar.domain.capture import CaptureIntake, CaptureSource, Marketplace, default_id_factory
from radar.domain.evaluation import (
    ConfidenceLevel,
    Decision,
    Evaluation,
)
from radar.domain.price_opportunity import Coupon, CouponState
from radar.domain.repost import (
    APPROVED_REPOST_POLICY,
    PublicationSnapshot,
    RepostOutcome,
    RepostReason,
)
from radar.domain.taxonomy import Brand
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.models import AuditEventRow, EvidenceRow, RepostDecisionRow
from radar.infrastructure.repost_repository import SqlAlchemyRepostDecisionRepository

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


class _StubEvaluations:
    """Minimal Evaluation reader for the repost persistence tests."""

    def __init__(self, evaluations: tuple[Evaluation, ...] = ()) -> None:
        self._evaluations = evaluations

    def list_evaluations(self, candidate_id: str) -> tuple[Evaluation, ...]:
        return tuple(item for item in self._evaluations if item.candidate_id == candidate_id)


def _evaluation(candidate_id: str, deal_score: str) -> Evaluation:
    return Evaluation(
        evaluation_id="eval-1",
        candidate_id=candidate_id,
        brand=Brand.RADAR_BEAUTY,
        deal_score=Decimal(deal_score),
        monetization_score=50,
        confidence=ConfidenceLevel.HIGH,
        decision=Decision.APPROVE,
        auto_eligible=True,
        passed_rules=(),
        failed_rules=(),
        warnings=(),
        breakdown={},
        feature_snapshot={},
        scoring_version="evaluation-1.0",
        deal_scoring_version="deal-1.0",
        monetization_scoring_version="monetization-1.0",
        confidence_scoring_version="confidence-1.0",
        taxonomy_version=None,
        taxonomy_hash=None,
        audit_event_id="aud-eval",
        created_at=FIXED_NOW,
        correlation_id="cid-eval",
    )


def _capture_service(engine: Engine) -> ManualCaptureService:
    return ManualCaptureService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        clock=lambda: FIXED_NOW,
        id_factory=default_id_factory,
    )


def _intake(**overrides: object) -> CaptureIntake:
    data: dict[str, object] = {
        "marketplace": Marketplace.MERCADO_LIVRE,
        "source": CaptureSource.BROWSER_EXTENSION,
        "external_id": "MLB123",
        "current_price": "100.00",
        "title": "Produto",
        "url": "https://www.mercadolivre.com.br/p/MLB123",
        "category": "Perfumes",
        "sales_count": 2300,
        "seller_name": "Loja",
        "seller_id": "SELLER-1",
    }
    data.update(overrides)
    return CaptureIntake(**data)  # type: ignore[arg-type]


def _capture_candidate(engine: Engine, **overrides: object) -> str:
    return (
        _capture_service(engine)
        .capture(_intake(**overrides), correlation_id="cid-capture")
        .candidate_id
    )


def _published(hours_ago: float = 10, price: str = "100") -> PublicationSnapshot:
    return PublicationSnapshot(
        published_at=FIXED_NOW - timedelta(hours=hours_ago),
        price=Decimal(price),
        publication_id="pub-1",
        coupon=Coupon(state=CouponState.NOT_APPLICABLE),
    )


def _service_with_deal(engine: Engine, candidate_id: str, deal_score: str) -> RepostService:
    ticks = itertools.count()
    return RepostService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        evaluations=_StubEvaluations((_evaluation(candidate_id, deal_score),)),
        store=SqlAlchemyRepostDecisionRepository(engine=engine),
        policy=APPROVED_REPOST_POLICY,
        id_factory=default_id_factory,
        clock=lambda: FIXED_NOW + timedelta(seconds=next(ticks)),
    )


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
    assert value is not None
    return int(value)


def test_decision_is_persisted_with_evidence_and_queryable(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _service_with_deal(migrated_engine, candidate_id, "90")

    record = service.decide(
        candidate_id,
        correlation_id="cid-repost",
        publications=[_published(hours_ago=10, price="100")],
    )

    assert record.result.decision is RepostOutcome.BLOCKED
    assert record.result.reason is RepostReason.DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE
    assert record.audit_event_id.startswith("aud_")
    assert record.evidence
    assert _count(migrated_engine, "repost_decision") == 1

    stored = service.list_decisions(candidate_id)
    assert len(stored) == 1
    assert stored[0].decision_id == record.decision_id
    assert stored[0].result.reason is record.result.reason
    assert stored[0].result.policy.content_hash == record.result.policy.content_hash
    assert {item.field_name for item in stored[0].evidence} == {
        item.field_name for item in record.evidence
    }


def test_material_price_drop_is_persisted_as_allowed(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine, current_price="90.00")
    service = _service_with_deal(migrated_engine, candidate_id, "50")

    record = service.decide(
        candidate_id,
        correlation_id="cid-repost",
        publications=[_published(hours_ago=10, price="100")],
    )

    assert record.result.decision is RepostOutcome.ALLOWED
    assert record.result.reason is RepostReason.MATERIAL_PRICE_DROP
    stored = service.list_decisions(candidate_id)
    assert stored[0].result.observed_price_drop_percent == Decimal("10.00")


def test_decisions_are_append_only_and_immutable(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _service_with_deal(migrated_engine, candidate_id, "90")

    first = service.decide(
        candidate_id,
        correlation_id="cid-1",
        publications=[_published(hours_ago=10, price="100")],
    )
    second = service.decide(
        candidate_id,
        correlation_id="cid-2",
        publications=[_published(hours_ago=10, price="100")],
    )

    assert first.decision_id != second.decision_id
    assert _count(migrated_engine, "repost_decision") == 2

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE repost_decision SET decision = 'ALLOWED' WHERE id = :id",
            {"id": first.decision_id},
        )
    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.exec_driver_sql(
            "DELETE FROM repost_decision WHERE id = :id",
            {"id": first.decision_id},
        )
    assert _count(migrated_engine, "repost_decision") == 2


def test_audit_event_records_the_decision(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _service_with_deal(migrated_engine, candidate_id, "90")
    record = service.decide(
        candidate_id,
        correlation_id="cid-audit",
        publications=[_published()],
    )

    with Session(migrated_engine) as session:
        row = session.execute(
            select(AuditEventRow).where(AuditEventRow.id == record.audit_event_id)
        ).scalar_one()

    assert row.event_type == "REPOST_DECIDED"
    assert row.entity_type == "candidate"
    assert row.entity_id == candidate_id
    assert row.correlation_id == "cid-audit"


def test_failed_write_rolls_back_without_partial_records(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _service_with_deal(migrated_engine, candidate_id, "90")
    record = service.decide(
        candidate_id,
        correlation_id="cid-1",
        publications=[_published()],
    )

    evidence_before = _count(migrated_engine, "evidence")
    audit_before = _count(migrated_engine, "audit_event")

    broken = replace(
        record,
        decision_id="rpd_broken",
        audit_event_id="aud_broken",
        result=replace(record.result, candidate_id="cand_missing"),
    )
    with pytest.raises(IntegrityError):
        service.store.save_decision(broken)

    assert _count(migrated_engine, "repost_decision") == 1
    assert _count(migrated_engine, "evidence") == evidence_before
    assert _count(migrated_engine, "audit_event") == audit_before


def test_persisted_row_keeps_policy_and_breakdown(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _service_with_deal(migrated_engine, candidate_id, "90")
    record = service.decide(
        candidate_id,
        correlation_id="cid-1",
        publications=[_published()],
    )

    with Session(migrated_engine) as session:
        row = session.execute(
            select(RepostDecisionRow).where(RepostDecisionRow.id == record.decision_id)
        ).scalar_one()

    assert row.decision == "BLOCKED"
    assert row.reason == "DUPLICATE_WITHOUT_SIGNIFICANT_CHANGE"
    assert row.allowed is False
    assert row.current_price == "100.00"
    assert row.cooldown_expired is False
    assert row.policy
    assert row.publication is not None

    with Session(migrated_engine) as session:
        evidence_rows = (
            session.execute(select(EvidenceRow).where(EvidenceRow.entity_id == record.decision_id))
            .scalars()
            .all()
        )
    assert {item.field_name for item in evidence_rows} >= {
        "decision",
        "reason",
        "current_price",
    }
    assert all(item.confidence is None for item in evidence_rows)
