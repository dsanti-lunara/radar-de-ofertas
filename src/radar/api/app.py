"""Control Center API (RDR-010 / SPEC-01).

The health/version/config boundary plus the manual capture boundary exist at
this stage; the UI and the rest of the API arrive in their own tickets. Health
reports fail closed: an unhealthy dependency yields HTTP 503 while the body
keeps the structured contract. Invalid configuration blocks app creation
before serving. Capture validation failures return the structured error
contract with the Correlation ID.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from radar import __version__
from radar.api.captures import build_capture_router, register_capture_error_handlers
from radar.api.classification import build_classification_router
from radar.api.contracts import CORRELATION_HEADER
from radar.api.price_opportunity import build_price_opportunity_router
from radar.api.seller_quality import build_seller_quality_router
from radar.application.correlation import new_correlation_id
from radar.bootstrap import build_health_service
from radar.domain.config import RadarConfig
from radar.domain.seller_quality import SellerQualityNormalization
from radar.domain.taxonomy import BrandTaxonomy
from radar.infrastructure.config import ConfigLoader
from radar.infrastructure.database import create_database_engine
from radar.infrastructure.seller_quality import SellerQualityLoader
from radar.infrastructure.settings import Settings
from radar.infrastructure.taxonomy import TaxonomyLoader


def create_app(
    settings: Settings | None = None,
    engine: Engine | None = None,
    config: RadarConfig | None = None,
    taxonomy: BrandTaxonomy | None = None,
    seller_quality: SellerQualityNormalization | None = None,
) -> FastAPI:
    # Invalid configuration raises ConfigInvalidError, so the API never serves
    # with a config that failed schema validation (RDR-004). The taxonomy is
    # loaded the same way: an invalid taxonomy file blocks app creation instead
    # of serving an uncalibrated Brand Fit. Seller Quality normalization follows
    # the same fail-closed contract (RDR-024).
    resolved_config = config or ConfigLoader.from_env().load()
    resolved_settings = settings or Settings(
        database_url=resolved_config.database_url,
        log_level=resolved_config.log_level,
    )
    resolved_engine = engine or create_database_engine(resolved_settings.database_url)
    resolved_taxonomy = taxonomy or TaxonomyLoader.from_env().load()
    resolved_seller_quality = seller_quality or SellerQualityLoader.from_env().load()
    health_service = build_health_service(resolved_settings, resolved_engine)

    app = FastAPI(title="Radar Engine API", version=__version__)
    app.state.settings = resolved_settings
    app.state.engine = resolved_engine
    app.state.config = resolved_config
    app.state.taxonomy = resolved_taxonomy
    app.state.seller_quality = resolved_seller_quality

    register_capture_error_handlers(app)
    app.include_router(build_capture_router(resolved_engine))
    app.include_router(build_classification_router(resolved_engine, resolved_taxonomy))
    app.include_router(build_price_opportunity_router(resolved_engine))
    app.include_router(build_seller_quality_router(resolved_engine, resolved_seller_quality))

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
