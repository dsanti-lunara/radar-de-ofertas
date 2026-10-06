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
from radar.application.purchase_source_service import PurchaseSourceService
from radar.domain.capture import CaptureIntake, CaptureSource, Marketplace, default_id_factory
from radar.domain.purchase_source import (
    APPROVED_PURCHASE_SOURCE_POLICY,
    PurchaseSource,
    PurchaseSourceDecision,
)
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.models import AuditEventRow, EvidenceRow, PurchaseSourceDecisionRow
from radar.infrastructure.purchase_source_repository import (
    SqlAlchemyPurchaseSourceDecisionRepository,
)

pytestmark = pytest.mark.integration

FIXED_NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def _capture_service(engine: Engine) -> ManualCaptureService:
    return ManualCaptureService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        clock=lambda: FIXED_NOW,
        id_factory=default_id_factory,
    )


def _purchase_source_service(engine: Engine) -> PurchaseSourceService:
    ticks = itertools.count()
    return PurchaseSourceService(
        repository=SqlAlchemyCaptureRepository(engine=engine),
        store=SqlAlchemyPurchaseSourceDecisionRepository(engine=engine),
        policy=APPROVED_PURCHASE_SOURCE_POLICY,
        id_factory=default_id_factory,
        clock=lambda: FIXED_NOW + timedelta(seconds=next(ticks)),
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


def _capture_candidate(engine: Engine) -> str:
    return _capture_service(engine).capture(_intake(), correlation_id="cid-capture").candidate_id


def _alternative(**overrides: object) -> PurchaseSource:
    data: dict[str, object] = {
        "source_id": "shopee:1",
        "price": Decimal("80"),
        "marketplace": "SHOPEE",
        "shipping_cost": Decimal("0"),
        "product_equivalence_id": "product-1",
    }
    data.update(overrides)
    return PurchaseSource(**data)  # type: ignore[arg-type]


def _decide(
    service: PurchaseSourceService,
    candidate_id: str,
    *,
    correlation_id: str = "cid-ps",
    alternatives: list[PurchaseSource] | None = None,
):
    return service.decide(
        candidate_id,
        correlation_id=correlation_id,
        product_equivalence_id="product-1",
        shipping_cost=Decimal("0"),
        alternatives=alternatives if alternatives is not None else [_alternative()],
    )


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as connection:
        value = connection.exec_driver_sql(f"SELECT COUNT(*) FROM {table}").scalar()
    assert value is not None
    return int(value)


def test_decision_is_persisted_with_evidence_and_queryable(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _purchase_source_service(migrated_engine)

    record = _decide(service, candidate_id)

    assert record.result.decision is PurchaseSourceDecision.REVIEW
    assert record.result.material is True
    assert record.audit_event_id.startswith("aud_")
    assert record.evidence
    assert _count(migrated_engine, "purchase_source_decision") == 1

    stored = service.list_decisions(candidate_id)
    assert len(stored) == 1
    assert stored[0].decision_id == record.decision_id
    assert stored[0].result.decision is record.result.decision
    assert stored[0].result.difference_percent == record.result.difference_percent
    assert {item.field_name for item in stored[0].evidence} == {
        item.field_name for item in record.evidence
    }


def test_decisions_are_append_only_and_immutable(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _purchase_source_service(migrated_engine)

    first = _decide(service, candidate_id, correlation_id="cid-1")
    second = _decide(
        service,
        candidate_id,
        correlation_id="cid-2",
        alternatives=[_alternative(price=Decimal("99"))],
    )

    assert first.decision_id != second.decision_id
    assert _count(migrated_engine, "purchase_source_decision") == 2
    stored = service.list_decisions(candidate_id)
    assert [item.decision_id for item in stored] == [first.decision_id, second.decision_id]

    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE purchase_source_decision SET decision = 'KEEP' WHERE id = :id",
            {"id": first.decision_id},
        )
    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.exec_driver_sql(
            "DELETE FROM purchase_source_decision WHERE id = :id",
            {"id": first.decision_id},
        )
    assert _count(migrated_engine, "purchase_source_decision") == 2


def test_audit_event_records_the_decision(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _purchase_source_service(migrated_engine)
    record = _decide(service, candidate_id, correlation_id="cid-audit")

    with Session(migrated_engine) as session:
        row = session.execute(
            select(AuditEventRow).where(AuditEventRow.id == record.audit_event_id)
        ).scalar_one()

    assert row.event_type == "PURCHASE_SOURCE_DECIDED"
    assert row.entity_type == "candidate"
    assert row.entity_id == candidate_id
    assert row.correlation_id == "cid-audit"


def test_failed_write_rolls_back_without_partial_records(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _purchase_source_service(migrated_engine)
    record = _decide(service, candidate_id)

    evidence_before = _count(migrated_engine, "evidence")
    audit_before = _count(migrated_engine, "audit_event")

    broken = replace(
        record,
        decision_id="psd_broken",
        audit_event_id="aud_broken",
        result=replace(record.result, candidate_id="cand_missing"),
    )
    with pytest.raises(IntegrityError):
        service.store.save_decision(broken)

    assert _count(migrated_engine, "purchase_source_decision") == 1
    assert _count(migrated_engine, "evidence") == evidence_before
    assert _count(migrated_engine, "audit_event") == audit_before


def test_persisted_row_keeps_policy_and_breakdown(migrated_engine: Engine) -> None:
    candidate_id = _capture_candidate(migrated_engine)
    service = _purchase_source_service(migrated_engine)
    record = _decide(service, candidate_id)

    with Session(migrated_engine) as session:
        row = session.execute(
            select(PurchaseSourceDecisionRow).where(
                PurchaseSourceDecisionRow.id == record.decision_id
            )
        ).scalar_one()

    assert row.policy_version == APPROVED_PURCHASE_SOURCE_POLICY.policy_version
    assert row.policy_hash == APPROVED_PURCHASE_SOURCE_POLICY.content_hash
    assert row.policy_action == "REVIEW"
    assert row.threshold_percent == "8"
    assert row.commission_considered is False

    with Session(migrated_engine) as session:
        evidence_rows = (
            session.execute(select(EvidenceRow).where(EvidenceRow.entity_id == record.decision_id))
            .scalars()
            .all()
        )
    assert {item.field_name for item in evidence_rows} >= {
        "decision",
        "difference_percent",
        "reference_difference_percent",
    }
    assert all(item.confidence is None for item in evidence_rows)
