"""AffiliateLink orchestration: approved Opportunity + tracking -> validated link
(RDR-018, RDR-070).

The service reads the persisted Candidate product context, the immutable latest
Evaluation and the Opportunity created from it, resolves the internal
:class:`~radar.domain.tracking.TrackingContext` from the versioned label mapping
and asks the configured :class:`~radar.domain.affiliate_link.AffiliateLinkProvider`
(Fake in development) for a link. The validated link is persisted as its own
entity in the same transaction as its ``AuditEvent`` (AUT-033, AUT-141).

The service fails closed (``Correctness -> Safety``): a Candidate that is not
approved, an Opportunity that is not linkable, an unmapped tracking label, a
provider failure or a returned link that does not match the expected host/product
raises a structured error *before* anything is written. Generation is idempotent
for the same Opportunity + label, so a repeated call never duplicates the entity
(AUT-039, AUT-132). It is framework-free (no FastAPI/SQLAlchemy/Chrome) and never
lets AI edit a URL (AUT-078, AUT-164).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from radar.domain.affiliate_link import (
    AFFILIATE_LINK_SCHEMA_VERSION,
    AffiliateLink,
    AffiliateLinkProvider,
    AffiliateLinkRequest,
    affiliate_link_input_invalid_error,
    affiliate_link_not_found_error,
    affiliate_link_opportunity_not_linkable_error,
    build_affiliate_link,
    parse_affiliate_link_response,
)
from radar.domain.allowed_claims import evaluation_not_found_error
from radar.domain.capture import (
    IdFactory,
    Marketplace,
    candidate_not_found_error,
    default_id_factory,
)
from radar.domain.evaluation import Decision, Evaluation
from radar.domain.opportunity import Opportunity, OpportunityState
from radar.domain.tracking import (
    TrackingLabelMapping,
    build_tracking_context,
    tracking_mapping_not_configured_error,
)

#: Opportunity states in which a link may be generated.
LINKABLE_OPPORTUNITY_STATES: frozenset[OpportunityState] = frozenset(
    {OpportunityState.LINK_PENDING, OpportunityState.LINK_READY}
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class CandidateLinkContext:
    """Sanitized persisted product context used to generate an affiliate link."""

    candidate_id: str
    marketplace: Marketplace
    external_id: str
    original_url: str | None
    correlation_id: str


class CandidateLinkContextRepository(Protocol):
    """Persistence port exposing a Candidate's product context for the link step."""

    def get_candidate_link_context(self, candidate_id: str) -> CandidateLinkContext | None: ...


class EvaluationReader(Protocol):
    """Read port for the immutable Evaluations of a Candidate."""

    def list_evaluations(self, candidate_id: str) -> tuple[Evaluation, ...]: ...


class OpportunityReader(Protocol):
    """Read port for the Opportunities created from a Candidate's Evaluation."""

    def list_opportunities(self, candidate_id: str) -> list[Opportunity]: ...


class AffiliateLinkRepository(Protocol):
    """Persistence port for AffiliateLinks."""

    def find_link(self, opportunity_id: str, tracking_label: str) -> AffiliateLink | None: ...

    def save_link(self, link: AffiliateLink) -> AffiliateLink: ...

    def list_links(self, candidate_id: str) -> tuple[AffiliateLink, ...]: ...

    def get_link(self, affiliate_link_id: str) -> AffiliateLink | None: ...


@dataclass(slots=True)
class AffiliateLinkService:
    """Generate and query affiliate links for approved Opportunities."""

    repository: AffiliateLinkRepository
    capture: CandidateLinkContextRepository
    evaluations: EvaluationReader
    opportunities: OpportunityReader
    tracking_labels: TrackingLabelMapping
    provider: AffiliateLinkProvider
    clock: Callable[[], datetime] = _utcnow
    id_factory: IdFactory = default_id_factory

    def generate(
        self,
        candidate_id: str,
        *,
        correlation_id: str,
        tracking_reference: str | None = None,
    ) -> AffiliateLink:
        """Generate (or return) the validated AffiliateLink for a Candidate.

        The Candidate must exist, its latest Evaluation must be ``APPROVE`` and the
        Opportunity created from that Evaluation must be linkable; otherwise the
        request fails closed without calling the provider or writing anything.
        """

        context = self.capture.get_candidate_link_context(candidate_id)
        if context is None:
            raise candidate_not_found_error(candidate_id)
        evaluations = self.evaluations.list_evaluations(candidate_id)
        if not evaluations:
            raise evaluation_not_found_error(candidate_id)
        evaluation = evaluations[-1]
        if evaluation.decision is not Decision.APPROVE:
            raise affiliate_link_opportunity_not_linkable_error(
                candidate_id=candidate_id, state=evaluation.decision.value
            )

        opportunity = next(
            (
                item
                for item in self.opportunities.list_opportunities(candidate_id)
                if item.evaluation_id == evaluation.evaluation_id
            ),
            None,
        )
        if opportunity is None or opportunity.state not in LINKABLE_OPPORTUNITY_STATES:
            raise affiliate_link_opportunity_not_linkable_error(
                candidate_id=candidate_id,
                opportunity_id=None if opportunity is None else opportunity.opportunity_id,
                state=None if opportunity is None else opportunity.state.value,
            )

        reference = tracking_reference or f"{evaluation.brand.value}:{context.marketplace.value}"
        tracking = build_tracking_context(
            opportunity_id=opportunity.opportunity_id,
            marketplace=context.marketplace,
            brand=evaluation.brand,
            internal_reference=reference,
            mapping=self.tracking_labels,
            id_factory=self.id_factory,
        )
        if not tracking.configured or tracking.external_label is None:
            raise tracking_mapping_not_configured_error(
                internal_reference=tracking.internal_reference,
                marketplace=context.marketplace,
            )

        existing = self.repository.find_link(opportunity.opportunity_id, tracking.external_label)
        if existing is not None:
            return existing

        if context.original_url is None:
            raise affiliate_link_input_invalid_error(
                "Candidate sem URL original não pode gerar link afiliado",
                context={"candidate_id": candidate_id},
            )

        request = AffiliateLinkRequest(
            opportunity_id=opportunity.opportunity_id,
            marketplace=context.marketplace,
            original_url=context.original_url,
            external_id=context.external_id,
            tracking=tracking,
        )
        # A provider failure or an invalid response raises here, before the write.
        raw_response = self.provider.generate(request)
        outcome = parse_affiliate_link_response(
            raw_response, provider=self.provider.name, request=request
        )
        now = self.clock()
        link = build_affiliate_link(
            request=request,
            outcome=outcome,
            correlation_id=correlation_id,
            audit_event_id=str(self.id_factory("aud")),
            created_at=now,
            id_factory=self.id_factory,
        )
        return self.repository.save_link(link)

    def list(self, candidate_id: str) -> tuple[AffiliateLink, ...]:
        """Return the persisted AffiliateLinks of a Candidate in chronological order."""

        return self.repository.list_links(candidate_id)

    def get(self, affiliate_link_id: str) -> AffiliateLink:
        """Return one AffiliateLink or fail closed with ``RAD-LINK-002``."""

        link = self.repository.get_link(affiliate_link_id)
        if link is None:
            raise affiliate_link_not_found_error(affiliate_link_id)
        return link


__all__ = [
    "AFFILIATE_LINK_SCHEMA_VERSION",
    "LINKABLE_OPPORTUNITY_STATES",
    "AffiliateLinkRepository",
    "AffiliateLinkService",
    "CandidateLinkContext",
    "CandidateLinkContextRepository",
    "EvaluationReader",
    "OpportunityReader",
]
