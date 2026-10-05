"""Seller Quality orchestration (RDR-024).

The service reads a persisted Candidate's seller facts through a narrow port and
applies the deterministic :mod:`radar.domain.seller_quality` composition using
the active versioned normalization. It is read-only and reproducible: the same
Candidate facts and normalization version always yield the same breakdown, so the
future Evaluation (RDR-016) persists the versioned snapshot instead of this
ticket inventing a second store.

Signals the manual capture does not persist yet (marketplace reputation and
official/trusted status) can be supplied at evaluation time; they are validated
by the public boundary and never trusted blindly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from radar.domain.capture import candidate_not_found_error
from radar.domain.seller_quality import (
    SellerFacts,
    SellerQualityNormalization,
    SellerQualityResult,
    SellerSignal,
    compute_seller_quality,
)

#: Origin recorded on a signal read from the persisted Candidate/Offer.
ORIGIN_PERSISTED_OFFER = "persisted_offer"

#: Origin recorded on a signal supplied at evaluation time.
ORIGIN_EVALUATION_INPUT = "evaluation_input"


@dataclass(frozen=True, slots=True)
class CandidateSellerContext:
    """Persisted seller facts of one Candidate (Offer + MarketplaceProduct)."""

    candidate_id: str
    marketplace_product_id: str
    seller_id: str | None = None
    seller_name: str | None = None
    rating: Decimal | None = None
    sales_count: int | None = None
    captured_at: datetime | None = None


class CandidateSellerContextRepository(Protocol):
    """Persistence port exposing a Candidate's seller context."""

    def get_candidate_seller_context(self, candidate_id: str) -> CandidateSellerContext | None: ...


@dataclass(slots=True)
class SellerQualityService:
    """Evaluate a Candidate's Seller Quality from persisted facts."""

    repository: CandidateSellerContextRepository
    normalization: SellerQualityNormalization

    def evaluate(
        self,
        candidate_id: str,
        *,
        reputation: SellerSignal[str] | None = None,
        rating: SellerSignal[Decimal] | None = None,
        sales_count: SellerSignal[int] | None = None,
        trusted: SellerSignal[bool] | None = None,
    ) -> SellerQualityResult:
        """Return the explainable breakdown or a structured not-found error.

        Supplied signals override the persisted values; when absent the persisted
        fact is used and an absent value stays an explicit gap instead of an
        invented one.
        """

        context = self.repository.get_candidate_seller_context(candidate_id)
        if context is None:
            raise candidate_not_found_error(candidate_id)

        facts = SellerFacts(
            seller_id=context.seller_id,
            seller_name=context.seller_name,
            reputation=reputation,
            rating=rating if rating is not None else _persisted_rating(context.rating),
            sales_count=(
                sales_count if sales_count is not None else _persisted_sales(context.sales_count)
            ),
            trusted=trusted,
        )
        return compute_seller_quality(
            candidate_id=candidate_id,
            facts=facts,
            normalization=self.normalization,
        )


def _persisted_rating(value: Decimal | None) -> SellerSignal[Decimal] | None:
    if value is None:
        return None
    return SellerSignal(value=value, source=ORIGIN_PERSISTED_OFFER)


def _persisted_sales(value: int | None) -> SellerSignal[int] | None:
    if value is None:
        return None
    return SellerSignal(value=value, source=ORIGIN_PERSISTED_OFFER)


__all__ = [
    "ORIGIN_EVALUATION_INPUT",
    "ORIGIN_PERSISTED_OFFER",
    "CandidateSellerContext",
    "CandidateSellerContextRepository",
    "SellerQualityService",
]
