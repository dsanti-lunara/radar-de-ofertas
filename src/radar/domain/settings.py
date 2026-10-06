"""Effective operational settings and AUTO eligibility (RDR-067, AUT-255..258).

The Settings screen does not invent a second source of truth. The *effective*
configuration is the already versioned/hashed automation, compliance and
publication policies plus the persisted operational state; the frequent
controls (global mode, kill switch, integration enable/disable) keep their own
audited boundaries. This module composes the read model and computes the AUTO
**eligibility** without ever promoting a capability: ``eligible`` is fail-closed
and ``promotes_automatically`` is always ``False`` (AUT-257, AUT-258, AUT-368).

Criteria that need calibration data the node does not collect yet (Shadow
samples, human agreement, P0/P1 classification, validation-failure counters)
are reported ``UNAVAILABLE`` instead of being faked, so an unproven criterion
can never look satisfied (AUT-350, AUT-351).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from radar.domain.human_action import HumanAction
from radar.domain.operations import ChannelCompliancePolicy, IntegrationHealth

#: Version of the public Settings contract (``docs/04_DATA_CONTRACTS.md``).
SETTINGS_SCHEMA_VERSION = "1.0"

#: Entity type recorded for the settings read model (no persistence row).
ENTITY_SETTINGS = "settings"


class AutoEligibilityState(StrEnum):
    """Verification state of one AUTO eligibility criterion (AUT-350)."""

    MET = "MET"
    NOT_MET = "NOT_MET"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class AutoEligibilityCriterion:
    """One explicit criterion behind the AUTO eligibility decision (AUT-258)."""

    criterion_id: str
    state: AutoEligibilityState
    detail: str

    def to_contract(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion_id,
            "state": self.state.value,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class AutoEligibility:
    """Read-only AUTO readiness; it never promotes a capability (AUT-257)."""

    eligible: bool
    promotes_automatically: bool
    requires_human_decision: bool
    criteria: tuple[AutoEligibilityCriterion, ...]

    def to_contract(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "promotes_automatically": self.promotes_automatically,
            "requires_human_decision": self.requires_human_decision,
            "criteria": [criterion.to_contract() for criterion in self.criteria],
        }


def evaluate_auto_eligibility(
    *,
    compliance_policy: ChannelCompliancePolicy,
    integrations: tuple[IntegrationHealth, ...],
    open_human_actions: tuple[HumanAction, ...],
    now: datetime,
) -> AutoEligibility:
    """Compute fail-closed AUTO eligibility from real, available evidence.

    A criterion is ``MET`` only from data the node actually has. The criteria
    that depend on calibration counters are ``UNAVAILABLE``, so the aggregate is
    eligible only when every observable criterion passes *and* no criterion is
    unproven -- which keeps the answer honest and the promotion human.
    """

    criteria: list[AutoEligibilityCriterion] = []

    block_reason = compliance_policy.blocking_reason(now)
    criteria.append(
        AutoEligibilityCriterion(
            criterion_id="compliance_policy",
            state=(
                AutoEligibilityState.MET if block_reason is None else AutoEligibilityState.NOT_MET
            ),
            detail=(
                "Compliance policy vigente e não bloqueante"
                if block_reason is None
                else f"Compliance bloqueia: {block_reason}"
            ),
        )
    )

    if not integrations:
        criteria.append(
            AutoEligibilityCriterion(
                criterion_id="integration_health",
                state=AutoEligibilityState.NOT_MET,
                detail="Nenhuma integração registrada; saúde não comprovada",
            )
        )
    else:
        unhealthy = tuple(item.name for item in integrations if not item.is_operational)
        criteria.append(
            AutoEligibilityCriterion(
                criterion_id="integration_health",
                state=(AutoEligibilityState.MET if not unhealthy else AutoEligibilityState.NOT_MET),
                detail=(
                    "Todas as integrações registradas operacionais"
                    if not unhealthy
                    else "Integrações não operacionais: " + ", ".join(unhealthy)
                ),
            )
        )

    criteria.append(
        AutoEligibilityCriterion(
            criterion_id="open_human_actions",
            state=(
                AutoEligibilityState.MET if not open_human_actions else AutoEligibilityState.NOT_MET
            ),
            detail=(
                "Nenhuma intervenção humana aberta"
                if not open_human_actions
                else f"{len(open_human_actions)} intervenção(ões) humana(s) aberta(s)"
            ),
        )
    )

    criteria.extend(
        AutoEligibilityCriterion(
            criterion_id=criterion_id,
            state=AutoEligibilityState.UNAVAILABLE,
            detail=detail,
        )
        for criterion_id, detail in (
            ("shadow_samples", "Amostragem do Shadow não coletada neste nó"),
            ("human_agreement", "Concordância humana não coletada neste nó"),
            ("p0_p1_open", "Classificação P0/P1 não disponível neste nó"),
            ("validation_failures", "Falhas de validação não agregadas neste nó"),
        )
    )

    eligible = all(criterion.state is AutoEligibilityState.MET for criterion in criteria)
    return AutoEligibility(
        eligible=eligible,
        promotes_automatically=False,
        requires_human_decision=True,
        criteria=tuple(criteria),
    )


__all__ = [
    "ENTITY_SETTINGS",
    "SETTINGS_SCHEMA_VERSION",
    "AutoEligibility",
    "AutoEligibilityCriterion",
    "AutoEligibilityState",
    "evaluate_auto_eligibility",
]
