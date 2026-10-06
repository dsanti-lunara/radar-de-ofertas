"""Editorial Review orchestration (RDR-045, RDR-046, RDR-050).

The service reads a persisted Candidate's sanitized facts, the immutable latest
Evaluation and the backend-sustained ``allowed_claims`` (RDR-032), selects the
minimal Knowledge context for ``brand + channel`` and asks the configured
:class:`~radar.domain.ai_review.AIProvider` for a structured Editorial Review. The
validated response is persisted as an append-only :class:`AIReview` in the same
transaction as its ``AuditEvent`` (AUT-141).

The service fails closed: a provider timeout/refusal/auth failure or an invalid
schema raises a structured error *before* anything is written, so a failed review
never becomes an approval and never creates an Opportunity by blind approval
(AUT-059, AUT-068). It is framework-free (no FastAPI/SQLAlchemy/Chrome) and never
computes a score, decides compliance or creates a link.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from radar.domain.ai_review import (
    EDITORIAL_REVIEW_TASK,
    AIProvider,
    AIReview,
    AIReviewEvaluationFacts,
    AIReviewOfferFacts,
    AIReviewProductFacts,
    ai_review_not_found_error,
    build_ai_review,
    build_ai_review_input,
    parse_editorial_review_response,
)
from radar.domain.allowed_claims import AllowedClaimsResult, evaluation_not_found_error
from radar.domain.capture import IdFactory, candidate_not_found_error, default_id_factory
from radar.domain.evaluation import Evaluation
from radar.domain.knowledge import Channel, KnowledgePack, select_knowledge_context


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class CandidateAIContext:
    """Sanitized persisted facts of one Candidate used by the AI review."""

    candidate_id: str
    marketplace: str
    external_id: str
    title: str | None
    url: str | None
    raw_category: str | None
    current_price: Decimal
    original_price: Decimal | None
    sales_count: int | None
    seller_name: str | None
    captured_at: datetime
    correlation_id: str
    raw_capture_id: str
    offer_id: str


class CandidateAIContextRepository(Protocol):
    """Persistence port exposing a Candidate's sanitized AI facts."""

    def get_candidate_ai_context(self, candidate_id: str) -> CandidateAIContext | None: ...


class EvaluationReader(Protocol):
    """Read port for the immutable Evaluations of a Candidate."""

    def list_evaluations(self, candidate_id: str) -> tuple[Evaluation, ...]: ...


class ClaimsReader(Protocol):
    """Read port for the backend-sustained allowed claims of a Candidate."""

    def get(
        self, candidate_id: str, *, evaluation_id: str | None = None
    ) -> AllowedClaimsResult: ...


class AIReviewRepository(Protocol):
    """Persistence port for append-only AIReviews."""

    def save_ai_review(self, review: AIReview) -> AIReview: ...

    def list_ai_reviews(self, candidate_id: str) -> tuple[AIReview, ...]: ...

    def get_ai_review(self, ai_review_id: str) -> AIReview | None: ...


@dataclass(slots=True)
class AIReviewService:
    """Execute and query the editorial review of a Candidate."""

    repository: AIReviewRepository
    capture: CandidateAIContextRepository
    evaluations: EvaluationReader
    claims: ClaimsReader
    knowledge: KnowledgePack
    provider: AIProvider
    clock: Callable[[], datetime] = _utcnow
    id_factory: IdFactory = default_id_factory

    def review(self, candidate_id: str, *, channel: Channel, correlation_id: str) -> AIReview:
        """Run one Editorial Review and persist the versioned decision.

        The candidate and the Evaluation must already exist: claims are always
        bound to an immutable Evaluation, so a Candidate without one fails closed
        before the provider is called.
        """

        context = self.capture.get_candidate_ai_context(candidate_id)
        if context is None:
            raise candidate_not_found_error(candidate_id)
        evaluations = self.evaluations.list_evaluations(candidate_id)
        if not evaluations:
            raise evaluation_not_found_error(candidate_id)
        evaluation = evaluations[-1]

        claims = self.claims.get(candidate_id, evaluation_id=evaluation.evaluation_id)
        claims_contract = claims.to_contract()
        knowledge = select_knowledge_context(
            self.knowledge,
            brand=evaluation.brand,
            channel=channel,
            task=EDITORIAL_REVIEW_TASK,
        )
        request = build_ai_review_input(
            candidate_id=candidate_id,
            marketplace=context.marketplace,
            product=AIReviewProductFacts(
                external_id=context.external_id,
                title=context.title,
                category=context.raw_category,
                url=context.url,
            ),
            offer=AIReviewOfferFacts(
                current_price=str(context.current_price),
                original_price=(
                    None if context.original_price is None else str(context.original_price)
                ),
                sales_count=context.sales_count,
                seller_name=context.seller_name,
            ),
            evaluation=AIReviewEvaluationFacts(
                evaluation_id=evaluation.evaluation_id,
                decision=evaluation.decision.value,
                deal_score=None if evaluation.deal_score is None else str(evaluation.deal_score),
                monetization_score=evaluation.monetization_score,
                confidence=None if evaluation.confidence is None else evaluation.confidence.value,
            ),
            knowledge=knowledge,
            allowed_claims=claims_contract["claims"],
            omitted_claims=claims_contract["omitted_claims"],
            forbidden_claims=claims_contract["forbidden_claims"],
        )

        # Any provider failure/refusal/unknown decision raises here, before the
        # transaction below, so a failed review is never persisted as approval.
        raw_response = self.provider.evaluate_candidate(request)
        outcome = parse_editorial_review_response(raw_response, provider=self.provider.name)

        now = self.clock()
        review = build_ai_review(
            request=request,
            outcome=outcome,
            provider=self.provider.name,
            model=getattr(self.provider, "model", None),
            correlation_id=correlation_id,
            audit_event_id=str(self.id_factory("aud")),
            created_at=now,
            id_factory=self.id_factory,
        )
        return self.repository.save_ai_review(review)

    def list(self, candidate_id: str) -> tuple[AIReview, ...]:
        """Return the persisted AIReviews of a Candidate in chronological order."""

        return self.repository.list_ai_reviews(candidate_id)

    def get(self, ai_review_id: str) -> AIReview:
        """Return one persisted AIReview or fail closed with ``RAD-AI-009``."""

        review = self.repository.get_ai_review(ai_review_id)
        if review is None:
            raise ai_review_not_found_error(ai_review_id)
        return review


__all__ = [
    "AIReviewRepository",
    "AIReviewService",
    "CandidateAIContext",
    "CandidateAIContextRepository",
    "ClaimsReader",
    "EvaluationReader",
]
