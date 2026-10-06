"""Allowed Claims orchestration (RDR-032).

The service reads a persisted Candidate's Offer and append-only price history
through a narrow port, resolves the Evaluation version the claims belong to and
applies the deterministic :mod:`radar.domain.allowed_claims` engine. It is
read-only and reproducible: the same Evaluation and evidence always yield the
same claims, so no second store is invented and the AI never creates a claim.

Conditions the manual capture does not persist yet (a confirmed coupon) can be
supplied at query time; they are validated by the public boundary and never
trusted blindly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from radar.domain.allowed_claims import (
    AllowedClaimsResult,
    ClaimOfferFacts,
    ClaimPriceFact,
    compute_allowed_claims,
    evaluation_not_found_error,
)
from radar.domain.capture import candidate_not_found_error
from radar.domain.evaluation import Evaluation
from radar.domain.price_opportunity import Coupon


@dataclass(frozen=True, slots=True)
class CandidateClaimsContext:
    """Persisted evidence context of one Candidate (Offer + price history)."""

    candidate_id: str
    offer_id: str
    current_price: Decimal
    captured_at: datetime
    source: str
    correlation_id: str
    raw_capture_id: str
    sales_count: int | None = None
    original_price: Decimal | None = None
    coupon: Coupon | None = None
    history: tuple[ClaimPriceFact, ...] = ()


class CandidateClaimsRepository(Protocol):
    """Persistence port exposing a Candidate's claim evidence."""

    def get_candidate_claims_context(self, candidate_id: str) -> CandidateClaimsContext | None: ...


class EvaluationReader(Protocol):
    """Read port for the immutable Evaluations of a Candidate."""

    def list_evaluations(self, candidate_id: str) -> tuple[Evaluation, ...]: ...


def _select_evaluation(
    evaluations: tuple[Evaluation, ...], evaluation_id: str | None, candidate_id: str
) -> Evaluation:
    """Resolve the requested Evaluation or the latest one, failing closed."""

    if evaluation_id is None:
        if not evaluations:
            raise evaluation_not_found_error(candidate_id)
        return evaluations[-1]
    for evaluation in evaluations:
        if evaluation.evaluation_id == evaluation_id:
            return evaluation
    raise evaluation_not_found_error(candidate_id, evaluation_id=evaluation_id)


@dataclass(slots=True)
class AllowedClaimsService:
    """Produce the evidence-backed allowed claims of a Candidate's Evaluation."""

    repository: CandidateClaimsRepository
    evaluations: EvaluationReader

    def get(
        self,
        candidate_id: str,
        *,
        evaluation_id: str | None = None,
        coupon: Coupon | None = None,
    ) -> AllowedClaimsResult:
        """Return the claims of the Candidate or a structured not-found error.

        An absent Evaluation is an explicit gap: claims are always bound to an
        immutable Evaluation version, so the AI input can be traced back to it.
        """

        context = self.repository.get_candidate_claims_context(candidate_id)
        if context is None:
            raise candidate_not_found_error(candidate_id)

        evaluation = _select_evaluation(
            self.evaluations.list_evaluations(candidate_id), evaluation_id, candidate_id
        )

        offer = ClaimOfferFacts(
            offer_id=context.offer_id,
            current_price=context.current_price,
            observed_at=context.captured_at,
            source=context.source,
            correlation_id=context.correlation_id,
            raw_capture_id=context.raw_capture_id,
            sales_count=context.sales_count,
            coupon=coupon if coupon is not None else context.coupon,
            original_price=context.original_price,
        )
        return compute_allowed_claims(
            candidate_id=candidate_id,
            evaluation_id=evaluation.evaluation_id,
            evaluation_decision=evaluation.decision.value,
            offer=offer,
            history=context.history,
        )


__all__ = [
    "AllowedClaimsService",
    "CandidateClaimsContext",
    "CandidateClaimsRepository",
    "EvaluationReader",
]
