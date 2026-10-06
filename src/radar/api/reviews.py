"""Opportunity review public boundary (RDR-058, RDR-059, RDR-060).

``GET /review/inbox`` and ``GET /review/candidates/{id}`` expose the Inbox and
detail read models built from the persisted Candidate/Evaluation/AIReview rows,
including the timeline and the artifact versions. ``POST
/candidates/{id}/human-reviews`` records an immutable ``HumanReview`` that keeps
the AI decision and the human decision separate, and **never** triggers a
commercial send: approving a Candidate is not a publication approval
(GRILL-001, AUT-035/AUT-036). Every response carries ``schema_version`` and the
Correlation ID, and a missing Candidate/Review returns a structured error
(``RAD-UI-002``/``RAD-UI-003``) through the shared handler.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import CORRELATION_HEADER, HumanReviewRequestContract
from radar.application.correlation import bind_correlation_id
from radar.application.review_service import REVIEW_SCHEMA_VERSION, ReviewService
from radar.domain.human_review import HUMAN_REVIEW_SCHEMA_VERSION
from radar.domain.operations import (
    DEFAULT_OPERATIONAL_STATE,
    AutomationPolicy,
    ChannelCompliancePolicy,
)
from radar.infrastructure.human_review_repository import SqlAlchemyHumanReviewRepository
from radar.infrastructure.operations_repository import SqlAlchemyOperationsRepository


def build_review_router(
    engine: Engine,
    automation_policy: AutomationPolicy,
    compliance_policy: ChannelCompliancePolicy,
) -> APIRouter:
    """Build the review router wired to SQLite and the operational policies."""

    router = APIRouter(tags=["reviews"])
    operations = SqlAlchemyOperationsRepository(engine=engine)

    def _operational_state():
        return operations.get_state() or DEFAULT_OPERATIONAL_STATE

    service = ReviewService(
        store=SqlAlchemyHumanReviewRepository(engine=engine),
        automation_policy=automation_policy,
        compliance_policy=compliance_policy,
        operational_state=_operational_state,
    )

    def _headers(correlation_id: str) -> dict[str, str]:
        return {CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"}

    @router.get("/review/inbox")
    def review_inbox(request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        items = service.inbox()
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": REVIEW_SCHEMA_VERSION,
                "status": "OK",
                "count": len(items),
                "items": [item.to_contract() for item in items],
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    @router.get("/review/candidates/{candidate_id}")
    def review_detail(candidate_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        detail = service.detail(candidate_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": REVIEW_SCHEMA_VERSION,
                "status": "OK",
                "candidate_id": candidate_id,
                "detail": detail.to_contract(),
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    @router.get("/candidates/{candidate_id}/human-reviews")
    def list_human_reviews(candidate_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        reviews = service.list_reviews(candidate_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
                "status": "OK",
                "candidate_id": candidate_id,
                "count": len(reviews),
                "human_reviews": [review.to_contract() for review in reviews],
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    @router.post("/candidates/{candidate_id}/human-reviews")
    def register_human_review(
        candidate_id: str,
        payload: HumanReviewRequestContract,
        request: Request,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        edited = (
            None
            if payload.edited_content is None
            else {
                "headline": payload.edited_content.headline,
                "body": payload.edited_content.body,
                "cta": payload.edited_content.cta,
            }
        )
        result = service.register(
            candidate_id,
            human_decision=payload.human_decision,
            reason=payload.reason,
            ai_review_id=payload.ai_review_id,
            note=payload.note,
            edited_content=edited,
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=201,
            content=result.to_contract(),
            headers=_headers(correlation_id),
        )

    @router.get("/human-reviews/{human_review_id}")
    def get_human_review(human_review_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        review = service.get_review(human_review_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
                "status": "OK",
                "human_review": review.to_contract(),
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    return router


__all__ = [
    "build_review_router",
]
