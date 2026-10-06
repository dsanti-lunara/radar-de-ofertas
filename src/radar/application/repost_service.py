"""Repost guardrail orchestration (RDR-033).

The service reads a persisted Candidate's Offer through a narrow port, takes the
Deal score from the latest immutable Evaluation (RDR-016), combines them with the
publication history supplied by the caller (a *fake* history until the real
publisher exists) and applies the deterministic
:mod:`radar.domain.repost` guardrail. The resulting decision is persisted
append-only together with its Evidence and audit event, so the guardrail is
observable and traceable from the public boundary.

The coupon/conditions the manual capture does not persist yet can be supplied at
decision time; they are validated by the public boundary and never trusted
blindly. A material coupon/condition is only accepted with caller-supplied
Evidence. No AI is called, no affiliate link is generated and nothing is
published here (AUT-031, AUT-007).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from radar.domain.capture import IdFactory, candidate_not_found_error, default_id_factory
from radar.domain.evaluation import Evaluation
from radar.domain.price_opportunity import Coupon
from radar.domain.repost import (
    PublicationSnapshot,
    RepostDecisionRecord,
    RepostEvidence,
    RepostFacts,
    RepostPolicy,
    build_repost_evidence,
    compute_repost,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class CandidateRepostContext:
    """Persisted facts of one Candidate used by the repost guardrail."""

    candidate_id: str
    current_price: Decimal
    captured_at: datetime
    correlation_id: str
    raw_capture_id: str
    coupon: Coupon | None = None


class CandidateRepostRepository(Protocol):
    """Persistence port exposing a Candidate's repost context."""

    def get_candidate_repost_context(self, candidate_id: str) -> CandidateRepostContext | None: ...


class EvaluationReader(Protocol):
    """Read port for the immutable Evaluations of a Candidate."""

    def list_evaluations(self, candidate_id: str) -> tuple[Evaluation, ...]: ...


class RepostDecisionStore(Protocol):
    """Persistence port for append-only repost decisions."""

    def save_decision(self, record: RepostDecisionRecord) -> RepostDecisionRecord: ...

    def list_decisions(self, candidate_id: str) -> tuple[RepostDecisionRecord, ...]: ...


def _latest_deal_score(evaluations: tuple[Evaluation, ...]) -> Decimal | None:
    if not evaluations:
        return None
    return evaluations[-1].deal_score


@dataclass(slots=True)
class RepostService:
    """Decide whether a Candidate may be reposted and persist the decision."""

    repository: CandidateRepostRepository
    evaluations: EvaluationReader
    store: RepostDecisionStore
    policy: RepostPolicy
    id_factory: IdFactory = default_id_factory
    clock: Callable[[], datetime] = _utcnow

    def decide(
        self,
        candidate_id: str,
        *,
        correlation_id: str,
        publications: Sequence[PublicationSnapshot] = (),
        coupon: Coupon | None = None,
        conditions: Mapping[str, str] | None = None,
        evidence: Sequence[RepostEvidence] = (),
    ) -> RepostDecisionRecord:
        """Apply the dedupe/repost guardrail and persist the decision."""

        context = self.repository.get_candidate_repost_context(candidate_id)
        if context is None:
            raise candidate_not_found_error(candidate_id)

        created_at = self.clock()
        deal_score = _latest_deal_score(self.evaluations.list_evaluations(candidate_id))
        resolved_coupon = coupon if coupon is not None else context.coupon
        result = compute_repost(
            candidate_id=candidate_id,
            facts=RepostFacts(
                current_price=context.current_price,
                deal_score=deal_score,
                coupon=resolved_coupon,
                conditions=dict(conditions or {}),
                evidence=tuple(evidence),
            ),
            publication_history=tuple(publications),
            policy=self.policy,
            as_of=created_at,
        )
        decision_id = self.id_factory("rpd")
        audit_event_id = self.id_factory("aud")
        record = RepostDecisionRecord(
            decision_id=decision_id,
            result=result,
            correlation_id=correlation_id,
            audit_event_id=audit_event_id,
            created_at=created_at,
            evidence=build_repost_evidence(
                decision_id=decision_id,
                result=result,
                captured_at=created_at,
                make_id=self.id_factory,
                supplied_evidence=tuple(evidence),
            ),
        )
        return self.store.save_decision(record)

    def list_decisions(self, candidate_id: str) -> tuple[RepostDecisionRecord, ...]:
        """Return the immutable repost decisions of a Candidate, oldest first."""

        if self.repository.get_candidate_repost_context(candidate_id) is None:
            raise candidate_not_found_error(candidate_id)
        return self.store.list_decisions(candidate_id)


__all__ = [
    "CandidateRepostContext",
    "CandidateRepostRepository",
    "EvaluationReader",
    "RepostDecisionStore",
    "RepostService",
]
