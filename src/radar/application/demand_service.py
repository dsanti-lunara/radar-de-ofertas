"""Demand orchestration (RDR-025).

The service reads a persisted Candidate's raw category and sales count through a
narrow port, resolves the canonical category with the active versioned taxonomy
and applies the deterministic :mod:`radar.domain.demand` composition using the
active per-category normalization. It is read-only and reproducible: the same
Candidate facts, supplied signals and normalization version always yield the same
breakdown, so the future Evaluation (RDR-016) persists the versioned snapshot
instead of this ticket inventing a second store.

Signals the manual capture does not persist yet (rating count, trend, affiliate
portal signal and badges) can be supplied at evaluation time; they are validated
by the public boundary and never trusted blindly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from radar.domain.capture import candidate_not_found_error
from radar.domain.demand import (
    DemandFacts,
    DemandNormalization,
    DemandResult,
    DemandSignal,
    compute_demand,
)
from radar.domain.taxonomy import BrandTaxonomy

#: Origin recorded on a signal read from the persisted Candidate/Offer.
ORIGIN_PERSISTED_OFFER = "persisted_offer"

#: Origin recorded on a signal supplied at evaluation time.
ORIGIN_EVALUATION_INPUT = "evaluation_input"


@dataclass(frozen=True, slots=True)
class CandidateDemandContext:
    """Persisted demand facts of one Candidate (Offer + MarketplaceProduct)."""

    candidate_id: str
    marketplace_product_id: str
    marketplace: str
    raw_category: str | None = None
    sales_count: int | None = None
    captured_at: datetime | None = None


class CandidateDemandContextRepository(Protocol):
    """Persistence port exposing a Candidate's demand context."""

    def get_candidate_demand_context(self, candidate_id: str) -> CandidateDemandContext | None: ...


@dataclass(slots=True)
class DemandService:
    """Evaluate a Candidate's Demand from persisted facts and configured signals."""

    repository: CandidateDemandContextRepository
    taxonomy: BrandTaxonomy
    normalization: DemandNormalization

    def evaluate(
        self,
        candidate_id: str,
        *,
        rating_count: DemandSignal[int] | None = None,
        trend: DemandSignal[str] | None = None,
        affiliate_portal: DemandSignal[str] | None = None,
        badges: DemandSignal[tuple[str, ...]] | None = None,
    ) -> DemandResult:
        """Return the explainable breakdown or a structured not-found error.

        The canonical category is resolved from the persisted raw category with
        the active taxonomy; an unresolved category stays an explicit gap. An
        absent signal stays an explicit gap instead of an invented value.
        """

        context = self.repository.get_candidate_demand_context(candidate_id)
        if context is None:
            raise candidate_not_found_error(candidate_id)

        facts = DemandFacts(
            raw_category=context.raw_category,
            category=self.taxonomy.resolve(context.raw_category),
            sales_count=(
                None
                if context.sales_count is None
                else DemandSignal(value=context.sales_count, source=ORIGIN_PERSISTED_OFFER)
            ),
            rating_count=rating_count,
            trend=trend,
            affiliate_portal=affiliate_portal,
            badges=badges,
        )
        return compute_demand(
            candidate_id=candidate_id,
            facts=facts,
            normalization=self.normalization,
        )


__all__ = [
    "ORIGIN_EVALUATION_INPUT",
    "ORIGIN_PERSISTED_OFFER",
    "CandidateDemandContext",
    "CandidateDemandContextRepository",
    "DemandService",
]
