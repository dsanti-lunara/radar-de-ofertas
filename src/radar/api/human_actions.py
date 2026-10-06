"""Public read boundary for HumanActions (RDR-040).

The retry/Dead Job flow creates HumanActions; ``GET /human-actions`` and
``GET /human-actions/{id}`` expose the pending intervention, its impact and the
next steps through the versioned public contract. Resolution belongs to the
Human Actions center (RDR-063).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import CORRELATION_HEADER
from radar.application.correlation import bind_correlation_id
from radar.application.human_action_service import HumanActionService
from radar.domain.human_action import HUMAN_ACTION_SCHEMA_VERSION, HumanActionStatus
from radar.infrastructure.human_action_repository import SqlAlchemyHumanActionRepository


def build_human_action_router(engine: Engine) -> APIRouter:
    """Build the HumanAction read router wired to the SQLite repository."""

    router = APIRouter(tags=["human-actions"])
    service = HumanActionService(repository=SqlAlchemyHumanActionRepository(engine=engine))

    @router.get("/human-actions")
    def list_human_actions(
        request: Request, status: HumanActionStatus | None = None
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        actions = service.list(status=None if status is None else status.value)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": HUMAN_ACTION_SCHEMA_VERSION,
                "correlation_id": correlation_id,
                "human_actions": [action.to_contract() for action in actions],
            },
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @router.get("/human-actions/{human_action_id}")
    def get_human_action(human_action_id: str, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        action = service.get(human_action_id)
        return JSONResponse(
            status_code=200,
            content=action.to_contract(),
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_human_action_router",
]
