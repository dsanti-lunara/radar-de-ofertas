"""Price Opportunity orchestration (RDR-023).

The service reads a persisted Candidate's Offer, its append-only price history
and any comparable evidence through a narrow port, then applies the
deterministic :mod:`radar.domain.price_opportunity` calculation. It is
read-only and reproducible: the same Candidate facts and confirmed conditions
always yield the same breakdown, so the future Evaluation (RDR-016) persists the
versioned snapshot instead of this ticket inventing a second store.

Conditions that the manual capture does not persist yet (confirmed coupon,
shipping and comparable evidence) can be supplied at evaluation time; they are
validated by the public boundary and never trusted blindly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from radar.domain.capture import candidate_not_found_error
from radar.domain.price_opportunity import (
    ComparableEvidence,
    Coupon,
    PriceHistoryFact,
    PriceOpportunityResult,
    compute_price_opportunity,
)


@dataclass(frozen=True, slots=True)
class CandidatePriceContext:
    """Persisted price context of one Candidate (Offer + history)."""

    candidate_id: str
    marketplace_product_id: str
    current_price: Decimal
    captured_at: datetime
    original_price: Decimal | None = None
    shipping_cost: Decimal | None = None
    coupon: Coupon | None = None
    history: tuple[PriceHistoryFact, ...] = ()
    comparable: ComparableEvidence | None = None


class CandidatePriceContextRepository(Protocol):
    """Persistence port exposing a Candidate's price context."""

    def get_candidate_price_context(self, candidate_id: str) -> CandidatePriceContext | None: ...


@dataclass(slots=True)
class PriceOpportunityService:
    """Evaluate a Candidate's Price Opportunity from persisted facts."""

    repository: CandidatePriceContextRepository

    def evaluate(
        self,
        candidate_id: str,
        *,
        shipping_cost: Decimal | None = None,
        coupon: Coupon | None = None,
        comparable: ComparableEvidence | None = None,
    ) -> PriceOpportunityResult:
        """Return the explainable breakdown or a structured not-found error.

        Supplied conditions override the persisted values; when absent the
        persisted Offer condition is used, and an absent value stays an explicit
        gap instead of an invented one.
        """

        context = self.repository.get_candidate_price_context(candidate_id)
        if context is None:
            raise candidate_not_found_error(candidate_id)

        return compute_price_opportunity(
            candidate_id=candidate_id,
            current_price=context.current_price,
            as_of=context.captured_at,
            original_price=context.original_price,
            shipping_cost=shipping_cost if shipping_cost is not None else context.shipping_cost,
            coupon=coupon if coupon is not None else context.coupon,
            history=context.history,
            comparable=comparable if comparable is not None else context.comparable,
        )


__all__ = [
    "CandidatePriceContext",
    "CandidatePriceContextRepository",
    "PriceOpportunityService",
]
