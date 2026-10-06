"""Home health overview orchestration (RDR-057).

The service runs the system health probes and reads the registered integration
health, then aggregates both into the framework-free
:class:`~radar.domain.home_health.HomeHealth` read model consumed by the Control
Center Home. It is a thin application seam: all state resolution lives in the
domain, so the behavior is observable from the public boundary and testable
without FastAPI (AUT-397).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from radar.application.health_service import HealthService
from radar.domain.home_health import HomeHealth, build_home_health
from radar.domain.operations import IntegrationHealth


class IntegrationHealthReader(Protocol):
    """Port that exposes the registered integration health."""

    def list_integrations(self) -> list[IntegrationHealth]: ...


@dataclass(slots=True)
class HomeHealthService:
    """Aggregate the system health report and registered integrations."""

    health_service: HealthService
    integrations: IntegrationHealthReader

    def evaluate(self, correlation_id: str | None = None) -> HomeHealth:
        """Return the Home health overview for the current node state.

        A failure to read the integration store fails closed: the integration
        capabilities become ``UNKNOWN`` instead of crashing the read model or
        advertising an unproven capability as healthy.
        """

        report = self.health_service.evaluate(correlation_id)
        integrations_unavailable = False
        try:
            registered = {health.name: health for health in self.integrations.list_integrations()}
        except Exception:  # a health read must never crash; fail closed as UNKNOWN
            registered = {}
            integrations_unavailable = True
        return build_home_health(
            report=report,
            integrations=registered,
            integrations_unavailable=integrations_unavailable,
        )


__all__ = [
    "HomeHealthService",
    "IntegrationHealthReader",
]
