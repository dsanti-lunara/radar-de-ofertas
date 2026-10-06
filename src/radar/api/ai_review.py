"""Editorial AI review public endpoints (RDR-045..RDR-047, RDR-050).

``POST /candidates/{candidate_id}/ai-review`` runs the configured
:class:`~radar.domain.ai_review.AIProvider` (Fake in development) against the
sanitized candidate facts, the immutable latest Evaluation and the
backend-sustained allowed claims, and persists the versioned ``AIReview`` with its
``knowledge``/``prompt`` versions and a Correlation ID. ``GET`` endpoints expose
the append-only reviews; a missing one returns ``RAD-AI-009``.

The boundary fails closed: a provider failure/refusal or an invalid response
returns a structured error and writes nothing, so no Opportunity is ever created
by blind AI approval. No score, link, compliance or publication is produced here
(AUT-031, AUT-059, AUT-068).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import CORRELATION_HEADER, AIReviewRequestContract
from radar.application.ai_review_service import AIReviewService
from radar.application.allowed_claims_service import AllowedClaimsService
from radar.application.correlation import bind_correlation_id
from radar.domain.ai_review import AI_REVIEW_SCHEMA_VERSION, AIProvider
from radar.domain.knowledge import KnowledgePack
from radar.infrastructure.ai_review_repository import SqlAlchemyAIReviewRepository
from radar.infrastructure.capture_repository import SqlAlchemyCaptureRepository
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository


def build_ai_review_router(
    engine: Engine,
    knowledge_pack: KnowledgePack,
    provider: AIProvider,
) -> APIRouter:
    """Build the AI review router wired to SQLite, the Knowledge Pack and provider."""

    router = APIRouter(tags=["ai-review"])
    capture = SqlAlchemyCaptureRepository(engine=engine)
    evaluations = SqlAlchemyEvaluationRepository(engine=engine)
    service = AIReviewService(
        repository=SqlAlchemyAIReviewRepository(engine=engine),
        capture=capture,
        evaluations=evaluations,
        claims=AllowedClaimsService(repository=capture, evaluations=evaluations),
        knowledge=knowledge_pack,
        provider=provider,
    )

    @router.post("/candidates/{candidate_id}/ai-review")
    def run_editorial_review(
        candidate_id: str,
        payload: AIReviewRequestContract,
        request: Request,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        review = service.review(
            candidate_id,
            channel=payload.channel,
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=201,
            content=review.to_contract(),
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/candidates/{candidate_id}/ai-reviews")
    def list_candidate_ai_reviews(candidate_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        reviews = service.list(candidate_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": AI_REVIEW_SCHEMA_VERSION,
                "status": "OK",
                "candidate_id": candidate_id,
                "count": len(reviews),
                "ai_reviews": [review.to_contract() for review in reviews],
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/ai-reviews/{ai_review_id}")
    def get_ai_review(ai_review_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        review = service.get(ai_review_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": AI_REVIEW_SCHEMA_VERSION,
                "status": "OK",
                "ai_review": review.to_contract(),
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_ai_review_router",
]
