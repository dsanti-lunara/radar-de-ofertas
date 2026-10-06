"""Operational controls public boundary (RDR-043, RDR-044).

The endpoints expose the global mode, the ``STOP_EXTERNAL_ACTIONS`` kill switch,
the authorization decision for one external action and the integration health.
Every response carries the versioned contract and the Correlation ID; external
action decisions are audited. Safe reading/diagnostic/recovery never depend on
the kill switch (AUT-317).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import (
    CORRELATION_HEADER,
    ExternalActionAuthorizationContract,
    IntegrationHealthContract,
    OperationsModeContract,
    StopExternalActionsContract,
)
from radar.application.correlation import bind_correlation_id
from radar.application.operations_service import OperationsService
from radar.domain.operations import (
    OPERATIONS_SCHEMA_VERSION,
    AutomationPolicy,
    ChannelCompliancePolicy,
    ExternalActionRequest,
)
from radar.infrastructure.operations_repository import SqlAlchemyOperationsRepository


def build_operations_router(
    engine: Engine,
    automation_policy: AutomationPolicy,
    compliance_policy: ChannelCompliancePolicy,
) -> APIRouter:
    """Build the operational controls router wired to the SQLite store."""

    router = APIRouter(tags=["operations"])
    service = OperationsService(
        store=SqlAlchemyOperationsRepository(engine=engine),
        automation_policy=automation_policy,
        compliance_policy=compliance_policy,
    )

    def _headers(correlation_id: str) -> dict[str, str]:
        return {CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"}

    @router.get("/operations")
    def get_operations(request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": OPERATIONS_SCHEMA_VERSION,
                "status": "OK",
                "state": service.state().to_contract(),
                "automation_policy": automation_policy.to_contract(),
                "compliance_policy": compliance_policy.to_contract(),
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    @router.post("/operations/mode")
    def set_mode(payload: OperationsModeContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        state = service.set_global_mode(
            payload.mode, reason=payload.reason, correlation_id=correlation_id
        )
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": OPERATIONS_SCHEMA_VERSION,
                "status": "OK",
                "state": state.to_contract(),
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    @router.post("/operations/stop-external-actions")
    def engage_stop(payload: StopExternalActionsContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        state = service.engage_stop(reason=payload.reason, correlation_id=correlation_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": OPERATIONS_SCHEMA_VERSION,
                "status": "STOPPED",
                "state": state.to_contract(),
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    @router.delete("/operations/stop-external-actions")
    def release_stop(payload: StopExternalActionsContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        state = service.release_stop(reason=payload.reason, correlation_id=correlation_id)
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": OPERATIONS_SCHEMA_VERSION,
                "status": "RESUMED",
                "state": state.to_contract(),
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    @router.post("/operations/authorize")
    def authorize(payload: ExternalActionAuthorizationContract, request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        decision = service.authorize(
            ExternalActionRequest(
                action=payload.action,
                brand=payload.brand,
                marketplace=payload.marketplace,
                channel=payload.channel,
                capability=payload.capability,
                integration=payload.integration,
                publication_approved=payload.publication_approved,
            ),
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=200,
            content=decision.to_contract(),
            headers=_headers(correlation_id),
        )

    @router.get("/integrations")
    def list_integrations(request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        integrations = service.list_integrations()
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": OPERATIONS_SCHEMA_VERSION,
                "status": "OK",
                "count": len(integrations),
                "integrations": [item.to_contract() for item in integrations],
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    @router.put("/integrations/{name}")
    def set_integration(
        name: str, payload: IntegrationHealthContract, request: Request
    ) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        health = service.set_integration_health(
            name,
            payload.state,
            summary=payload.summary,
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=200,
            content={
                "schema_version": OPERATIONS_SCHEMA_VERSION,
                "status": "OK",
                "integration": health.to_contract(),
                "correlation_id": correlation_id,
            },
            headers=_headers(correlation_id),
        )

    return router


__all__ = [
    "build_operations_router",
]
