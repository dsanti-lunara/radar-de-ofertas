"""Health orchestration (RDR-010).

The service runs a sequence of probes and turns their result into a
:class:`~radar.domain.health.SystemHealth` report. Probe failures fail closed:
the affected check becomes ``UNHEALTHY`` instead of crashing the endpoint.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from radar.application.correlation import new_correlation_id
from radar.domain.errors import RadarError
from radar.domain.health import (
    HEALTH_PROBE_FAILED,
    HEALTH_SCHEMA_VERSION,
    HealthCheck,
    HealthProbe,
    HealthState,
    SystemHealth,
    aggregate_health,
)

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class HealthService:
    def __init__(
        self,
        probes: Sequence[HealthProbe],
        *,
        app_version: str,
        clock: Clock = _utc_now,
        correlation_id_factory: Callable[[], str] = new_correlation_id,
        schema_version: str = HEALTH_SCHEMA_VERSION,
    ) -> None:
        self._probes = tuple(probes)
        self._app_version = app_version
        self._clock = clock
        self._correlation_id_factory = correlation_id_factory
        self._schema_version = schema_version

    def evaluate(self, correlation_id: str | None = None) -> SystemHealth:
        observed_at = self._clock()
        resolved_id = correlation_id or self._correlation_id_factory()
        checks = tuple(self._run(probe) for probe in self._probes)
        return SystemHealth(
            schema_version=self._schema_version,
            status=aggregate_health(checks),
            checks=checks,
            correlation_id=resolved_id,
            observed_at=observed_at,
            app_version=self._app_version,
        )

    @staticmethod
    def _run(probe: HealthProbe) -> HealthCheck:
        try:
            return probe.check()
        except Exception as exc:  # probes fail closed, never crash the endpoint
            return HealthCheck(
                name=probe.name,
                state=HealthState.UNHEALTHY,
                summary="Probe de saúde falhou inesperadamente",
                error=RadarError(
                    code=HEALTH_PROBE_FAILED,
                    message=f"{type(exc).__name__}: {exc}",
                    retryable=False,
                    action="Inspecionar logs do Radar e repetir o diagnóstico",
                    context={"probe": probe.name},
                ),
            )
