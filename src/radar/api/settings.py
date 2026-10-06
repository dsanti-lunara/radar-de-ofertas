"""Effective Settings read boundary (RDR-067, AUT-255..258).

``GET /settings`` composes the versioned operational policies with the persisted
operational state, the registered integration health and the open HumanActions.
It is a read-only diagnostic surface: it changes nothing, never promotes a
capability to AUTO and reports unproven eligibility criteria honestly.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar.api.captures import resolve_correlation_id
from radar.api.contracts import CORRELATION_HEADER
from radar.application.correlation import bind_correlation_id
from radar.application.settings_service import SettingsService
from radar.domain.operations import AutomationPolicy, ChannelCompliancePolicy
from radar.domain.publication import PublicationPolicy
from radar.infrastructure.human_action_repository import SqlAlchemyHumanActionRepository
from radar.infrastructure.operations_repository import SqlAlchemyOperationsRepository


def build_settings_router(
    engine: Engine,
    automation_policy: AutomationPolicy,
    compliance_policy: ChannelCompliancePolicy,
    publication_policy: PublicationPolicy,
) -> APIRouter:
    """Build the read-only Settings router wired to the SQLite stores."""

    router = APIRouter(tags=["settings"])
    service = SettingsService(
        operations_store=SqlAlchemyOperationsRepository(engine=engine),
        human_action_store=SqlAlchemyHumanActionRepository(engine=engine),
        automation_policy=automation_policy,
        compliance_policy=compliance_policy,
        publication_policy=publication_policy,
    )

    @router.get("/settings")
    def get_settings(request: Request) -> JSONResponse:
        correlation_id = bind_correlation_id(resolve_correlation_id(request))
        settings = service.read()
        return JSONResponse(
            status_code=200,
            content=settings.to_contract(correlation_id=correlation_id),
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    return router


__all__ = [
    "build_settings_router",
]
