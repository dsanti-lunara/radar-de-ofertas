"""Purchase Source orchestration (RDR-031).

The service reads a persisted Candidate's Offer through a narrow port, builds the
chosen (affiliate) source from those persisted facts plus the comparable context
supplied at decision time, and applies the deterministic
:mod:`radar.domain.purchase_source` guardrail with the active policy. The
resulting decision is persisted append-only together with its Evidence and audit
event, so the guardrail is observable and traceable from the public boundary.

The chosen price comes from the persisted Offer; the product equivalence id,
comparable conditions and conditions the manual capture does not persist yet
(shipping, coupon, commission) are supplied by the caller, validated by the
public boundary and never trusted blindly. No AI is called and no affiliate link
or publication is created here (AUT-031, AUT-007).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from radar.domain.capture import IdFactory, candidate_not_found_error, default_id_factory
from radar.domain.price_opportunity import Coupon
from radar.domain.purchase_source import (
    PurchaseSource,
    PurchaseSourceDecisionRecord,
    PurchaseSourcePolicy,
    build_purchase_source_evidence,
    compute_purchase_source,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class CandidatePurchaseContext:
    """Persisted purchase context of one Candidate (Offer + MarketplaceProduct)."""

    candidate_id: str
    marketplace_product_id: str
    marketplace: str
    current_price: Decimal
    captured_at: datetime
    shipping_cost: Decimal | None = None
    coupon: Coupon | None = None
    affiliate_commission: Decimal | None = None


class CandidatePurchaseContextRepository(Protocol):
    """Persistence port exposing a Candidate's purchase context."""

    def get_candidate_purchase_context(
        self, candidate_id: str
    ) -> CandidatePurchaseContext | None: ...


class PurchaseSourceDecisionStore(Protocol):
    """Persistence port for append-only purchase source decisions."""

    def save_decision(
        self, record: PurchaseSourceDecisionRecord
    ) -> PurchaseSourceDecisionRecord: ...

    def list_decisions(self, candidate_id: str) -> tuple[PurchaseSourceDecisionRecord, ...]: ...


@dataclass(slots=True)
class PurchaseSourceService:
    """Decide the purchase source and persist the immutable decision."""

    repository: CandidatePurchaseContextRepository
    store: PurchaseSourceDecisionStore
    policy: PurchaseSourcePolicy
    id_factory: IdFactory = default_id_factory
    clock: Callable[[], datetime] = _utcnow

    def decide(
        self,
        candidate_id: str,
        *,
        correlation_id: str,
        product_equivalence_id: str | None = None,
        conditions: Mapping[str, str] | None = None,
        shipping_cost: Decimal | None = None,
        coupon: Coupon | None = None,
        affiliate_commission: Decimal | None = None,
        alternatives: Sequence[PurchaseSource] = (),
    ) -> PurchaseSourceDecisionRecord:
        """Compare the Candidate's affiliate source with reliable alternatives."""

        context = self.repository.get_candidate_purchase_context(candidate_id)
        if context is None:
            raise candidate_not_found_error(candidate_id)

        resolved_coupon = coupon if coupon is not None else (context.coupon or Coupon())
        chosen = PurchaseSource(
            source_id=f"candidate:{candidate_id}",
            price=context.current_price,
            marketplace=context.marketplace,
            shipping_cost=(shipping_cost if shipping_cost is not None else context.shipping_cost),
            coupon=resolved_coupon,
            product_equivalence_id=product_equivalence_id,
            conditions=dict(conditions or {}),
            affiliate_commission=(
                affiliate_commission
                if affiliate_commission is not None
                else context.affiliate_commission
            ),
        )
        created_at = self.clock()
        result = compute_purchase_source(
            candidate_id=candidate_id,
            chosen=chosen,
            alternatives=alternatives,
            policy=self.policy,
            as_of=created_at,
        )
        decision_id = self.id_factory("psd")
        audit_event_id = self.id_factory("aud")
        record = PurchaseSourceDecisionRecord(
            decision_id=decision_id,
            result=result,
            correlation_id=correlation_id,
            audit_event_id=audit_event_id,
            created_at=created_at,
            evidence=build_purchase_source_evidence(
                decision_id=decision_id,
                result=result,
                captured_at=created_at,
                make_id=self.id_factory,
            ),
        )
        return self.store.save_decision(record)

    def list_decisions(self, candidate_id: str) -> tuple[PurchaseSourceDecisionRecord, ...]:
        """Return the immutable decisions of a Candidate, oldest first."""

        if self.repository.get_candidate_purchase_context(candidate_id) is None:
            raise candidate_not_found_error(candidate_id)
        return self.store.list_decisions(candidate_id)


__all__ = [
    "CandidatePurchaseContext",
    "CandidatePurchaseContextRepository",
    "PurchaseSourceDecisionStore",
    "PurchaseSourceService",
]
