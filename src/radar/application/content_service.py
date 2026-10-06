"""ContentGeneration orchestration (RDR-019, RDR-051..RDR-054, RDR-069).

The service reads a persisted Opportunity, the sanitized facts of its Candidate,
the immutable Evaluation and the backend-sustained ``allowed_claims`` (RDR-032),
resolves the validated :class:`~radar.domain.affiliate_link.AffiliateLink`, selects
the minimal Knowledge context for ``brand + channel + task`` and asks the
configured :class:`~radar.domain.content.ContentProvider` (Fake in development) for
a structured Content Generation. The response is validated by the deterministic
local guards before a publishable preview is rendered and persisted as its own
entity in the same transaction as its ``AuditEvent`` (AUT-034, AUT-082, AUT-141).

The service fails closed: a non-approved/missing link, a provider failure, a URL
introduced by the AI or a guard breach (unsupported number/claim) raises a
structured error *before* anything is written, so no publishable preview is
persisted without Evidence (AUT-031, AUT-063). It is framework-free (no
FastAPI/SQLAlchemy/Chrome) and never lets the AI create a link or a price
(AUT-164).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from radar.application.ai_review_service import (
    CandidateAIContext,
    CandidateAIContextRepository,
    ClaimsReader,
    EvaluationReader,
)
from radar.domain.affiliate_link import AffiliateLink
from radar.domain.ai_review import (
    AIReviewEvaluationFacts,
    AIReviewOfferFacts,
    AIReviewProductFacts,
)
from radar.domain.allowed_claims import evaluation_not_found_error
from radar.domain.capture import (
    IdFactory,
    MarketplacePriceHistory,
    candidate_not_found_error,
    default_id_factory,
)
from radar.domain.content import (
    CONTENT_GENERATION_ENGINE_VERSION,
    GENERATE_CONTENT_TASK,
    ContentGeneration,
    ContentGenerationResolution,
    ContentProvider,
    build_content_generation,
    build_content_generation_input,
    canonical_ai_input_hash,
    canonical_money,
    content_generation_not_found_error,
    content_input_invalid_error,
    current_price_claim_value,
    is_stale,
    parse_generate_content_response,
    raise_for_validation,
    render_content,
    validate_generated_content,
)
from radar.domain.knowledge import Channel, KnowledgePack, select_knowledge_context
from radar.domain.operations import ChannelCompliancePolicy
from radar.domain.opportunity import (
    TERMINAL_OPPORTUNITY_STATES,
    Opportunity,
    opportunity_not_found_error,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class OpportunityReader(Protocol):
    """Read port for Opportunities."""

    def get_opportunity(self, opportunity_id: str) -> Opportunity | None: ...


class AffiliateLinkReader(Protocol):
    """Read port for the validated AffiliateLink of an Opportunity."""

    def find_link_for_opportunity(self, opportunity_id: str) -> AffiliateLink | None: ...


class PriceHistoryReader(Protocol):
    """Read port for the append-only price history of a MarketplaceProduct."""

    def get_price_history(self, marketplace_product_id: str) -> MarketplacePriceHistory | None: ...


class ContentGenerationRepository(Protocol):
    """Persistence port for ContentGenerations."""

    def save_content_generation(self, record: ContentGeneration) -> ContentGeneration: ...

    def list_content_generations(self, opportunity_id: str) -> tuple[ContentGeneration, ...]: ...

    def get_content_generation(self, content_generation_id: str) -> ContentGeneration | None: ...

    def list_content_generations_by_ai_input_hash(
        self, opportunity_id: str, ai_input_hash: str
    ) -> tuple[ContentGeneration, ...]: ...


@dataclass(slots=True)
class ContentGenerationService:
    """Generate, render and query validated content previews of an Opportunity."""

    repository: ContentGenerationRepository
    opportunities: OpportunityReader
    capture: CandidateAIContextRepository
    evaluations: EvaluationReader
    claims: ClaimsReader
    links: AffiliateLinkReader
    price_history: PriceHistoryReader
    knowledge: KnowledgePack
    provider: ContentProvider
    compliance: ChannelCompliancePolicy
    clock: Callable[[], datetime] = _utcnow
    id_factory: IdFactory = default_id_factory

    def generate(
        self,
        opportunity_id: str,
        *,
        channel: Channel,
        correlation_id: str,
    ) -> ContentGenerationResolution:
        """Resolve the content preview of one Opportunity (RDR-019, RDR-055).

        The Opportunity must exist, be non-terminal and already carry a validated
        AffiliateLink; otherwise the request fails closed before the provider is
        called or anything is written. When an equivalent input was already
        generated and is still valid, the persisted generation is reused without a
        new provider call (``cache_hit=True``); a relevant change to product/offer,
        scores, warnings or Knowledge/Prompt versions invalidates the cache.
        """

        opportunity = self.opportunities.get_opportunity(opportunity_id)
        if opportunity is None:
            raise opportunity_not_found_error(opportunity_id)
        if opportunity.state in TERMINAL_OPPORTUNITY_STATES:
            raise content_input_invalid_error(
                "Opportunity terminal não gera conteúdo",
                context={"opportunity_id": opportunity_id, "state": opportunity.state.value},
            )

        context = self.capture.get_candidate_ai_context(opportunity.candidate_id)
        if context is None:
            raise candidate_not_found_error(opportunity.candidate_id)

        evaluation = next(
            (
                item
                for item in self.evaluations.list_evaluations(opportunity.candidate_id)
                if item.evaluation_id == opportunity.evaluation_id
            ),
            None,
        )
        if evaluation is None:
            raise evaluation_not_found_error(opportunity.candidate_id)

        link = self.links.find_link_for_opportunity(opportunity_id)
        if link is None:
            raise content_input_invalid_error(
                "Opportunity sem AffiliateLink validado não gera conteúdo",
                context={"opportunity_id": opportunity_id},
            )

        claims = self.claims.get(opportunity.candidate_id, evaluation_id=opportunity.evaluation_id)
        knowledge = select_knowledge_context(
            self.knowledge,
            brand=evaluation.brand,
            channel=channel,
            task=GENERATE_CONTENT_TASK,
        )
        request = build_content_generation_input(
            candidate_id=opportunity.candidate_id,
            opportunity_id=opportunity_id,
            marketplace=context.marketplace,
            product=AIReviewProductFacts(
                external_id=context.external_id,
                title=context.title,
                category=context.raw_category,
                url=context.url,
            ),
            offer=AIReviewOfferFacts(
                current_price=str(context.current_price),
                original_price=(
                    None if context.original_price is None else str(context.original_price)
                ),
                sales_count=context.sales_count,
                seller_name=context.seller_name,
            ),
            evaluation=AIReviewEvaluationFacts(
                evaluation_id=evaluation.evaluation_id,
                decision=evaluation.decision.value,
                deal_score=None if evaluation.deal_score is None else str(evaluation.deal_score),
                monetization_score=evaluation.monetization_score,
                confidence=None if evaluation.confidence is None else evaluation.confidence.value,
            ),
            knowledge=knowledge,
            allowed_claims=claims.to_contract()["claims"],
            omitted_claims=claims.to_contract()["omitted_claims"],
            forbidden_claims=claims.to_contract()["forbidden_claims"],
        )

        # An equivalent, still-valid input reuses the persisted generation and
        # never calls the provider (RDR-055). ``is_stale`` also guards facts the
        # provider input does not carry (e.g. the validated affiliate URL), so a
        # matching-but-stale row is skipped instead of being served.
        ai_input_hash = canonical_ai_input_hash(request)
        for candidate in self.repository.list_content_generations_by_ai_input_hash(
            opportunity_id, ai_input_hash
        ):
            if not self.is_stale(candidate):
                return ContentGenerationResolution(record=candidate, cache_hit=True)

        # Provider failure/refusal/invalid schema/URL raises here, before any write.
        raw_response = self.provider.generate_content(request)
        generated = parse_generate_content_response(raw_response, provider=self.provider.name)

        now = self.clock()
        validation = validate_generated_content(
            generated=generated,
            claims=claims,
            channel=channel,
            compliance_policy=self.compliance,
            now=now,
        )
        # A guard breach (unsupported number/claim, channel, compliance) fails
        # closed: no publishable preview is persisted.
        raise_for_validation(validation, channel=channel)

        price = current_price_claim_value(claims)
        if price is None:
            raise content_input_invalid_error(
                "Sem CURRENT_PRICE sustentado não há preço de renderer",
                context={"candidate_id": opportunity.candidate_id},
            )
        rendered = render_content(
            generated=generated,
            price=price,
            affiliate_url=link.affiliate_url,
            tracking=link.tracking.to_contract(),
        )
        facts = _build_facts(
            opportunity=opportunity,
            context=context,
            channel=channel,
            knowledge_version=knowledge.knowledge_version,
            prompt_version=knowledge.prompt_version,
            price=price,
            affiliate_url=link.affiliate_url,
        )
        record = build_content_generation(
            request=request,
            generated=generated,
            rendered=rendered,
            validation=validation,
            facts=facts,
            correlation_id=correlation_id,
            audit_event_id=str(self.id_factory("aud")),
            created_at=now,
            id_factory=self.id_factory,
        )
        saved = self.repository.save_content_generation(record)
        return ContentGenerationResolution(record=saved, cache_hit=False)

    def list(self, opportunity_id: str) -> tuple[ContentGeneration, ...]:
        """Return the persisted ContentGenerations of an Opportunity, oldest first."""

        return self.repository.list_content_generations(opportunity_id)

    def get(self, content_generation_id: str) -> ContentGeneration:
        """Return one ContentGeneration or fail closed with ``RAD-AI-011``."""

        record = self.repository.get_content_generation(content_generation_id)
        if record is None:
            raise content_generation_not_found_error(content_generation_id)
        return record

    def is_stale(self, record: ContentGeneration) -> bool:
        """Return True when a relevant fact changed after the content was generated.

        The check is read-only and deterministic: it recomputes the current facts
        (latest own price observation, current validated link, current
        knowledge/prompt version) and compares their canonical hash with the
        snapshot stored at generation time (``docs/08_WORKFLOW_ENGINE.md``).
        """

        return is_stale(record, current_facts=self._current_facts(record))

    def _current_facts(self, record: ContentGeneration) -> Mapping[str, Any]:
        facts: dict[str, Any] = dict(record.facts)
        marketplace_product_id = facts.get("marketplace_product_id")
        if isinstance(marketplace_product_id, str):
            history = self.price_history.get_price_history(marketplace_product_id)
            if history is not None and history.observations:
                facts["price"] = canonical_money(history.observations[-1].price)
        link = self.links.find_link_for_opportunity(record.opportunity_id)
        if link is not None:
            facts["affiliate_url"] = link.affiliate_url
        facts["knowledge_version"] = self.knowledge.knowledge_version
        facts["prompt_version"] = self.knowledge.prompt_version
        facts["generation_version"] = CONTENT_GENERATION_ENGINE_VERSION
        return facts


def _build_facts(
    *,
    opportunity: Opportunity,
    context: CandidateAIContext,
    channel: Channel,
    knowledge_version: str,
    prompt_version: str,
    price: str,
    affiliate_url: str,
) -> Mapping[str, Any]:
    return {
        "opportunity_id": opportunity.opportunity_id,
        "candidate_id": opportunity.candidate_id,
        "marketplace_product_id": context.marketplace_product_id,
        "channel": channel.value,
        "generation_version": CONTENT_GENERATION_ENGINE_VERSION,
        "knowledge_version": knowledge_version,
        "prompt_version": prompt_version,
        "price": canonical_money(price),
        "affiliate_url": affiliate_url,
    }


__all__ = [
    "AffiliateLinkReader",
    "CandidateAIContext",
    "CandidateAIContextRepository",
    "ClaimsReader",
    "ContentGenerationRepository",
    "ContentGenerationService",
    "ContentProvider",
    "EvaluationReader",
    "OpportunityReader",
    "PriceHistoryReader",
    "content_generation_not_found_error",
    "content_input_invalid_error",
]
