"""SQLAlchemy persistence and read model for HumanReview (RDR-058..RDR-060).

The human review is append-only: this repository never updates or deletes a row,
and the ``human_review`` table carries SQLite triggers (migration ``0018``) that
reject UPDATE/DELETE at the database level. A review and its audit event are
written in one transaction, so a failed write never leaves a partial record
(AUT-010, AUT-141).

The read model composes the persisted Candidate/Offer/Evaluation/AIReview rows so
the Inbox and the detail are served from real data with their timeline and
versions; nothing is recomputed or invented here (docs/11).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from radar.application.review_service import (
    AiReviewRef,
    EvidenceView,
    InboxItem,
    PricePointView,
    ReviewDetail,
    TimelineEntry,
    VersionView,
)
from radar.domain.audit import AuditEvent
from radar.domain.capture import (
    ENTITY_CANDIDATE,
    ENTITY_MARKETPLACE_PRODUCT,
    CandidateState,
)
from radar.domain.evaluation import Evaluation
from radar.domain.human_review import EditedContent, HumanDecision, HumanReview
from radar.infrastructure.ai_review_repository import SqlAlchemyAIReviewRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from radar.infrastructure.models import (
    AIReviewRow,
    AuditEventRow,
    CandidateRow,
    EvidenceRow,
    HumanReviewRow,
    MarketplaceProductRow,
    OfferRow,
    OpportunityRow,
    PriceObservationRow,
    ProductRow,
)
from radar.infrastructure.opportunity_repository import SqlAlchemyWorkflowRepository

_ENTITY_OFFER = "offer"
_ENTITY_AI_REVIEW = "ai_review"
_ENTITY_OPPORTUNITY = "opportunity"
_ENTITY_HUMAN_REVIEW = "human_review"


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _candidate_query():
    return (
        select(CandidateRow, OfferRow, MarketplaceProductRow, ProductRow)
        .join(OfferRow, CandidateRow.offer_id == OfferRow.id)
        .join(
            MarketplaceProductRow,
            OfferRow.marketplace_product_id == MarketplaceProductRow.id,
        )
        .outerjoin(ProductRow, MarketplaceProductRow.product_id == ProductRow.id)
    )


@dataclass(slots=True)
class SqlAlchemyHumanReviewRepository:
    """Persist HumanReviews and serve the review read model on SQLite."""

    engine: Engine

    # -- Writes -------------------------------------------------------------

    def save_human_review(self, review: HumanReview, audit_events: tuple[AuditEvent, ...]) -> None:
        """Persist a HumanReview and its audit event atomically (append-only)."""

        with Session(self.engine) as session, session.begin():
            for event in audit_events:
                session.add(_audit_event_to_row(event))
            session.flush()
            session.add(_human_review_to_row(review))

    # -- HumanReview reads --------------------------------------------------

    def get_human_review(self, human_review_id: str) -> HumanReview | None:
        with Session(self.engine) as session:
            row = session.get(HumanReviewRow, human_review_id)
            return None if row is None else _human_review_from_row(row)

    def list_human_reviews(self, candidate_id: str) -> tuple[HumanReview, ...]:
        with Session(self.engine) as session:
            rows = (
                session.execute(
                    select(HumanReviewRow)
                    .where(HumanReviewRow.candidate_id == candidate_id)
                    .order_by(HumanReviewRow.created_at, HumanReviewRow.id)
                )
                .scalars()
                .all()
            )
            return tuple(_human_review_from_row(row) for row in rows)

    def get_ai_review_ref(
        self, candidate_id: str, ai_review_id: str | None = None
    ) -> AiReviewRef | None:
        """Return the requested/latest AIReview decision of a Candidate."""

        with Session(self.engine) as session:
            if ai_review_id is not None:
                row = session.get(AIReviewRow, ai_review_id)
                if row is None or row.candidate_id != candidate_id:
                    return None
                return AiReviewRef(ai_review_id=row.id, decision=row.decision)
            row = _latest_row(session, AIReviewRow, AIReviewRow.candidate_id == candidate_id)
            if row is None:
                return None
            return AiReviewRef(ai_review_id=row.id, decision=row.decision)

    # -- Read model ---------------------------------------------------------

    def list_inbox(self) -> tuple[InboxItem, ...]:
        """Return every Candidate row as an Inbox item, newest first (RDR-058)."""

        with Session(self.engine) as session:
            rows = session.execute(
                _candidate_query().order_by(CandidateRow.created_at.desc(), CandidateRow.id.desc())
            ).all()
            evaluations = SqlAlchemyEvaluationRepository(self.engine)
            return tuple(self._inbox_item(session, evaluations, row) for row in rows)

    def _inbox_item(self, session: Session, evaluations: SqlAlchemyEvaluationRepository, row):
        candidate_row, offer_row, marketplace_row, product_row = row
        history = evaluations.list_evaluations(candidate_row.id)
        latest = history[-1] if history else None
        opportunity = _latest_row(
            session, OpportunityRow, OpportunityRow.candidate_id == candidate_row.id
        )
        ai = _latest_row(session, AIReviewRow, AIReviewRow.candidate_id == candidate_row.id)
        human = _latest_row(
            session, HumanReviewRow, HumanReviewRow.candidate_id == candidate_row.id
        )
        return InboxItem(
            candidate_id=candidate_row.id,
            candidate_state=CandidateState(candidate_row.state).value,
            marketplace=marketplace_row.marketplace,
            external_id=marketplace_row.external_id,
            title=marketplace_row.title,
            url=marketplace_row.url,
            current_price=offer_row.current_price,
            original_price=offer_row.original_price,
            brand=(
                latest.brand.value
                if latest is not None
                else (product_row.brand if product_row is not None else None)
            ),
            deal_score=(
                None if latest is None or latest.deal_score is None else str(latest.deal_score)
            ),
            monetization_score=None if latest is None else latest.monetization_score,
            confidence=(
                None if latest is None or latest.confidence is None else latest.confidence.value
            ),
            decision=None if latest is None else latest.decision.value,
            main_reason=_main_reason(latest),
            opportunity_id=None if opportunity is None else opportunity.id,
            opportunity_state=None if opportunity is None else opportunity.state,
            ai_decision=None if ai is None else ai.decision,
            human_decision=None if human is None else human.human_decision,
            created_at=candidate_row.created_at,
            updated_at=candidate_row.updated_at,
        )

    def get_detail(self, candidate_id: str) -> ReviewDetail | None:
        """Compose the Candidate detail read model or return ``None`` (RDR-059)."""

        with Session(self.engine) as session:
            row = session.execute(_candidate_query().where(CandidateRow.id == candidate_id)).first()
            if row is None:
                return None
            candidate_row, offer_row, marketplace_row, product_row = row
            evaluations = SqlAlchemyEvaluationRepository(self.engine).list_evaluations(candidate_id)
            ai_reviews = SqlAlchemyAIReviewRepository(self.engine).list_ai_reviews(candidate_id)
            workflow = SqlAlchemyWorkflowRepository(self.engine)
            opportunities = workflow.list_opportunities(candidate_id)
            latest_evaluation = evaluations[-1] if evaluations else None
            latest_ai = ai_reviews[-1] if ai_reviews else None

            opportunity_history: list[TimelineEntry] = []
            for opportunity in opportunities:
                opportunity_history.extend(
                    _event_entry(event)
                    for event in workflow.list_opportunity_events(opportunity.opportunity_id)
                )
            human_reviews = self.list_human_reviews(candidate_id)
            timeline = _timeline(
                session,
                candidate_id=candidate_id,
                ai_review_ids=tuple(item.ai_review_id for item in ai_reviews),
                human_review_ids=tuple(item.human_review_id for item in human_reviews),
                opportunity_ids=tuple(item.opportunity_id for item in opportunities),
            )
            opportunity_contracts = tuple(item.to_contract() for item in opportunities)
            return ReviewDetail(
                candidate=_candidate_contract(
                    candidate_row, offer_row, marketplace_row, product_row
                ),
                evaluation=(None if latest_evaluation is None else latest_evaluation.to_contract()),
                evaluations=tuple(item.to_contract() for item in evaluations),
                price_history=_price_history(session, marketplace_row),
                evidence=_evidence(session, offer_row, marketplace_row),
                ai_reviews=tuple(item.to_contract() for item in ai_reviews),
                human_reviews=tuple(item.to_contract() for item in human_reviews),
                opportunity=None if not opportunity_contracts else opportunity_contracts[-1],
                opportunity_history=tuple(
                    sorted(
                        opportunity_history,
                        key=lambda entry: (entry.recorded_at, entry.entity_id),
                    )
                ),
                timeline=timeline,
                versions=_versions(latest_evaluation, latest_ai),
                correlation_id=candidate_row.correlation_id,
            )


def _latest_row(session: Session, model: type[Any], condition: Any) -> Any:
    return session.execute(
        select(model).where(condition).order_by(model.created_at.desc(), model.id.desc()).limit(1)
    ).scalar_one_or_none()


def _main_reason(evaluation: Evaluation | None) -> str | None:
    if evaluation is None:
        return None
    if evaluation.failed_rules:
        return str(evaluation.failed_rules[0].rule)
    if evaluation.warnings:
        return str(evaluation.warnings[0].code)
    return None


def _candidate_contract(
    candidate_row: CandidateRow,
    offer_row: OfferRow,
    marketplace_row: MarketplaceProductRow,
    product_row: ProductRow | None,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_row.id,
        "state": CandidateState(candidate_row.state).value,
        "marketplace": marketplace_row.marketplace,
        "external_id": marketplace_row.external_id,
        "title": marketplace_row.title,
        "url": marketplace_row.url,
        "raw_category": marketplace_row.raw_category,
        "canonical_name": None if product_row is None else product_row.canonical_name,
        "brand": None if product_row is None else product_row.brand,
        "current_price": offer_row.current_price,
        "original_price": offer_row.original_price,
        "sales_count": offer_row.sales_count,
        "seller_name": offer_row.seller_name,
        "correlation_id": candidate_row.correlation_id,
        "created_at": candidate_row.created_at,
        "updated_at": candidate_row.updated_at,
    }


def _price_history(
    session: Session, marketplace_row: MarketplaceProductRow
) -> tuple[PricePointView, ...]:
    rows = (
        session.execute(
            select(PriceObservationRow)
            .where(PriceObservationRow.marketplace_product_id == marketplace_row.id)
            .order_by(PriceObservationRow.observed_at, PriceObservationRow.id)
        )
        .scalars()
        .all()
    )
    return tuple(
        PricePointView(
            price_observation_id=row.id,
            price=row.price,
            original_price=row.original_price,
            shipping_cost=row.shipping_cost,
            source=row.source,
            observed_at=row.observed_at,
            correlation_id=row.correlation_id,
            raw_capture_id=row.raw_capture_id,
        )
        for row in rows
    )


def _evidence(
    session: Session, offer_row: OfferRow, marketplace_row: MarketplaceProductRow
) -> tuple[EvidenceView, ...]:
    rows = (
        session.execute(
            select(EvidenceRow)
            .where(
                or_(
                    and_(
                        EvidenceRow.entity_type == ENTITY_MARKETPLACE_PRODUCT,
                        EvidenceRow.entity_id == marketplace_row.id,
                    ),
                    and_(
                        EvidenceRow.entity_type == _ENTITY_OFFER,
                        EvidenceRow.entity_id == offer_row.id,
                    ),
                )
            )
            .order_by(EvidenceRow.captured_at, EvidenceRow.id)
        )
        .scalars()
        .all()
    )
    return tuple(
        EvidenceView(
            evidence_id=row.id,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            field_name=row.field_name,
            value=row.value,
            source_type=row.source_type,
            source_url=row.source_url,
            captured_at=row.captured_at,
            confidence=row.confidence,
            raw_reference=row.raw_reference,
        )
        for row in rows
    )


def _timeline(
    session: Session,
    *,
    candidate_id: str,
    ai_review_ids: tuple[str, ...],
    human_review_ids: tuple[str, ...],
    opportunity_ids: tuple[str, ...],
) -> tuple[TimelineEntry, ...]:
    conditions = [
        and_(
            AuditEventRow.entity_type == ENTITY_CANDIDATE,
            AuditEventRow.entity_id == candidate_id,
        )
    ]
    if ai_review_ids:
        conditions.append(
            and_(
                AuditEventRow.entity_type == _ENTITY_AI_REVIEW,
                AuditEventRow.entity_id.in_(ai_review_ids),
            )
        )
    if human_review_ids:
        conditions.append(
            and_(
                AuditEventRow.entity_type == _ENTITY_HUMAN_REVIEW,
                AuditEventRow.entity_id.in_(human_review_ids),
            )
        )
    if opportunity_ids:
        conditions.append(
            and_(
                AuditEventRow.entity_type == _ENTITY_OPPORTUNITY,
                AuditEventRow.entity_id.in_(opportunity_ids),
            )
        )
    rows = (
        session.execute(
            select(AuditEventRow)
            .where(or_(*conditions))
            .order_by(AuditEventRow.recorded_at, AuditEventRow.id)
        )
        .scalars()
        .all()
    )
    return tuple(_audit_row_entry(row) for row in rows)


def _versions(latest_evaluation: Evaluation | None, latest_ai) -> VersionView:
    return VersionView(
        scoring_version=_attr(latest_evaluation, "scoring_version"),
        deal_scoring_version=_attr(latest_evaluation, "deal_scoring_version"),
        monetization_scoring_version=_attr(latest_evaluation, "monetization_scoring_version"),
        confidence_scoring_version=_attr(latest_evaluation, "confidence_scoring_version"),
        taxonomy_version=_attr(latest_evaluation, "taxonomy_version"),
        taxonomy_hash=_attr(latest_evaluation, "taxonomy_hash"),
        ai_knowledge_version=_attr(latest_ai, "knowledge_version"),
        ai_prompt_version=_attr(latest_ai, "prompt_version"),
    )


def _attr(source: object, name: str) -> str | None:
    if source is None:
        return None
    value = getattr(source, name, None)
    return None if value is None else str(value)


def _audit_row_entry(row: AuditEventRow) -> TimelineEntry:
    payload = {} if row.payload is None else json.loads(row.payload)
    return TimelineEntry(
        event_type=row.event_type,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        source=row.source,
        correlation_id=row.correlation_id,
        recorded_at=row.recorded_at,
        payload=payload,
    )


def _event_entry(event: AuditEvent) -> TimelineEntry:
    return TimelineEntry(
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        source=event.source,
        correlation_id=event.correlation_id,
        recorded_at=event.recorded_at.isoformat(),
        payload=dict(event.payload),
    )


def _audit_event_to_row(event: AuditEvent) -> AuditEventRow:
    return AuditEventRow(
        id=event.id,
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        source=event.source,
        correlation_id=event.correlation_id,
        payload=json.dumps(dict(event.payload), ensure_ascii=False, sort_keys=True),
        recorded_at=_iso(event.recorded_at),
    )


def _human_review_to_row(review: HumanReview) -> HumanReviewRow:
    return HumanReviewRow(
        id=review.human_review_id,
        candidate_id=review.candidate_id,
        ai_review_id=review.ai_review_id,
        ai_decision=review.ai_decision,
        human_decision=review.human_decision.value,
        reason=review.reason,
        note=review.note,
        edited_content=(
            None
            if review.edited_content is None
            else json.dumps(review.edited_content.to_contract(), ensure_ascii=False, sort_keys=True)
        ),
        correlation_id=review.correlation_id,
        audit_event_id=review.audit_event_id,
        schema_version=review.schema_version,
        created_at=_iso(review.reviewed_at),
    )


def _human_review_from_row(row: HumanReviewRow) -> HumanReview:
    edited = None
    if row.edited_content is not None:
        payload = json.loads(row.edited_content)
        edited = EditedContent(
            headline=str(payload["headline"]),
            body=str(payload["body"]),
            cta=str(payload["cta"]),
        )
    return HumanReview(
        human_review_id=row.id,
        candidate_id=row.candidate_id,
        ai_review_id=row.ai_review_id,
        ai_decision=row.ai_decision,
        human_decision=HumanDecision(row.human_decision),
        reason=row.reason,
        note=row.note,
        edited_content=edited,
        correlation_id=row.correlation_id,
        audit_event_id=row.audit_event_id,
        reviewed_at=datetime.fromisoformat(row.created_at),
        schema_version=row.schema_version,
    )


__all__ = [
    "SqlAlchemyHumanReviewRepository",
]
