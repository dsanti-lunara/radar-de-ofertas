"""Control Center API (RDR-010 / SPEC-01).

Only the health/version/config boundary exists at this stage; the UI and the
rest of the API arrive in their own tickets. Health reports fail closed: an
unhealthy dependency yields HTTP 503 while the body keeps the structured
contract. Invalid configuration blocks app creation before serving.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar import __version__
from radar.application.correlation import new_correlation_id
from radar.bootstrap import build_health_service
from radar.domain.config import RadarConfig
from radar.infrastructure.config import ConfigLoader
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.settings import Settings

CORRELATION_HEADER = "X-Correlation-ID"


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    config: RadarConfig | None = None,
) -> FastAPI:
    # Invalid configuration raises ConfigInvalidError, so the API never serves
    # with a config that failed schema validation (RDR-004).
    resolved_config = config or ConfigLoader.from_env().load()
    resolved_settings = settings or Settings(
        database_url=resolved_config.database_url,
        log_level=resolved_config.log_level,
    )
    resolved_engine = engine or create_database_engine(resolved_settings.database_url)
    health_service = build_health_service(resolved_settings, resolved_engine)

    app = FastAPI(title="Radar Engine API", version=__version__)
    app.state.settings = resolved_settings
    app.state.engine = resolved_engine
    app.state.config = resolved_config

    @app.get("/version")
    def version() -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "app_version": resolved_settings.app_version,
            "api_version": __version__,
        }

    @app.get("/config")
    def config_endpoint(request: Request) -> JSONResponse:
        correlation_id = request.headers.get(CORRELATION_HEADER) or new_correlation_id()
        payload = {
            "status": "VALID",
            "correlation_id": correlation_id,
            **resolved_config.to_contract(),
        }
        return JSONResponse(
            content=payload,
            headers={CORRELATION_HEADER: correlation_id, "Cache-Control": "no-store"},
        )

    @app.get("/health")
    def health(request: Request) -> JSONResponse:
        report = health_service.evaluate(request.headers.get(CORRELATION_HEADER))
        status_code = 200 if report.is_operational else 503
        return JSONResponse(
            content=report.to_contract(),
            status_code=status_code,
            headers={
                CORRELATION_HEADER: report.correlation_id,
                "Cache-Control": "no-store",
            },
        )

    return app
