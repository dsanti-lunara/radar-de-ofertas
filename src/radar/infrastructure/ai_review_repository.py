"""SQLAlchemy implementation of the append-only AIReview store (RDR-050).

The AIReview is append-only: this repository never updates or deletes a row, and
the ``ai_review`` table carries SQLite triggers (migration ``0013``) that reject
UPDATE/DELETE at the database level. The review and its audit event are written in
one transaction, so a failed write never leaves a partial record (AUT-141).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.domain.ai_review import (
    AIReview,
    AIReviewWarning,
    EditorialDecision,
)
from radar.domain.audit import AI_REVIEW_RECORDED
from radar.infrastructure.models import AIReviewRow, AuditEventRow


def _iso(moment: datetime) -> str:
    return moment.isoformat()


@dataclass(slots=True)
class SqlAlchemyAIReviewRepository:
    """Persist and read append-only AIReviews against SQLite."""

    engine: Engine

    def save_ai_review(self, review: AIReview) -> AIReview:
        with Session(self.engine) as session, session.begin():
            session.add(_audit_event_to_row(review))
            session.flush()
            session.add(_ai_review_to_row(review))
        return review

    def list_ai_reviews(self, candidate_id: str) -> tuple[AIReview, ...]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(AIReviewRow)
                    .where(AIReviewRow.candidate_id == candidate_id)
                    .order_by(AIReviewRow.created_at, AIReviewRow.id)
                )
                .scalars()
                .all()
            )
            return tuple(_ai_review_from_row(row) for row in rows)

    def get_ai_review(self, ai_review_id: str) -> AIReview | None:
        with Session(self.engine) as session:
            row = session.get(AIReviewRow, ai_review_id)
            return None if row is None else _ai_review_from_row(row)


def _audit_event_to_row(review: AIReview) -> AuditEventRow:
    return AuditEventRow(
        id=review.audit_event_id,
        event_type=AI_REVIEW_RECORDED,
        entity_type="ai_review",
        entity_id=review.ai_review_id,
        source="ai",
        correlation_id=review.correlation_id,
        payload=json.dumps(
            {
                "candidate_id": review.candidate_id,
                "evaluation_id": review.evaluation_id,
                "task": review.task,
                "provider": review.provider,
                "decision": review.decision.value,
                "knowledge_version": review.knowledge_version,
                "prompt_version": review.prompt_version,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        recorded_at=_iso(review.created_at),
    )


def _ai_review_to_row(review: AIReview) -> AIReviewRow:
    return AIReviewRow(
        id=review.ai_review_id,
        candidate_id=review.candidate_id,
        evaluation_id=review.evaluation_id,
        task=review.task,
        provider=review.provider,
        model=review.model,
        knowledge_version=review.knowledge_version,
        knowledge_hash=review.knowledge_hash,
        prompt_version=review.prompt_version,
        decision=review.decision.value,
        editorial_angle=review.editorial_angle,
        reason_codes=json.dumps(list(review.reason_codes), ensure_ascii=False, sort_keys=True),
        warnings=json.dumps(
            [warning.to_contract() for warning in review.warnings],
            ensure_ascii=False,
            sort_keys=True,
        ),
        allowed_claims=json.dumps(
            [dict(claim) for claim in review.allowed_claims],
            ensure_ascii=False,
            sort_keys=True,
        ),
        input_snapshot=json.dumps(dict(review.input_snapshot), ensure_ascii=False, sort_keys=True),
        correlation_id=review.correlation_id,
        audit_event_id=review.audit_event_id,
        schema_version=review.schema_version,
        created_at=_iso(review.created_at),
    )


def _ai_review_from_row(row: AIReviewRow) -> AIReview:
    warnings = tuple(
        AIReviewWarning(
            code=str(item["code"]),
            message=str(item["message"]),
            context=dict(item.get("context") or {}),
        )
        for item in json.loads(row.warnings)
    )
    allowed_claims: tuple[dict[str, Any], ...] = tuple(
        dict(item) for item in json.loads(row.allowed_claims)
    )
    return AIReview(
        ai_review_id=row.id,
        candidate_id=row.candidate_id,
        evaluation_id=row.evaluation_id,
        task=row.task,
        provider=row.provider,
        model=row.model,
        knowledge_version=row.knowledge_version,
        knowledge_hash=row.knowledge_hash,
        prompt_version=row.prompt_version,
        decision=EditorialDecision(row.decision),
        editorial_angle=row.editorial_angle,
        reason_codes=tuple(str(code) for code in json.loads(row.reason_codes)),
        warnings=warnings,
        allowed_claims=allowed_claims,
        input_snapshot=json.loads(row.input_snapshot),
        correlation_id=row.correlation_id,
        audit_event_id=row.audit_event_id,
        created_at=datetime.fromisoformat(row.created_at),
        schema_version=row.schema_version,
    )


__all__ = [
    "SqlAlchemyAIReviewRepository",
]
