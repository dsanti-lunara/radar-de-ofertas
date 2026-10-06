"""Opportunity review read model and auditable human review (RDR-058..RDR-060).

This module implements the objective of TKT-26: list Candidates/Opportunities,
consult the Evidence/breakdown and register a human review, all through the
public boundary. It is framework-free (no FastAPI/SQLAlchemy/Chrome):

* :class:`ReviewService.inbox` builds the Opportunity Inbox read model from the
  persisted capture/Evaluation/AIReview/HumanReview rows (docs/11);
* :class:`ReviewService.detail` composes the Candidate detail with its score
  breakdown, warnings, price history, Evidence and a merged timeline that
  carries the versions of each decision;
* :class:`ReviewService.register` records an immutable :class:`HumanReview` and
  **never** triggers a commercial send. Approving a Candidate is not a
  publication approval (GRILL-001): the response always reports
  ``publication_authorized=false`` and the current operational gate, so SHADOW
  accepts a review while still blocking every PUBLISH (AUT-035/AUT-036).

The store port is provided by infrastructure; the operational gate decision is
the pure :func:`decide_external_action` domain function, so a read never writes
an audit event.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from radar.domain.audit import HUMAN_REVIEW_RECORDED, AuditEvent
from radar.domain.capture import IdFactory, default_id_factory
from radar.domain.human_review import (
    AUDIT_SOURCE_HUMAN_REVIEW,
    ENTITY_HUMAN_REVIEW,
    HumanReview,
    build_human_review,
    human_review_input_invalid_error,
    human_review_not_found_error,
    review_candidate_not_found_error,
)
from radar.domain.operations import (
    AutomationPolicy,
    ChannelCompliancePolicy,
    ExternalAction,
    ExternalActionRequest,
    OperationalState,
    decide_external_action,
)
from radar.domain.taxonomy import Brand

#: Version of the public review contracts (``docs/04_DATA_CONTRACTS.md``).
REVIEW_SCHEMA_VERSION = "1.0"

#: Operator-facing note that keeps Candidate approval and publication approval
#: separate on every review response (GRILL-001).
CANDIDATE_APPROVAL_NOTE = (
    "Aprovação de Candidate não autoriza publicação; em ASSISTED o envio exige "
    "aprovação humana explícita da publicação e os guardrails vigentes."
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class AutomationView:
    """Operational gate observed from the public boundary (TKT-17/GRILL-001).

    The decision is computed for a ``PUBLISH`` request **without** the explicit
    publication approval, so a Candidate approval can never be mistaken for a
    publication approval: in SHADOW/ASSISTED ``publish_allowed`` stays false.
    """

    automation_mode: str
    global_mode: str
    stop_external_actions: bool
    compliance_status: str
    publish_allowed: bool
    publish_reason_code: str
    publish_message: str
    automation_policy_version: str
    compliance_policy_version: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "automation_mode": self.automation_mode,
            "global_mode": self.global_mode,
            "stop_external_actions": self.stop_external_actions,
            "compliance_status": self.compliance_status,
            "publish_allowed": self.publish_allowed,
            "publish_reason_code": self.publish_reason_code,
            "publish_message": self.publish_message,
            "automation_policy_version": self.automation_policy_version,
            "compliance_policy_version": self.compliance_policy_version,
        }


def build_automation_view(
    *,
    automation_policy: AutomationPolicy,
    compliance_policy: ChannelCompliancePolicy,
    operational_state: OperationalState,
    brand: Brand | None,
    now: datetime,
    correlation_id: str,
) -> AutomationView:
    """Compute the operational gate for a publication that this review never approved."""

    decision = decide_external_action(
        request=ExternalActionRequest(action=ExternalAction.PUBLISH, brand=brand),
        operational_state=operational_state,
        automation_policy=automation_policy,
        compliance_policy=compliance_policy,
        now=now,
        correlation_id=correlation_id,
    )
    return AutomationView(
        automation_mode=decision.automation_mode.value,
        global_mode=decision.global_mode.value,
        stop_external_actions=decision.stop_external_actions,
        compliance_status=decision.compliance_status.value,
        publish_allowed=decision.allowed,
        publish_reason_code=decision.reason_code,
        publish_message=decision.message,
        automation_policy_version=decision.automation_policy_version,
        compliance_policy_version=decision.compliance_policy_version,
    )


@dataclass(frozen=True, slots=True)
class InboxItem:
    """One Candidate/Opportunity row of the Opportunity Inbox (RDR-058)."""

    candidate_id: str
    candidate_state: str
    marketplace: str
    external_id: str
    title: str | None
    url: str | None
    current_price: str | None
    original_price: str | None
    brand: str | None
    deal_score: str | None
    monetization_score: int | None
    confidence: str | None
    decision: str | None
    main_reason: str | None
    opportunity_id: str | None
    opportunity_state: str | None
    ai_decision: str | None
    human_decision: str | None
    created_at: str
    updated_at: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_state": self.candidate_state,
            "marketplace": self.marketplace,
            "external_id": self.external_id,
            "title": self.title,
            "url": self.url,
            "current_price": self.current_price,
            "original_price": self.original_price,
            "brand": self.brand,
            "deal_score": self.deal_score,
            "monetization_score": self.monetization_score,
            "confidence": self.confidence,
            "decision": self.decision,
            "main_reason": self.main_reason,
            "opportunity_id": self.opportunity_id,
            "opportunity_state": self.opportunity_state,
            "ai_decision": self.ai_decision,
            "human_decision": self.human_decision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    """One append-only audit event of the Candidate timeline (RDR-059)."""

    event_type: str
    entity_type: str
    entity_id: str
    source: str
    correlation_id: str
    recorded_at: str
    payload: Mapping[str, Any]

    def to_contract(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "recorded_at": self.recorded_at,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True, slots=True)
class PricePointView:
    """One append-only price observation shown in the detail (RDR-013)."""

    price_observation_id: str
    price: str
    original_price: str | None
    shipping_cost: str | None
    source: str
    observed_at: str
    correlation_id: str
    raw_capture_id: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "price_observation_id": self.price_observation_id,
            "price": self.price,
            "original_price": self.original_price,
            "shipping_cost": self.shipping_cost,
            "source": self.source,
            "observed_at": self.observed_at,
            "correlation_id": self.correlation_id,
            "raw_capture_id": self.raw_capture_id,
        }


@dataclass(frozen=True, slots=True)
class EvidenceView:
    """One Evidence row that sustains the shown facts (RDR-014, AUT-029)."""

    evidence_id: str
    entity_type: str
    entity_id: str
    field_name: str
    value: str
    source_type: str
    source_url: str | None
    captured_at: str
    confidence: str | None
    raw_reference: str | None

    def to_contract(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "field_name": self.field_name,
            "value": self.value,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "captured_at": self.captured_at,
            "confidence": self.confidence,
            "raw_reference": self.raw_reference,
        }


@dataclass(frozen=True, slots=True)
class VersionView:
    """Versions of every artifact the detail exposes (AUT-065)."""

    scoring_version: str | None
    deal_scoring_version: str | None
    monetization_scoring_version: str | None
    confidence_scoring_version: str | None
    taxonomy_version: str | None
    taxonomy_hash: str | None
    ai_knowledge_version: str | None
    ai_prompt_version: str | None

    def to_contract(self) -> dict[str, Any]:
        return {
            "scoring_version": self.scoring_version,
            "deal_scoring_version": self.deal_scoring_version,
            "monetization_scoring_version": self.monetization_scoring_version,
            "confidence_scoring_version": self.confidence_scoring_version,
            "taxonomy_version": self.taxonomy_version,
            "taxonomy_hash": self.taxonomy_hash,
            "ai_knowledge_version": self.ai_knowledge_version,
            "ai_prompt_version": self.ai_prompt_version,
        }


@dataclass(frozen=True, slots=True)
class ReviewDetail:
    """Candidate detail read model of the Opportunity detail screen (RDR-059)."""

    candidate: Mapping[str, Any]
    evaluation: Mapping[str, Any] | None
    evaluations: tuple[Mapping[str, Any], ...]
    price_history: tuple[PricePointView, ...]
    evidence: tuple[EvidenceView, ...]
    ai_reviews: tuple[Mapping[str, Any], ...]
    human_reviews: tuple[Mapping[str, Any], ...]
    opportunity: Mapping[str, Any] | None
    opportunity_history: tuple[TimelineEntry, ...]
    timeline: tuple[TimelineEntry, ...]
    versions: VersionView
    correlation_id: str
    automation: AutomationView | None = None

    def to_contract(self) -> dict[str, Any]:
        return {
            "candidate": dict(self.candidate),
            "evaluation": None if self.evaluation is None else dict(self.evaluation),
            "evaluations": [dict(item) for item in self.evaluations],
            "price_history": [point.to_contract() for point in self.price_history],
            "evidence": [item.to_contract() for item in self.evidence],
            "ai_reviews": [dict(item) for item in self.ai_reviews],
            "human_reviews": [dict(item) for item in self.human_reviews],
            "opportunity": None if self.opportunity is None else dict(self.opportunity),
            "opportunity_history": [entry.to_contract() for entry in self.opportunity_history],
            "timeline": [entry.to_contract() for entry in self.timeline],
            "versions": self.versions.to_contract(),
            "automation": None if self.automation is None else self.automation.to_contract(),
        }


@dataclass(frozen=True, slots=True)
class HumanReviewResult:
    """Observable outcome of registering a human review (RDR-060)."""

    review: HumanReview
    automation: AutomationView

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": REVIEW_SCHEMA_VERSION,
            "status": "RECORDED",
            "human_review": self.review.to_contract(),
            "publication_authorized": False,
            "note": CANDIDATE_APPROVAL_NOTE,
            "automation": self.automation.to_contract(),
            "correlation_id": self.review.correlation_id,
        }


@dataclass(frozen=True, slots=True)
class AiReviewRef:
    """Snapshot of the AI editorial decision a HumanReview is compared against."""

    ai_review_id: str
    decision: str


class ReviewStore(Protocol):
    """Persistence port for the review read model and human decisions."""

    def save_human_review(
        self, review: HumanReview, audit_events: tuple[AuditEvent, ...]
    ) -> None: ...

    def get_human_review(self, human_review_id: str) -> HumanReview | None: ...

    def list_human_reviews(self, candidate_id: str) -> tuple[HumanReview, ...]: ...

    def get_ai_review_ref(
        self, candidate_id: str, ai_review_id: str | None = None
    ) -> AiReviewRef | None: ...

    def list_inbox(self) -> tuple[InboxItem, ...]: ...

    def get_detail(self, candidate_id: str) -> ReviewDetail | None: ...


@dataclass(slots=True)
class ReviewService:
    """Serve the Opportunity Inbox/detail and record auditable human reviews."""

    store: ReviewStore
    automation_policy: AutomationPolicy
    compliance_policy: ChannelCompliancePolicy
    operational_state: Callable[[], OperationalState]
    clock: Callable[[], datetime] = _utcnow
    id_factory: IdFactory = default_id_factory

    def inbox(self) -> tuple[InboxItem, ...]:
        """Return every Candidate/Opportunity row of the Inbox (RDR-058)."""

        return self.store.list_inbox()

    def detail(self, candidate_id: str) -> ReviewDetail:
        """Return the Candidate detail or fail closed with ``RAD-UI-003``."""

        detail = self.store.get_detail(candidate_id)
        if detail is None:
            raise review_candidate_not_found_error(candidate_id)
        return replace(
            detail,
            automation=self._automation_view(
                detail=detail, now=self.clock(), correlation_id=detail.correlation_id
            ),
        )

    def list_reviews(self, candidate_id: str) -> tuple[HumanReview, ...]:
        """Return the append-only HumanReviews of a Candidate, oldest first."""

        if self.store.get_detail(candidate_id) is None:
            raise review_candidate_not_found_error(candidate_id)
        return self.store.list_human_reviews(candidate_id)

    def get_review(self, human_review_id: str) -> HumanReview:
        """Return one HumanReview or fail closed with ``RAD-UI-002``."""

        review = self.store.get_human_review(human_review_id)
        if review is None:
            raise human_review_not_found_error(human_review_id)
        return review

    def register(
        self,
        candidate_id: str,
        *,
        human_decision: object,
        reason: object,
        correlation_id: str,
        ai_review_id: object = None,
        note: object = None,
        edited_content: object = None,
    ) -> HumanReviewResult:
        """Record an immutable human decision without any commercial send."""

        detail = self.store.get_detail(candidate_id)
        if detail is None:
            raise review_candidate_not_found_error(candidate_id)
        resolved_ai_review_id = None if ai_review_id is None else str(ai_review_id)
        ai_ref = self.store.get_ai_review_ref(candidate_id, resolved_ai_review_id)
        if resolved_ai_review_id is not None and ai_ref is None:
            raise human_review_input_invalid_error(
                "ai_review_id não pertence ao Candidate informado",
                context={"field": "ai_review_id", "candidate_id": candidate_id},
            )
        now = self.clock()
        review = build_human_review(
            candidate_id=candidate_id,
            human_decision=human_decision,
            reason=reason,
            ai_review_id=None if ai_ref is None else ai_ref.ai_review_id,
            ai_decision=None if ai_ref is None else ai_ref.decision,
            note=note,
            edited_content=edited_content,
            correlation_id=correlation_id,
            now=now,
            id_factory=self.id_factory,
        )
        audit = AuditEvent(
            id=review.audit_event_id,
            event_type=HUMAN_REVIEW_RECORDED,
            entity_type=ENTITY_HUMAN_REVIEW,
            entity_id=review.human_review_id,
            source=AUDIT_SOURCE_HUMAN_REVIEW,
            correlation_id=review.correlation_id,
            recorded_at=now,
            payload={
                "candidate_id": candidate_id,
                "ai_review_id": review.ai_review_id,
                "ai_decision": review.ai_decision,
                "human_decision": review.human_decision.value,
                "reason": review.reason,
                "publication_authorized": False,
            },
        )
        self.store.save_human_review(review, (audit,))
        automation = self._automation_view(detail=detail, now=now, correlation_id=correlation_id)
        return HumanReviewResult(review=review, automation=automation)

    def _automation_view(
        self, *, detail: ReviewDetail, now: datetime, correlation_id: str
    ) -> AutomationView:
        brand_value = detail.candidate.get("brand")
        brand = None if brand_value is None else Brand(str(brand_value))
        return build_automation_view(
            automation_policy=self.automation_policy,
            compliance_policy=self.compliance_policy,
            operational_state=self.operational_state(),
            brand=brand,
            now=now,
            correlation_id=correlation_id,
        )


__all__ = [
    "CANDIDATE_APPROVAL_NOTE",
    "REVIEW_SCHEMA_VERSION",
    "AiReviewRef",
    "AutomationView",
    "EvidenceView",
    "HumanReviewResult",
    "InboxItem",
    "PricePointView",
    "ReviewDetail",
    "ReviewService",
    "ReviewStore",
    "TimelineEntry",
    "VersionView",
    "build_automation_view",
]
