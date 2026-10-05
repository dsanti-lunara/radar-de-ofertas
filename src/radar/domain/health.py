"""System health model (RDR-010).

The model is intentionally framework-free. Infrastructure provides
:class:`HealthProbe` implementations and the application layer aggregates them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from radar.domain.errors import RadarError

HEALTH_SCHEMA_VERSION = "1.0"

#: Error used when a probe itself fails in an unexpected way.
HEALTH_PROBE_FAILED = "RAD-SYS-001"


class HealthState(StrEnum):
    """Standardized health states (AUT-243)."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class HealthCheck:
    name: str
    state: HealthState
    summary: str
    error: RadarError | None = None

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "state": self.state.value,
            "summary": self.summary,
        }
        if self.error is not None:
            payload["error"] = self.error.to_contract()
        return payload


@dataclass(frozen=True, slots=True)
class SystemHealth:
    """Public health report returned by the CLI and the API."""

    schema_version: str
    status: HealthState
    checks: tuple[HealthCheck, ...]
    correlation_id: str
    observed_at: datetime
    app_version: str

    @property
    def is_operational(self) -> bool:
        """True when the service can keep serving (healthy or degraded)."""

        return self.status in (HealthState.HEALTHY, HealthState.DEGRADED)

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "app_version": self.app_version,
            "correlation_id": self.correlation_id,
            "observed_at": self.observed_at.isoformat(),
            "checks": [check.to_contract() for check in self.checks],
        }


def aggregate_health(checks: Sequence[HealthCheck]) -> HealthState:
    """Combine individual checks into one system state.

    Fail closed: any ``UNHEALTHY`` check makes the system unhealthy, an
    ``UNKNOWN`` check is reported as ``DEGRADED`` so an unproven dependency is
    never advertised as healthy.
    """

    if not checks:
        return HealthState.UNKNOWN
    states = {check.state for check in checks}
    if HealthState.UNHEALTHY in states:
        return HealthState.UNHEALTHY
    if HealthState.UNKNOWN in states or HealthState.DEGRADED in states:
        return HealthState.DEGRADED
    return HealthState.HEALTHY


@runtime_checkable
class HealthProbe(Protocol):
    """A named, self-contained health check performed by infrastructure."""

    @property
    def name(self) -> str: ...

    def check(self) -> HealthCheck: ...
