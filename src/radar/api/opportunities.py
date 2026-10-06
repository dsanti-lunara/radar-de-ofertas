"""Opportunity public endpoints driven by the Workflow Engine (RDR-017, RDR-041).

``POST /candidates/{candidate_id}/opportunities`` advances an evaluated Candidate
through the engine: only an ``APPROVE`` Evaluation creates an Opportunity (and the
engine enqueues the next Job in the same transaction); a ``REJECT`` returns
``REJECTED`` without an Opportunity; a ``REVIEW`` creates an explicit
``REVIEW_CANDIDATE`` HumanAction. ``GET`` endpoints expose the persisted
Opportunity and its append-only transition audit. ``POST
/opportunities/{id}/transitions`` applies an explicit transition and rejects an
invalid one with ``RAD-WF-015`` after auditing it. No AI, link or publication is
triggered here (AUT-031, AUT-007).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import (
    CORRELATION_HEADER,
    OpportunityAdvanceContract,
    OpportunityTransitionContract,
)
from radar.application.correlation import bind_correlation_id
from radar.application.workflow_service import WorkflowService
from radar.domain.workflow import WORKFLOW_SCHEMA_VERSION, WorkflowPolicy
from radar.infrastructure.evaluation_repository import SqlAlchemyEvaluationRepository
from radar.infrastructure.opportunity_repository import SqlAlchemyWorkflowRepository


def build_opportunity_router(engine: Engine, policy: WorkflowPolicy) -> APIRouter:
    """Build the Opportunity router wired to the SQLite store and workflow policy."""

    router = APIRouter(tags=["opportunities"])
    service = WorkflowService(
        store=SqlAlchemyWorkflowRepository(engine=engine),
        evaluation_store=SqlAlchemyEvaluationRepository(engine=engine),
        policy=policy,
    )

    @router.post("/candidates/{candidate_id}/opportunities")
    def advance_candidate(
        candidate_id: str,
        payload: OpportunityAdvanceContract,
        request: Request,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        result = service.advance(
            candidate_id,
            correlation_id=correlation_id,
            priority=payload.priority,
        )
        status_code = 201 if result.status == "OPPORTUNITY_CREATED" else 200
        return JSONResponse(
            status_code=status_code,
            content=result.to_contract(),
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/candidates/{candidate_id}/opportunities")
    def list_candidate_opportunities(candidate_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        opportunities = service.list(candidate_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": WORKFLOW_SCHEMA_VERSION,
                "status": "OK",
                "candidate_id": candidate_id,
                "count": len(opportunities),
                "opportunities": [item.to_contract() for item in opportunities],
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/opportunities/{opportunity_id}")
    def get_opportunity(opportunity_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        opportunity, events = service.get(opportunity_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": WORKFLOW_SCHEMA_VERSION,
                "status": "OK",
                "opportunity": opportunity.to_contract(),
                "history": [event.to_contract() for event in events],
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.post("/opportunities/{opportunity_id}/transitions")
    def transition_opportunity(
        opportunity_id: str,
        payload: OpportunityTransitionContract,
        request: Request,
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        opportunity = service.transition(
            opportunity_id,
            target_state=payload.target_state,
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": WORKFLOW_SCHEMA_VERSION,
                "status": "TRANSITIONED",
                "opportunity": opportunity.to_contract(),
                "correlation_id": correlation_id,
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_opportunity_router",
]
