"""Home health overview read model (RDR-057, SPEC-07).

Framework-free aggregation of the Home health strip consumed by the Control
Center (``docs/11_OPERATIONS_AND_UI.md``). The model is honest by construction:
a dependency without a registered integration is reported as ``UNKNOWN`` and a
dependency without a matching health probe is reported as ``UNKNOWN`` as well,
so the strip never invents a capability that the node does not actually have
(AUT-243, AUT-315).

The module is deliberately side-effect free and framework-free (no
FastAPI/SQLAlchemy/Chrome) so the domain stays independent from infrastructure
(AUT-397).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from radar.domain.errors import RadarError
from radar.domain.health import (
    HealthCheck,
    HealthState,
    SystemHealth,
    aggregate_health_states,
)
from radar.domain.operations import IntegrationHealth, IntegrationState

#: Version of the public Home health overview contract (``docs/04_DATA_CONTRACTS.md``).
HOME_HEALTH_SCHEMA_VERSION = "1.0"

#: Version of the aggregation engine that produced the overview.
HOME_HEALTH_ENGINE_VERSION = "home-health-1.0"

#: Ordered canonical capabilities of the Home health strip (``docs/11_OPERATIONS_AND_UI.md``).
HOME_HEALTH_CAPABILITIES: tuple[str, ...] = (
    "core",
    "database",
    "scheduler",
    "ai",
    "browser",
    "mercado_livre",
    "shopee",
    "whatsapp",
    "telegram",
    "backup",
)

#: The capability representing the process that serves the overview itself.
CORE_CAPABILITY = "core"

#: The capability sourced from the system health report instead of an integration.
DATABASE_CAPABILITY = "database"

#: Health probe that backs the Database strip item.
DATABASE_HEALTH_PROBE = "database"

#: Canonical capability -> registered integration name (lowercase slug).
CAPABILITY_INTEGRATIONS: Mapping[str, str] = {
    "scheduler": "scheduler",
    "ai": "ai",
    "browser": "browser",
    "mercado_livre": "mercado_livre",
    "shopee": "shopee",
    "whatsapp": "whatsapp",
    "telegram": "telegram",
    "backup": "backup",
}

#: Integration state -> capability health state. A capability that cannot run is
#: never advertised as healthy: only ``ONLINE`` maps to ``HEALTHY``.
CAPABILITY_STATE_BY_INTEGRATION_STATE: Mapping[IntegrationState, HealthState] = {
    IntegrationState.ONLINE: HealthState.HEALTHY,
    IntegrationState.DEGRADED: HealthState.DEGRADED,
    IntegrationState.OFFLINE: HealthState.UNHEALTHY,
    IntegrationState.AUTH_REQUIRED: HealthState.UNHEALTHY,
    IntegrationState.PAUSED: HealthState.UNHEALTHY,
    IntegrationState.DISABLED: HealthState.UNHEALTHY,
    IntegrationState.UNKNOWN: HealthState.UNKNOWN,
}

#: Provenance of one capability state.
SOURCE_API = "api"
SOURCE_HEALTH = "health"
SOURCE_INTEGRATION = "integration"
SOURCE_UNREGISTERED = "unregistered"

#: Stable, safe reason codes attached to strip items.
REASON_API_RESPONDING = "API_RESPONDING"
REASON_PROBE_NOT_REPORTED = "HEALTH_PROBE_NOT_REPORTED"
REASON_INTEGRATION_NOT_REGISTERED = "INTEGRATION_NOT_REGISTERED"
REASON_INTEGRATION_HEALTH_UNAVAILABLE = "INTEGRATION_HEALTH_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class CapabilityHealth:
    """One item of the Home health strip."""

    capability: str
    state: HealthState
    summary: str
    source: str
    reason_code: str | None = None
    integration: str | None = None
    integration_state: IntegrationState | None = None
    error: RadarError | None = None

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "capability": self.capability,
            "state": self.state.value,
            "summary": self.summary,
            "source": self.source,
        }
        if self.reason_code is not None:
            payload["reason_code"] = self.reason_code
        if self.integration is not None:
            payload["integration"] = self.integration
        if self.integration_state is not None:
            payload["integration_state"] = self.integration_state.value
        if self.error is not None:
            payload["error"] = self.error.to_contract()
        return payload


@dataclass(frozen=True, slots=True)
class HomeHealth:
    """Public overview returned by ``GET /health/overview`` and the Control Center."""

    schema_version: str
    status: HealthState
    engine_version: str
    app_version: str
    correlation_id: str
    observed_at: datetime
    items: tuple[CapabilityHealth, ...]

    @property
    def is_operational(self) -> bool:
        """True when the aggregate state can keep serving (healthy or degraded)."""

        return self.status in (HealthState.HEALTHY, HealthState.DEGRADED)

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "engine_version": self.engine_version,
            "app_version": self.app_version,
            "correlation_id": self.correlation_id,
            "observed_at": self.observed_at.isoformat(),
            "items": [item.to_contract() for item in self.items],
        }


def build_home_health(
    *,
    report: SystemHealth,
    integrations: Mapping[str, IntegrationHealth],
    integrations_unavailable: bool = False,
    engine_version: str = HOME_HEALTH_ENGINE_VERSION,
) -> HomeHealth:
    """Aggregate the system health report and registered integrations.

    ``integrations`` is keyed by integration name. A capability whose canonical
    integration was never registered is ``UNKNOWN`` (reason
    ``INTEGRATION_NOT_REGISTERED``), never healthy. When the integration store
    itself cannot be read, every integration capability is ``UNKNOWN`` with
    reason ``INTEGRATION_HEALTH_UNAVAILABLE`` instead of being reported as
    missing, so the strip does not invent a registration state.
    """

    items = tuple(
        _build_item(
            capability,
            report=report,
            integrations=integrations,
            integrations_unavailable=integrations_unavailable,
        )
        for capability in HOME_HEALTH_CAPABILITIES
    )
    return HomeHealth(
        schema_version=HOME_HEALTH_SCHEMA_VERSION,
        status=aggregate_health_states(item.state for item in items),
        engine_version=engine_version,
        app_version=report.app_version,
        correlation_id=report.correlation_id,
        observed_at=report.observed_at,
        items=items,
    )


def _build_item(
    capability: str,
    *,
    report: SystemHealth,
    integrations: Mapping[str, IntegrationHealth],
    integrations_unavailable: bool,
) -> CapabilityHealth:
    if capability == CORE_CAPABILITY:
        return CapabilityHealth(
            capability=capability,
            state=HealthState.HEALTHY,
            summary="Control Center API respondendo",
            source=SOURCE_API,
            reason_code=REASON_API_RESPONDING,
        )
    if capability == DATABASE_CAPABILITY:
        check = _find_check(report.checks, DATABASE_HEALTH_PROBE)
        if check is None:
            return CapabilityHealth(
                capability=capability,
                state=HealthState.UNKNOWN,
                summary="Probe de banco não reportado",
                source=SOURCE_HEALTH,
                reason_code=REASON_PROBE_NOT_REPORTED,
            )
        return CapabilityHealth(
            capability=capability,
            state=check.state,
            summary=check.summary,
            source=SOURCE_HEALTH,
            error=check.error,
        )

    integration_name = CAPABILITY_INTEGRATIONS[capability]
    health = integrations.get(integration_name)
    if health is None:
        if integrations_unavailable:
            return CapabilityHealth(
                capability=capability,
                state=HealthState.UNKNOWN,
                summary="Saúde de integração indisponível",
                source=SOURCE_UNREGISTERED,
                reason_code=REASON_INTEGRATION_HEALTH_UNAVAILABLE,
                integration=integration_name,
            )
        return CapabilityHealth(
            capability=capability,
            state=HealthState.UNKNOWN,
            summary="Integração não registrada",
            source=SOURCE_UNREGISTERED,
            reason_code=REASON_INTEGRATION_NOT_REGISTERED,
            integration=integration_name,
        )
    return CapabilityHealth(
        capability=capability,
        state=CAPABILITY_STATE_BY_INTEGRATION_STATE[health.state],
        summary=health.summary,
        source=SOURCE_INTEGRATION,
        integration=integration_name,
        integration_state=health.state,
    )


def _find_check(checks: Sequence[HealthCheck], name: str) -> HealthCheck | None:
    for check in checks:
        if check.name == name:
            return check
    return None


__all__ = [
    "CAPABILITY_INTEGRATIONS",
    "CAPABILITY_STATE_BY_INTEGRATION_STATE",
    "CORE_CAPABILITY",
    "DATABASE_CAPABILITY",
    "DATABASE_HEALTH_PROBE",
    "HOME_HEALTH_CAPABILITIES",
    "HOME_HEALTH_ENGINE_VERSION",
    "HOME_HEALTH_SCHEMA_VERSION",
    "REASON_API_RESPONDING",
    "REASON_INTEGRATION_HEALTH_UNAVAILABLE",
    "REASON_INTEGRATION_NOT_REGISTERED",
    "REASON_PROBE_NOT_REPORTED",
    "SOURCE_API",
    "SOURCE_HEALTH",
    "SOURCE_INTEGRATION",
    "SOURCE_UNREGISTERED",
    "CapabilityHealth",
    "HomeHealth",
    "build_home_health",
]
