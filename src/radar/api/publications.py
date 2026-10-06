"""Publication public endpoints (RDR-020, RDR-072).

``POST /opportunities/{opportunity_id}/publications`` publishes a ready
``ContentGeneration`` through the configured :class:`~radar.domain.publication.Publisher`
(Fake in development). The TKT-17 authorization gate and the versioned
publication policy (cap/burst/cooldown/quiet hours) are evaluated before the
publisher, so a blocked request returns a structured ``RAD-PUB-003`` block with
the actionable ``reason_code`` and performs no side effect. A repeated
``idempotency_key`` returns the persisted Publication with
``idempotent_replay=true`` and never sends again.

``GET`` endpoints expose the append-only Publication timeline; a missing one
returns ``RAD-PUB-002``. No score, link or content is produced here and the
unknown-result window belongs to TKT-24.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.content_generations import build_content_generation_service
from radar.api.contracts import (
    CORRELATION_HEADER,
    PublicationRequestContract,
    PublicationResolveContract,
)
from radar.application.correlation import bind_correlation_id
from radar.application.operations_service import OperationsService
from radar.application.publication_service import PublicationService
from radar.domain.content import ContentProvider
from radar.domain.knowledge import KnowledgePack
from radar.domain.operations import AutomationPolicy, ChannelCompliancePolicy
from radar.domain.publication import PUBLICATION_SCHEMA_VERSION, PublicationPolicy, Publisher
from radar.infrastructure.affiliate_link_repository import SqlAlchemyAffiliateLinkRepository
from radar.infrastructure.content_repository import SqlAlchemyContentGenerationRepository
from radar.infrastructure.operations_repository import SqlAlchemyOperationsRepository
from radar.infrastructure.opportunity_repository import SqlAlchemyWorkflowRepository
from radar.infrastructure.publication_repository import SqlAlchemyPublicationRepository


def build_publication_router(
    engine: Engine,
    knowledge_pack: KnowledgePack,
    content_provider: ContentProvider,
    compliance_policy: ChannelCompliancePolicy,
    publication_policy: PublicationPolicy,
    publisher: Publisher,
    automation_policy: AutomationPolicy,
) -> APIRouter:
    """Build the publication router wired to SQLite, the gate and the publisher."""

    router = APIRouter(tags=["publications"])
    content_service = build_content_generation_service(
        engine, knowledge_pack, content_provider, compliance_policy
    )
    operations = OperationsService(
        store=SqlAlchemyOperationsRepository(engine=engine),
        automation_policy=automation_policy,
        compliance_policy=compliance_policy,
    )
    service = PublicationService(
        repository=SqlAlchemyPublicationRepository(engine=engine),
        opportunities=SqlAlchemyWorkflowRepository(engine=engine),
        content=SqlAlchemyContentGenerationRepository(engine=engine),
        revalidation=content_service,
        links=SqlAlchemyAffiliateLinkRepository(engine=engine),
        authorizer=operations,
        policy=publication_policy,
        publisher=publisher,
    )

    def _headers(correlation_id: str) -> dict[str, str]:
        return {CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"}

    @router.post("/opportunities/{opportunity_id}/publications")
    def publish(
        opportunity_id: str, payload: PublicationRequestContract, request: Request
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        resolution = service.publish(
            opportunity_id,
            content_generation_id=payload.content_generation_id,
            destination_id=payload.destination_id,
            idempotency_key=payload.idempotency_key,
            publication_approved=payload.publication_approved,
            correlation_id=correlation_id,
        )
        status_code = 200 if resolution.idempotent_replay else 201
        return JSONResponse(
            status_code=status_code,
            content=resolution.to_contract(),
            headers=_headers(correlation_id),
        )

    @router.get("/opportunities/{opportunity_id}/publications")
    def list_publications(opportunity_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        records = service.list(opportunity_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": PUBLICATION_SCHEMA_VERSION,
                "status": "OK",
                "opportunity_id": opportunity_id,
                "count": len(records),
                "publications": [record.to_contract() for record in records],
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    @router.get("/publications/{publication_id}")
    def get_publication(publication_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        record = service.get(publication_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": PUBLICATION_SCHEMA_VERSION,
                "status": "OK",
                "publication": record.to_contract(),
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    @router.post("/publications/{publication_id}/resolve")
    def resolve_publication(
        publication_id: str, payload: PublicationResolveContract, request: Request
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        resolution = service.resolve(
            publication_id,
            decision=payload.decision,
            evidence=payload.to_evidence(),
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": PUBLICATION_SCHEMA_VERSION,
                "status": "RESOLVED",
                "resolution": resolution.to_contract(),
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    return router


__all__ = [
    "build_publication_router",
]
