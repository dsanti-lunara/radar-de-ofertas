"""Evaluation orchestration (RDR-016, RDR-027, RDR-028, RDR-029, RDR-030).

The service reads a persisted Candidate's category through a narrow port,
resolves the approved Brand Fit with the active versioned taxonomy and composes
the deterministic :mod:`radar.domain.evaluation` result from the component scores
produced by the dependent tickets (Price Opportunity, Seller Quality, Demand and
Brand Fit). The resulting Evaluation is immutable and persisted append-only
through the :class:`EvaluationStore` port, so old evaluations are never
overwritten and the decision is observable from the public boundary.

The service is framework-free (no FastAPI/SQLAlchemy/Chrome): it depends only on
domain code and narrow protocols. AI is never called to compute a score, and no
affiliate link or publication is created here (AUT-031, AUT-007).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from radar.application.classification_service import CandidateCategoryRepository
from radar.domain.capture import IdFactory, candidate_not_found_error, default_id_factory
from radar.domain.evaluation import (
    ConfidenceFacts,
    DealFacts,
    Evaluation,
    EvaluationWarning,
    HardRule,
    MonetizationFacts,
    build_evaluation,
)
from radar.domain.taxonomy import Brand, BrandTaxonomy, classify_category


class EvaluationStore(Protocol):
    """Persistence port for immutable Evaluations."""

    def save_evaluation(self, evaluation: Evaluation) -> Evaluation: ...

    def list_evaluations(self, candidate_id: str) -> tuple[Evaluation, ...]: ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class EvaluationService:
    """Evaluate a Candidate and persist the immutable Evaluation."""

    repository: CandidateCategoryRepository
    store: EvaluationStore
    taxonomy: BrandTaxonomy
    id_factory: IdFactory = default_id_factory
    clock: Callable[[], datetime] = _utcnow

    def evaluate(
        self,
        candidate_id: str,
        *,
        brand: Brand,
        deal: DealFacts,
        correlation_id: str,
        monetization: MonetizationFacts | None = None,
        confidence: ConfidenceFacts | None = None,
        declared_hard_rules: Sequence[HardRule] = (),
    ) -> Evaluation:
        """Compose and persist the Evaluation or raise a structured not-found error.

        Brand Fit comes from the active taxonomy (config), never from the caller,
        so an uncalibrated category stays an explicit gap instead of an invented
        value. The other Deal components are the normalized outputs of the
        dependent tickets and are validated by the domain before any score.
        """

        context = self.repository.get_candidate_category(candidate_id)
        if context is None:
            raise candidate_not_found_error(candidate_id)

        classification = classify_category(
            candidate_id=candidate_id,
            brand=brand,
            raw_category=context.raw_category,
            taxonomy=self.taxonomy,
        )
        deal_facts = DealFacts(
            price_opportunity=deal.price_opportunity,
            seller_quality=deal.seller_quality,
            demand=deal.demand,
            brand_fit=classification.brand_fit,
        )
        classification_warnings = tuple(
            EvaluationWarning(code=warning.code, message=warning.message, context=warning.context)
            for warning in classification.warnings
        )
        evaluation = build_evaluation(
            evaluation_id=self.id_factory("eval"),
            candidate_id=candidate_id,
            brand=brand,
            deal=deal_facts,
            monetization=monetization,
            confidence=confidence,
            declared_hard_rules=declared_hard_rules,
            classification_hard_rules=classification.hard_rules,
            classification_warnings=classification_warnings,
            taxonomy_version=self.taxonomy.taxonomy_version,
            taxonomy_hash=self.taxonomy.content_hash,
            correlation_id=correlation_id,
            created_at=self.clock(),
            audit_event_id=self.id_factory("aud"),
        )
        return self.store.save_evaluation(evaluation)

    def list_evaluations(self, candidate_id: str) -> tuple[Evaluation, ...]:
        """Return the immutable Evaluations of a Candidate, oldest first."""

        if self.repository.get_candidate_category(candidate_id) is None:
            raise candidate_not_found_error(candidate_id)
        return self.store.list_evaluations(candidate_id)


__all__ = [
    "EvaluationService",
    "EvaluationStore",
]
