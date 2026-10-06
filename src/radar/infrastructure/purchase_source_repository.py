"""SQLAlchemy implementation of the append-only purchase source store (RDR-031).

A decision is written together with its Evidence rows and its audit event inside
one transaction, so a failed write never leaves a partial record. The
``purchase_source_decision`` table carries SQLite triggers (migration ``0005``)
that reject UPDATE/DELETE, so an old decision is never overwritten (AUT-029).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.domain.audit import PURCHASE_SOURCE_DECIDED
from radar.domain.capture import Evidence
from radar.domain.purchase_source import (
    ENTITY_PURCHASE_SOURCE_DECISION,
    EVIDENCE_SOURCE_PURCHASE_SOURCE_COMPARISON,
    MaterialDifferenceAction,
    PurchaseSourceDecision,
    PurchaseSourceDecisionRecord,
    PurchaseSourceEvaluation,
    PurchaseSourcePolicy,
    PurchaseSourceResult,
    PurchaseSourceWarning,
)
from radar.infrastructure.models import AuditEventRow, EvidenceRow, PurchaseSourceDecisionRow


def _iso(moment: datetime) -> str:
    return moment.isoformat()


@dataclass(slots=True)
class SqlAlchemyPurchaseSourceDecisionRepository:
    """Persist and read append-only purchase source decisions against SQLite."""

    engine: Engine

    def save_decision(self, record: PurchaseSourceDecisionRecord) -> PurchaseSourceDecisionRecord:
        with Session(self.engine) as session, session.begin():
            session.add(_audit_event_to_row(record))
            session.flush()
            session.add_all(_evidence_to_row(item) for item in record.evidence)
            session.flush()
            session.add(_decision_to_row(record))
        return record

    def list_decisions(self, candidate_id: str) -> tuple[PurchaseSourceDecisionRecord, ...]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(PurchaseSourceDecisionRow)
                    .where(PurchaseSourceDecisionRow.candidate_id == candidate_id)
                    .order_by(
                        PurchaseSourceDecisionRow.created_at,
                        PurchaseSourceDecisionRow.id,
                    )
                )
                .scalars()
                .all()
            )
            return tuple(_decision_from_row(session, row) for row in rows)


def _audit_event_to_row(record: PurchaseSourceDecisionRecord) -> AuditEventRow:
    result = record.result
    return AuditEventRow(
        id=record.audit_event_id,
        event_type=PURCHASE_SOURCE_DECIDED,
        entity_type="candidate",
        entity_id=result.candidate_id,
        source="purchase_source",
        correlation_id=record.correlation_id,
        payload=json.dumps(
            {
                "decision_id": record.decision_id,
                "decision": result.decision.value,
                "material": result.material,
                "best_alternative_source_id": result.best_alternative_source_id,
                "policy_version": result.policy.policy_version,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        recorded_at=_iso(record.created_at),
    )


def _evidence_to_row(evidence: Evidence) -> EvidenceRow:
    return EvidenceRow(
        id=evidence.id,
        entity_type=evidence.entity_type,
        entity_id=evidence.entity_id,
        field_name=evidence.field_name,
        value=evidence.value,
        source_type=evidence.source_type,
        source_url=evidence.source_url,
        captured_at=_iso(evidence.captured_at),
        confidence=evidence.confidence,
        raw_reference=evidence.raw_reference,
    )


def _decision_to_row(record: PurchaseSourceDecisionRecord) -> PurchaseSourceDecisionRow:
    result = record.result
    return PurchaseSourceDecisionRow(
        id=record.decision_id,
        candidate_id=result.candidate_id,
        decision=result.decision.value,
        chosen_source_id=result.chosen_source_id,
        best_alternative_source_id=result.best_alternative_source_id,
        substituted_source_id=result.substituted_source_id,
        chosen_effective_price=(
            None if result.chosen_effective_price is None else str(result.chosen_effective_price)
        ),
        alternative_effective_price=(
            None
            if result.alternative_effective_price is None
            else str(result.alternative_effective_price)
        ),
        difference_percent=(
            None if result.difference_percent is None else str(result.difference_percent)
        ),
        material=result.material,
        threshold_percent=str(result.threshold_percent),
        commission_considered=result.commission_considered,
        policy_version=result.policy.policy_version,
        policy_hash=result.policy.content_hash,
        policy_action=result.policy.on_material_difference.value,
        sources=json.dumps(
            [source.to_contract() for source in result.sources],
            ensure_ascii=False,
            sort_keys=True,
        ),
        warnings=json.dumps(
            [warning.to_contract() for warning in result.warnings],
            ensure_ascii=False,
            sort_keys=True,
        ),
        as_of=_iso(result.as_of),
        audit_event_id=record.audit_event_id,
        correlation_id=record.correlation_id,
        created_at=_iso(record.created_at),
    )


def _decision_from_row(
    session: Session, row: PurchaseSourceDecisionRow
) -> PurchaseSourceDecisionRecord:
    sources = tuple(
        PurchaseSourceEvaluation(
            source_id=str(item["source_id"]),
            role=str(item["role"]),
            marketplace=item.get("marketplace"),
            url=item.get("url"),
            price=Decimal(str(item["price"])),
            shipping_cost=(
                None if item.get("shipping_cost") is None else Decimal(str(item["shipping_cost"]))
            ),
            coupon_state=str(item["coupon_state"]),
            coupon_amount=(
                None if item.get("coupon_amount") is None else Decimal(str(item["coupon_amount"]))
            ),
            effective_price=(
                None
                if item.get("effective_price") is None
                else Decimal(str(item["effective_price"]))
            ),
            equivalent=bool(item["product_equivalent"]),
            conditions_comparable=bool(item["conditions_comparable"]),
            eligible=bool(item["eligible"]),
            reason=str(item["reason"]),
        )
        for item in json.loads(row.sources)
    )
    warnings = tuple(
        PurchaseSourceWarning(
            code=str(item["code"]),
            message=str(item["message"]),
            context=dict(item.get("context") or {}),
        )
        for item in json.loads(row.warnings)
    )
    policy = PurchaseSourcePolicy(
        policy_version=row.policy_version,
        content_hash=row.policy_hash,
        reference_difference_percent=Decimal(row.threshold_percent),
        on_material_difference=MaterialDifferenceAction(row.policy_action),
    )
    result = PurchaseSourceResult(
        candidate_id=row.candidate_id,
        decision=PurchaseSourceDecision(row.decision),
        chosen_source_id=row.chosen_source_id,
        best_alternative_source_id=row.best_alternative_source_id,
        chosen_effective_price=(
            None if row.chosen_effective_price is None else Decimal(row.chosen_effective_price)
        ),
        alternative_effective_price=(
            None
            if row.alternative_effective_price is None
            else Decimal(row.alternative_effective_price)
        ),
        difference_percent=(
            None if row.difference_percent is None else Decimal(row.difference_percent)
        ),
        material=bool(row.material),
        threshold_percent=Decimal(row.threshold_percent),
        substituted_source_id=row.substituted_source_id,
        policy=policy,
        sources=sources,
        warnings=warnings,
        as_of=datetime.fromisoformat(row.as_of),
        commission_considered=bool(row.commission_considered),
    )
    evidence = _load_evidence(session, row.id)
    return PurchaseSourceDecisionRecord(
        decision_id=row.id,
        result=result,
        correlation_id=row.correlation_id,
        audit_event_id=row.audit_event_id,
        created_at=datetime.fromisoformat(row.created_at),
        evidence=evidence,
    )


def _load_evidence(session: Session, decision_id: str) -> tuple[Evidence, ...]:
    rows = (
        session.execute(
            select(EvidenceRow)
            .where(
                EvidenceRow.entity_type == ENTITY_PURCHASE_SOURCE_DECISION,
                EvidenceRow.entity_id == decision_id,
            )
            .order_by(EvidenceRow.field_name, EvidenceRow.id)
        )
        .scalars()
        .all()
    )
    return tuple(
        Evidence(
            id=row.id,
            entity_type=ENTITY_PURCHASE_SOURCE_DECISION,
            entity_id=row.entity_id,
            field_name=row.field_name,
            value=row.value,
            source_type=EVIDENCE_SOURCE_PURCHASE_SOURCE_COMPARISON,
            captured_at=datetime.fromisoformat(row.captured_at),
            source_url=row.source_url,
            confidence=row.confidence,
            raw_reference=row.raw_reference,
        )
        for row in rows
    )


__all__ = [
    "SqlAlchemyPurchaseSourceDecisionRepository",
]
