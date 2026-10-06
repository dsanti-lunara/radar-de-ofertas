"""SQLAlchemy implementation of the append-only repost store (RDR-033).

A decision is written together with its Evidence rows and its audit event inside
one transaction, so a failed write never leaves a partial record. The
``repost_decision`` table carries SQLite triggers (migration ``0006``) that
reject UPDATE/DELETE, so an old decision is never overwritten (AUT-029, AUT-064).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.domain.audit import REPOST_DECIDED
from radar.domain.capture import Evidence
from radar.domain.price_opportunity import Coupon, CouponState
from radar.domain.repost import (
    ENTITY_REPOST_DECISION,
    MaterialChange,
    MaterialChangeType,
    PublicationSnapshot,
    RepostDecisionRecord,
    RepostOutcome,
    RepostPolicy,
    RepostReason,
    RepostResult,
    RepostWarning,
)
from radar.infrastructure.models import AuditEventRow, EvidenceRow, RepostDecisionRow


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _optional_coupon(document: dict[str, object] | None) -> Coupon | None:
    if document is None:
        return None
    state = document.get("coupon_state")
    amount = document.get("coupon_amount")
    code = document.get("coupon_code")
    if state is None and amount is None and code is None:
        return None
    return Coupon(
        state=CouponState(str(state)) if state is not None else CouponState.UNKNOWN,
        amount=None if amount is None else Decimal(str(amount)),
        code=None if code is None else str(code),
    )


@dataclass(slots=True)
class SqlAlchemyRepostDecisionRepository:
    """Persist and read append-only repost decisions against SQLite."""

    engine: Engine

    def save_decision(self, record: RepostDecisionRecord) -> RepostDecisionRecord:
        with Session(self.engine) as session, session.begin():
            session.add(_audit_event_to_row(record))
            session.flush()
            session.add_all(_evidence_to_row(item) for item in record.evidence)
            session.flush()
            session.add(_decision_to_row(record))
        return record

    def list_decisions(self, candidate_id: str) -> tuple[RepostDecisionRecord, ...]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(RepostDecisionRow)
                    .where(RepostDecisionRow.candidate_id == candidate_id)
                    .order_by(RepostDecisionRow.created_at, RepostDecisionRow.id)
                )
                .scalars()
                .all()
            )
            return tuple(_decision_from_row(session, row) for row in rows)


def _audit_event_to_row(record: RepostDecisionRecord) -> AuditEventRow:
    result = record.result
    return AuditEventRow(
        id=record.audit_event_id,
        event_type=REPOST_DECIDED,
        entity_type="candidate",
        entity_id=result.candidate_id,
        source="repost",
        correlation_id=record.correlation_id,
        payload=json.dumps(
            {
                "decision_id": record.decision_id,
                "decision": result.decision.value,
                "reason": result.reason.value,
                "allowed": result.allowed,
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


def _decision_to_row(record: RepostDecisionRecord) -> RepostDecisionRow:
    result = record.result
    return RepostDecisionRow(
        id=record.decision_id,
        candidate_id=result.candidate_id,
        decision=result.decision.value,
        reason=result.reason.value,
        allowed=result.allowed,
        material_changes=json.dumps(
            [change.to_contract() for change in result.material_changes],
            ensure_ascii=False,
            sort_keys=True,
        ),
        publication=(
            None
            if result.publication is None
            else json.dumps(result.publication.to_contract(), ensure_ascii=False, sort_keys=True)
        ),
        current_price=str(result.current_price),
        observed_price_drop_percent=(
            None
            if result.observed_price_drop_percent is None
            else str(result.observed_price_drop_percent)
        ),
        cooldown_expires_at=(
            None if result.cooldown_expires_at is None else _iso(result.cooldown_expires_at)
        ),
        cooldown_expired=result.cooldown_expired,
        deal_score=None if result.deal_score is None else str(result.deal_score),
        policy=json.dumps(result.policy.to_contract(), ensure_ascii=False, sort_keys=True),
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


def _decision_from_row(session: Session, row: RepostDecisionRow) -> RepostDecisionRecord:
    policy_document = json.loads(row.policy)
    policy = RepostPolicy(
        policy_version=str(policy_document["policy_version"]),
        content_hash=str(policy_document["policy_hash"]),
        cooldown_hours=int(policy_document["cooldown_hours"]),
        price_drop_percent=Decimal(str(policy_document["price_drop_percent"])),
        strong_deal_threshold=Decimal(str(policy_document["strong_deal_threshold"])),
    )
    publication: PublicationSnapshot | None = None
    if row.publication is not None:
        document = json.loads(row.publication)
        publication = PublicationSnapshot(
            published_at=datetime.fromisoformat(str(document["published_at"])),
            price=Decimal(str(document["price"])),
            publication_id=document.get("publication_id"),
            coupon=_optional_coupon(document),
            conditions=dict(document.get("conditions") or {}),
        )
    material_changes = tuple(
        MaterialChange(
            change_type=MaterialChangeType(str(item["change_type"])),
            detail=dict(item.get("detail") or {}),
        )
        for item in json.loads(row.material_changes)
    )
    warnings = tuple(
        RepostWarning(
            code=str(item["code"]),
            message=str(item["message"]),
            context=dict(item.get("context") or {}),
        )
        for item in json.loads(row.warnings)
    )
    result = RepostResult(
        candidate_id=row.candidate_id,
        decision=RepostOutcome(row.decision),
        reason=RepostReason(row.reason),
        allowed=bool(row.allowed),
        material_changes=material_changes,
        publication=publication,
        current_price=Decimal(row.current_price),
        observed_price_drop_percent=(
            None
            if row.observed_price_drop_percent is None
            else Decimal(row.observed_price_drop_percent)
        ),
        cooldown_expires_at=(
            None
            if row.cooldown_expires_at is None
            else datetime.fromisoformat(row.cooldown_expires_at)
        ),
        cooldown_expired=bool(row.cooldown_expired),
        deal_score=None if row.deal_score is None else Decimal(row.deal_score),
        policy=policy,
        warnings=warnings,
        as_of=datetime.fromisoformat(row.as_of),
    )
    return RepostDecisionRecord(
        decision_id=row.id,
        result=result,
        correlation_id=row.correlation_id,
        audit_event_id=row.audit_event_id,
        created_at=datetime.fromisoformat(row.created_at),
        evidence=_load_evidence(session, row.id),
    )


def _load_evidence(session: Session, decision_id: str) -> tuple[Evidence, ...]:
    rows = (
        session.execute(
            select(EvidenceRow)
            .where(
                EvidenceRow.entity_type == ENTITY_REPOST_DECISION,
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
            entity_type=ENTITY_REPOST_DECISION,
            entity_id=row.entity_id,
            field_name=row.field_name,
            value=row.value,
            source_type=row.source_type,
            captured_at=datetime.fromisoformat(row.captured_at),
            source_url=row.source_url,
            confidence=row.confidence,
            raw_reference=row.raw_reference,
        )
        for row in rows
    )


__all__ = [
    "SqlAlchemyRepostDecisionRepository",
]
