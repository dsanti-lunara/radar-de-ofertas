"""Effective Settings read model and AUTO eligibility (RDR-067, AUT-255..258).

The service composes the already versioned operational policies with the
persisted operational state, the registered integration health and the open
HumanActions into one read model for the Settings screen. It performs no write:
the frequent controls keep their own audited boundaries (mode, kill switch,
integration health), and AUTO promotion stays a human decision (AUT-257).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from radar.domain.human_action import HumanAction, HumanActionStatus
from radar.domain.operations import (
    DEFAULT_OPERATIONAL_STATE,
    AutomationPolicy,
    ChannelCompliancePolicy,
    IntegrationHealth,
    OperationalState,
)
from radar.domain.publication import PublicationPolicy
from radar.domain.settings import (
    SETTINGS_SCHEMA_VERSION,
    AutoEligibility,
    evaluate_auto_eligibility,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SettingsOperationsStore(Protocol):
    """Read port for the operational state and integration health."""

    def get_state(self) -> OperationalState | None: ...

    def list_integrations(self) -> list[IntegrationHealth]: ...


class SettingsHumanActionStore(Protocol):
    """Read port for the open HumanActions."""

    def list(self, *, status: str | None = None) -> list[HumanAction]: ...


@dataclass(frozen=True, slots=True)
class EffectiveSettings:
    """Versioned, read-only view of the effective operational configuration."""

    observed_at: datetime
    operations: OperationalState
    automation_policy: AutomationPolicy
    compliance_policy: ChannelCompliancePolicy
    publication_policy: PublicationPolicy
    integrations: tuple[IntegrationHealth, ...]
    auto_eligibility: AutoEligibility

    def to_contract(self, *, correlation_id: str) -> dict[str, Any]:
        return {
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "status": "OK",
            "correlation_id": correlation_id,
            "observed_at": self.observed_at.astimezone(UTC).isoformat(),
            "operations": self.operations.to_contract(),
            "automation_policy": self.automation_policy.to_contract(),
            "compliance_policy": self.compliance_policy.to_contract(),
            "publication_policy": self.publication_policy.to_contract(),
            "integrations": [item.to_contract() for item in self.integrations],
            "auto_eligibility": self.auto_eligibility.to_contract(),
        }


@dataclass(slots=True)
class SettingsService:
    """Compose the effective settings read model for the Control Center."""

    operations_store: SettingsOperationsStore
    human_action_store: SettingsHumanActionStore
    automation_policy: AutomationPolicy
    compliance_policy: ChannelCompliancePolicy
    publication_policy: PublicationPolicy
    clock: Callable[[], datetime] = _utcnow

    def read(self) -> EffectiveSettings:
        """Return the effective settings snapshot and AUTO eligibility."""

        now = self.clock()
        state = self.operations_store.get_state() or DEFAULT_OPERATIONAL_STATE
        integrations = tuple(self.operations_store.list_integrations())
        open_actions = tuple(self.human_action_store.list(status=HumanActionStatus.OPEN.value))
        eligibility = evaluate_auto_eligibility(
            compliance_policy=self.compliance_policy,
            integrations=integrations,
            open_human_actions=open_actions,
            now=now,
        )
        return EffectiveSettings(
            observed_at=now,
            operations=state,
            automation_policy=self.automation_policy,
            compliance_policy=self.compliance_policy,
            publication_policy=self.publication_policy,
            integrations=integrations,
            auto_eligibility=eligibility,
        )


__all__ = [
    "EffectiveSettings",
    "SettingsHumanActionStore",
    "SettingsOperationsStore",
    "SettingsService",
]
