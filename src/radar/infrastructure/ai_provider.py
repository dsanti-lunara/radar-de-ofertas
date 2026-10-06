"""Deterministic Fake AI provider (RDR-047).

``FakeAIProvider`` is the development provider of ``docs/06_AI_ENGINE.md``
(RDR-047). It satisfies the framework-free :class:`~radar.domain.ai_review.AIProvider`
contract without any network, credential, clock or filesystem access: it computes
a deterministic Editorial Review from the already-decided Evaluation and the
backend-sustained ``allowed_claims`` only. Marketplace content is treated as inert
data, so a product title can never steer the decision or trigger ``AUTO_PUBLISH``
(AUT-275, AUT-276).

The real provider remains gated by SPIKE-01/RDR-048 and is not implemented here.
"""

from __future__ import annotations

from typing import Any

from radar.domain.ai_review import AIReviewInput, EditorialDecision
from radar.domain.evaluation import Decision

#: Provider identity recorded on every AIReview produced by the fake.
FAKE_PROVIDER_NAME = "fake"
FAKE_PROVIDER_MODEL = "fake-editorial-review-1.0"

#: Reason codes emitted deterministically by the fake provider.
REASON_EDITORIAL_PASSED = "EDITORIAL_REVIEW_PASSED"
REASON_EVALUATION_REVIEW_REQUIRED = "EVALUATION_REVIEW_REQUIRED"
REASON_EVALUATION_REJECTED = "EVALUATION_REJECTED"
REASON_PRICE_CONTEXT_AVAILABLE = "PRICE_CONTEXT_AVAILABLE"
REASON_COUPON_CONTEXT_AVAILABLE = "COUPON_CONTEXT_AVAILABLE"

#: Editorial angles selected from the available claim context.
ANGLE_PRICE_OPPORTUNITY = "PRICE_OPPORTUNITY"
ANGLE_CONFIRMED_COUPON = "CONFIRMED_COUPON"
ANGLE_GENERAL = "GENERAL"

_PRICE_CLAIM_TYPES = frozenset(
    {"PREVIOUS_OBSERVED_PRICE", "PRICE_DROP_PERCENT", "LOWEST_OBSERVED_30D"}
)


def _claim_types(request: AIReviewInput) -> set[str]:
    return {
        str(claim.get("claim_type"))
        for claim in request.allowed_claims
        if isinstance(claim, dict) and claim.get("claim_type")
    }


class FakeAIProvider:
    """Deterministic, offline implementation of the ``AIProvider`` contract."""

    def __init__(self) -> None:
        self._name = FAKE_PROVIDER_NAME
        self._model = FAKE_PROVIDER_MODEL

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    def evaluate_candidate(self, request: AIReviewInput) -> dict[str, Any]:
        """Return a deterministic Editorial Review response mapping.

        The backend decision always precedes the AI: a ``REJECT``/``REVIEW``
        Evaluation is never overridden into an approval (AUT-056). Only an
        ``APPROVE`` Evaluation yields an ``APPROVE`` editorial decision, and the
        angle is derived from the claim types the backend sustains.
        """

        decision = request.evaluation.decision
        if decision == Decision.REJECT.value:
            return self._response(
                EditorialDecision.REJECT,
                angle=None,
                reason_codes=[REASON_EVALUATION_REJECTED],
            )
        if decision == Decision.REVIEW.value:
            return self._response(
                EditorialDecision.REVIEW,
                angle=None,
                reason_codes=[REASON_EVALUATION_REVIEW_REQUIRED],
            )

        claim_types = _claim_types(request)
        reason_codes = [REASON_EDITORIAL_PASSED]
        if claim_types & _PRICE_CLAIM_TYPES:
            reason_codes.append(REASON_PRICE_CONTEXT_AVAILABLE)
        if "CONFIRMED_COUPON" in claim_types:
            reason_codes.append(REASON_COUPON_CONTEXT_AVAILABLE)
            angle = ANGLE_CONFIRMED_COUPON
        elif claim_types & _PRICE_CLAIM_TYPES:
            angle = ANGLE_PRICE_OPPORTUNITY
        else:
            angle = ANGLE_GENERAL
        return self._response(EditorialDecision.APPROVE, angle=angle, reason_codes=reason_codes)

    @staticmethod
    def _response(
        decision: EditorialDecision,
        *,
        angle: str | None,
        reason_codes: list[str],
    ) -> dict[str, Any]:
        return {
            "decision": decision.value,
            "editorial_angle": angle,
            "reason_codes": reason_codes,
            "warnings": [],
        }


__all__ = [
    "ANGLE_CONFIRMED_COUPON",
    "ANGLE_GENERAL",
    "ANGLE_PRICE_OPPORTUNITY",
    "FAKE_PROVIDER_MODEL",
    "FAKE_PROVIDER_NAME",
    "FakeAIProvider",
]
