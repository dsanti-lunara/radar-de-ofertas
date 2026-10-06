"""ContentGeneration public endpoints (RDR-019, RDR-051..RDR-054, RDR-069).

``POST /opportunities/{opportunity_id}/content-generations`` runs the configured
:class:`~radar.domain.content.ContentProvider` (Fake in development) against the
sanitized facts, the immutable Evaluation, the backend-sustained allowed claims and
the validated AffiliateLink, applies the deterministic local guards, renders the
final content with backend price/link/disclosure and persists the versioned
``ContentGeneration``. An equivalent, still-valid input reuses the persisted
generation and reports ``cache_hit=true`` without calling the provider again
(RDR-055). ``GET`` endpoints expose the append-only previews; a missing
one returns ``RAD-AI-011`` and a preview whose relevant facts changed is reported
as ``STALE``.

The boundary fails closed: a provider failure/refusal, an AI-invented URL or a
guard breach (unsupported number/claim) returns a structured error and writes
nothing, so no publishable preview is produced without Evidence. No score, link,
compliance decision or publication is produced here (AUT-031, AUT-082, AUT-164).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import CORRELATION_HEADER, ContentGenerationRequestContract
from radar.application.allowed_claims_service import AllowedClaimsService
from radar.application.content_service import ContentGenerationService
from radar.application.correlation import bind_correlation_id
from radar.domain.content import CONTENT_SCHEMA_VERSION, ContentProvider
from radar.domain.knowledge import KnowledgePack
from radar.domain.operations import ChannelCompliancePolicy
from radar.infrastructure.affiliate_link_repository import SqlAlchemyAffiliateLinkRepository
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.content_repository import SqlAlchemyContentGenerationRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from radar.infrastructure.opportunity_repository import SqlAlchemyWorkflowRepository


def build_content_generation_service(
    engine: Engine,
    knowledge_pack: KnowledgePack,
    provider: ContentProvider,
    compliance_policy: ChannelCompliancePolicy,
) -> ContentGenerationService:
    """Wire the ContentGeneration service once for the content/publication routers."""

    capture = SqlAlchemyCaptureRepository(engine=engine)
    evaluations = SqlAlchemyEvaluationRepository(engine=engine)
    return ContentGenerationService(
        repository=SqlAlchemyContentGenerationRepository(engine=engine),
        opportunities=SqlAlchemyWorkflowRepository(engine=engine),
        capture=capture,
        evaluations=evaluations,
        claims=AllowedClaimsService(repository=capture, evaluations=evaluations),
        links=SqlAlchemyAffiliateLinkRepository(engine=engine),
        price_history=capture,
        knowledge=knowledge_pack,
        provider=provider,
        compliance=compliance_policy,
    )


def build_content_generation_router(
    engine: Engine,
    knowledge_pack: KnowledgePack,
    provider: ContentProvider,
    compliance_policy: ChannelCompliancePolicy,
) -> APIRouter:
    """Build the content generation router wired to SQLite, knowledge and provider."""

    router = APIRouter(tags=["content-generations"])
    service = build_content_generation_service(engine, knowledge_pack, provider, compliance_policy)

    @router.post("/opportunities/{opportunity_id}/content-generations")
    def generate_content_generation(
        opportunity_id: str,
        payload: ContentGenerationRequestContract,
        request: Request,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        resolution = service.generate(
            opportunity_id,
            channel=payload.channel,
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=201,
            content=resolution.to_contract(stale=False),
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/opportunities/{opportunity_id}/content-generations")
    def list_content_generations(opportunity_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        records = service.list(opportunity_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": CONTENT_SCHEMA_VERSION,
                "status": "OK",
                "opportunity_id": opportunity_id,
                "count": len(records),
                "content_generations": [
                    record.to_contract(stale=service.is_stale(record)) for record in records
                ],
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/content-generations/{content_generation_id}")
    def get_content_generation(content_generation_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        record = service.get(content_generation_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": CONTENT_SCHEMA_VERSION,
                "status": "OK",
                "content_generation": record.to_contract(stale=service.is_stale(record)),
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_content_generation_router",
    "build_content_generation_service",
]
