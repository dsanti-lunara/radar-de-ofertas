"""AffiliateLink public endpoints (RDR-018, RDR-070).

``POST /candidates/{candidate_id}/affiliate-link`` generates the validated
AffiliateLink for an approved Candidate whose Opportunity is linkable, resolving
the internal TrackingContext from the versioned label mapping and asking the
configured :class:`~radar.domain.affiliate_link.AffiliateLinkProvider` (Fake in
development) for a literal link. ``GET`` endpoints expose the persisted links; a
missing one returns ``RAD-LINK-002``.

The boundary fails closed: a non-approved Candidate, an unmapped tracking label,
a provider failure or a returned link that does not match the expected
host/product returns a structured error and writes nothing. A Fake link is
reported as ``productive=false`` (AUT-422) and no AI edits a URL
(AUT-078, AUT-164).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import CORRELATION_HEADER, AffiliateLinkRequestContract
from radar.application.affiliate_link_service import AffiliateLinkService
from radar.application.correlation import bind_correlation_id
from radar.domain.affiliate_link import AFFILIATE_LINK_SCHEMA_VERSION, AffiliateLinkProvider
from radar.domain.tracking import TrackingLabelMapping
from radar.infrastructure.affiliate_link_repository import SqlAlchemyAffiliateLinkRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from radar.infrastructure.opportunity_repository import SqlAlchemyWorkflowRepository


def build_affiliate_link_router(
    engine: Engine,
    tracking_labels: TrackingLabelMapping,
    provider: AffiliateLinkProvider,
) -> APIRouter:
    """Build the affiliate link router wired to SQLite, the mapping and provider."""

    router = APIRouter(tags=["affiliate-links"])
    service = AffiliateLinkService(
        repository=SqlAlchemyAffiliateLinkRepository(engine=engine),
        capture=SqlAlchemyAffiliateLinkRepository(engine=engine),
        evaluations=SqlAlchemyEvaluationRepository(engine=engine),
        opportunities=SqlAlchemyWorkflowRepository(engine=engine),
        tracking_labels=tracking_labels,
        provider=provider,
    )

    @router.post("/candidates/{candidate_id}/affiliate-link")
    def generate_affiliate_link(
        candidate_id: str,
        payload: AffiliateLinkRequestContract,
        request: Request,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        link = service.generate(
            candidate_id,
            correlation_id=correlation_id,
            tracking_reference=payload.tracking_reference,
        )
        return JSONResponse(
            status_code=201,
            content=link.to_contract(),
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/candidates/{candidate_id}/affiliate-links")
    def list_candidate_affiliate_links(candidate_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        links = service.list(candidate_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": AFFILIATE_LINK_SCHEMA_VERSION,
                "status": "OK",
                "candidate_id": candidate_id,
                "count": len(links),
                "affiliate_links": [link.to_contract() for link in links],
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/affiliate-links/{affiliate_link_id}")
    def get_affiliate_link(affiliate_link_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        link = service.get(affiliate_link_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": AFFILIATE_LINK_SCHEMA_VERSION,
                "status": "OK",
                "affiliate_link": link.to_contract(),
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_affiliate_link_router",
]
