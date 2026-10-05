"""Composition root: wires infrastructure implementations into the application."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from radar.application.health_service import HealthService
from radar.infrastructure.probes import DatabaseHealthProbe, SchemaHealthProbe
from radar.infrastructure.settings import Settings


def build_health_service(settings: Settings, engine: Engine) -> HealthService:
    """Build the system health service used by the CLI and the API."""

    return HealthService(
        probes=[
            DatabaseHealthProbe(engine),
            SchemaHealthProbe(engine, settings.database_url),
        ],
        app_version=settings.app_version,
    )
