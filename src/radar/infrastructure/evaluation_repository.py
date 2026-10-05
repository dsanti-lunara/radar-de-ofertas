"""SQLAlchemy implementation of the immutable Evaluation store (RDR-016).

The Evaluation is append-only: this repository never updates or deletes a row,
and the ``evaluation`` table carries SQLite triggers (migration ``0004``) that
reject UPDATE/DELETE at the database level (AUT-030). The evaluation and its
audit event are written in one transaction, so a failed write never leaves a
partial record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.domain.audit import EVALUATION_RECORDED
from radar.domain.evaluation import (
    ConfidenceLevel,
    Decision,
    Evaluation,
    EvaluationWarning,
)
from radar.domain.taxonomy import Brand, HardRuleViolation
from radar.infrastructure.models import AuditEventRow, EvaluationRow


def _iso(moment: datetime) -> str:
    return moment.isoformat()


@dataclass(slots=True)
class SqlAlchemyEvaluationRepository:
    """Persist and read append-only Evaluations against SQLite."""

    engine: Engine

    def save_evaluation(self, evaluation: Evaluation) -> Evaluation:
        with Session(self.engine) as session, session.begin():
            session.add(_audit_event_to_row(evaluation))
            session.flush()
            session.add(_evaluation_to_row(evaluation))
        return evaluation

    def list_evaluations(self, candidate_id: str) -> tuple[Evaluation, ...]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(EvaluationRow)
                    .where(EvaluationRow.candidate_id == candidate_id)
                    .order_by(EvaluationRow.created_at, EvaluationRow.id)
                )
                .scalars()
                .all()
            )
            return tuple(_evaluation_from_row(row) for row in rows)


def _audit_event_to_row(evaluation: Evaluation) -> AuditEventRow:
    return AuditEventRow(
        id=evaluation.audit_event_id,
        event_type=EVALUATION_RECORDED,
        entity_type="candidate",
        entity_id=evaluation.candidate_id,
        source="evaluation",
        correlation_id=evaluation.correlation_id,
        payload=json.dumps(
            {
                "evaluation_id": evaluation.evaluation_id,
                "decision": evaluation.decision.value,
                "deal_score": None if evaluation.deal_score is None else str(evaluation.deal_score),
                "monetization_score": evaluation.monetization_score,
                "confidence": None
                if evaluation.confidence is None
                else evaluation.confidence.value,
                "scoring_version": evaluation.scoring_version,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        recorded_at=_iso(evaluation.created_at),
    )


def _evaluation_to_row(evaluation: Evaluation) -> EvaluationRow:
    return EvaluationRow(
        id=evaluation.evaluation_id,
        candidate_id=evaluation.candidate_id,
        brand=evaluation.brand.value,
        deal_score=None if evaluation.deal_score is None else str(evaluation.deal_score),
        monetization_score=evaluation.monetization_score,
        confidence=None if evaluation.confidence is None else evaluation.confidence.value,
        decision=evaluation.decision.value,
        auto_eligible=evaluation.auto_eligible,
        passed_rules=json.dumps(list(evaluation.passed_rules), ensure_ascii=False, sort_keys=True),
        failed_rules=json.dumps(
            [rule.to_contract() for rule in evaluation.failed_rules],
            ensure_ascii=False,
            sort_keys=True,
        ),
        warnings=json.dumps(
            [warning.to_contract() for warning in evaluation.warnings],
            ensure_ascii=False,
            sort_keys=True,
        ),
        breakdown=json.dumps(dict(evaluation.breakdown), ensure_ascii=False, sort_keys=True),
        feature_snapshot=json.dumps(
            dict(evaluation.feature_snapshot), ensure_ascii=False, sort_keys=True
        ),
        scoring_version=evaluation.scoring_version,
        deal_scoring_version=evaluation.deal_scoring_version,
        monetization_scoring_version=evaluation.monetization_scoring_version,
        confidence_scoring_version=evaluation.confidence_scoring_version,
        taxonomy_version=evaluation.taxonomy_version,
        taxonomy_hash=evaluation.taxonomy_hash,
        audit_event_id=evaluation.audit_event_id,
        correlation_id=evaluation.correlation_id,
        created_at=_iso(evaluation.created_at),
    )


def _evaluation_from_row(row: EvaluationRow) -> Evaluation:
    failed_rules = tuple(
        HardRuleViolation(
            rule=str(item["rule"]),
            message=str(item["message"]),
            context=dict(item.get("context") or {}),
        )
        for item in json.loads(row.failed_rules)
    )
    warnings = tuple(
        EvaluationWarning(
            code=str(item["code"]),
            message=str(item["message"]),
            context=dict(item.get("context") or {}),
        )
        for item in json.loads(row.warnings)
    )
    return Evaluation(
        evaluation_id=row.id,
        candidate_id=row.candidate_id,
        brand=Brand(row.brand),
        deal_score=None if row.deal_score is None else Decimal(row.deal_score),
        monetization_score=row.monetization_score,
        confidence=None if row.confidence is None else ConfidenceLevel(row.confidence),
        decision=Decision(row.decision),
        auto_eligible=bool(row.auto_eligible),
        passed_rules=tuple(str(rule) for rule in json.loads(row.passed_rules)),
        failed_rules=failed_rules,
        warnings=warnings,
        breakdown=json.loads(row.breakdown),
        feature_snapshot=json.loads(row.feature_snapshot),
        scoring_version=row.scoring_version,
        deal_scoring_version=row.deal_scoring_version,
        monetization_scoring_version=row.monetization_scoring_version,
        confidence_scoring_version=row.confidence_scoring_version,
        taxonomy_version=row.taxonomy_version,
        taxonomy_hash=row.taxonomy_hash,
        audit_event_id=row.audit_event_id,
        created_at=datetime.fromisoformat(row.created_at),
        correlation_id=row.correlation_id,
    )


__all__ = [
    "SqlAlchemyEvaluationRepository",
]
