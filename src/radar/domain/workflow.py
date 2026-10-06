"""Workflow Engine planning: approval gate, next step and aging/TTL (RDR-041).

This module implements the deterministic part of the Workflow Engine described in
``docs/08_WORKFLOW_ENGINE.md`` (AUT-116..AUT-120):

* the **approval gate** -- an Opportunity is only planned from a Candidate whose
  latest immutable Evaluation decided ``APPROVE``; a ``REJECT`` never advances and
  a ``REVIEW`` requires an explicit human resolution (AUT-032, AUT-147);
* the **next step** -- the engine (never a worker calling another worker,
  AUT-119) plans the next Job (``GENERATE_AFFILIATE_LINK``) and the Opportunity
  state that goes with it;
* **aging/TTL** -- a Candidate whose Evaluation is older than the configured TTL
  must be revalidated before consuming AI or any dependent step, so the engine
  raises ``RAD-WF-005`` (AUT-135, AUT-144).

The TTL is operational configuration, not a hardcoded constant (AUT-045). The
SDDs do not approve a numeric TTL, so the approved baseline leaves it explicitly
unset; an operator enables the gate with a versioned/hashed policy. When the TTL
is unset the plan reports the explicit gap instead of inventing a value.

The module is framework-free (no FastAPI/SQLAlchemy/Chrome) and never calls AI
(AUT-397, AUT-031).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from radar.domain.capture import CandidateState
from radar.domain.errors import RadarError, RadarException
from radar.domain.evaluation import Decision, Evaluation
from radar.domain.job import JobType
from radar.domain.opportunity import OpportunityState

#: Version of the public workflow contract.
WORKFLOW_SCHEMA_VERSION = "1.0"

#: Version of the workflow policy document schema.
WORKFLOW_POLICY_SCHEMA_VERSION = "1.0"

#: Error codes (see ``docs/ERROR_CATALOG.md``).
REVALIDATION_REQUIRED = "RAD-WF-005"
CANDIDATE_REVIEW_REQUIRED = "RAD-WF-017"
WORKFLOW_POLICY_INVALID = "RAD-CFG-011"

#: Next Job the engine creates once a Candidate is approved (SDD-08).
NEXT_JOB_AFTER_APPROVAL = JobType.GENERATE_AFFILIATE_LINK

#: Opportunity state the engine records when it creates the next step.
STATE_AFTER_APPROVAL = OpportunityState.LINK_PENDING

#: Candidate states that can never become an Opportunity.
BLOCKED_CANDIDATE_STATES: frozenset[CandidateState] = frozenset(
    {CandidateState.REJECTED, CandidateState.EXPIRED, CandidateState.ERROR}
)

#: Warning emitted when the aging/TTL gate is not configured.
WARNING_TTL_NOT_CONFIGURED = "WORKFLOW_TTL_NOT_CONFIGURED"


class WorkflowOutcome(StrEnum):
    """What the engine plans to do with a Candidate (RDR-041)."""

    CREATE_OPPORTUNITY = "CREATE_OPPORTUNITY"
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class WorkflowError(RadarException):
    """Raised when the Workflow Engine cannot advance a Candidate."""


def revalidation_required_error(
    *,
    entity_type: str,
    entity_id: str,
    age_seconds: int,
    ttl_seconds: int,
    evaluation_id: str | None = None,
) -> WorkflowError:
    """Build the structured ``RAD-WF-005`` error for aged/stale facts.

    Revalidation is an explicit operational/human step (a new capture or a new
    Evaluation), not a blind retry, so the error is not retryable and explains the
    impact and the next steps (AUT-135, AUT-144).
    """

    context: dict[str, Any] = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "age_seconds": age_seconds,
        "ttl_seconds": ttl_seconds,
    }
    if evaluation_id is not None:
        context["evaluation_id"] = evaluation_id
    return WorkflowError(
        RadarError(
            code=REVALIDATION_REQUIRED,
            message="Dados envelhecidos exigem revalidação antes de avançar",
            retryable=False,
            action=(
                "Revalidar a oferta (nova captura/avaliação) antes de consumir IA "
                "ou criar a próxima etapa"
            ),
            context=context,
        )
    )


def workflow_policy_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> WorkflowError:
    """Build the structured ``RAD-CFG-011`` error for an invalid workflow policy."""

    return WorkflowError(
        RadarError(
            code=WORKFLOW_POLICY_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o arquivo de policy do workflow e validar novamente",
            context=dict(context or {}),
        )
    )


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _to_ttl(value: Any, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise workflow_policy_invalid_error(
            "TTL deve ser um inteiro de segundos maior que zero ou nulo",
            context={"field": field_name},
        )
    return value


@dataclass(frozen=True, slots=True)
class WorkflowPolicy:
    """Versioned, hashed workflow configuration (AUT-045, AUT-207).

    Both TTLs are optional on purpose: the SDDs do not approve a numeric TTL, so
    the baseline keeps them unset and the aging gate is an explicit operational
    decision. A configured value must be a positive integer number of seconds.
    """

    policy_version: str
    content_hash: str
    candidate_ttl_seconds: int | None = None
    opportunity_ttl_seconds: int | None = None

    @property
    def candidate_ttl_configured(self) -> bool:
        return self.candidate_ttl_seconds is not None

    @property
    def opportunity_ttl_configured(self) -> bool:
        return self.opportunity_ttl_seconds is not None

    def candidate_is_aged(self, *, created_at: datetime, now: datetime) -> bool:
        """True when the facts are older than the configured Candidate TTL."""

        if self.candidate_ttl_seconds is None:
            return False
        age = (_to_utc(now) - _to_utc(created_at)).total_seconds()
        return age > self.candidate_ttl_seconds

    def opportunity_is_aged(self, *, created_at: datetime, now: datetime) -> bool:
        """True when the Opportunity is older than the configured Opportunity TTL."""

        if self.opportunity_ttl_seconds is None:
            return False
        age = (_to_utc(now) - _to_utc(created_at)).total_seconds()
        return age > self.opportunity_ttl_seconds

    def to_contract(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "policy_hash": self.content_hash,
            "candidate_ttl_seconds": self.candidate_ttl_seconds,
            "opportunity_ttl_seconds": self.opportunity_ttl_seconds,
        }


def _content_hash(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_workflow_policy(document: Mapping[str, Any]) -> WorkflowPolicy:
    """Build and validate the workflow policy from a plain document.

    A document without TTLs is valid and means the aging gate is not configured;
    an unknown ``schema_version``, a missing version or a non-positive TTL fails
    closed with ``RAD-CFG-011``.
    """

    if not isinstance(document, Mapping):
        raise workflow_policy_invalid_error("Policy deve ser um objeto")

    schema_version = document.get("schema_version")
    if schema_version is not None and str(schema_version) != WORKFLOW_POLICY_SCHEMA_VERSION:
        raise workflow_policy_invalid_error(
            "schema_version de policy não suportada",
            context={"schema_version": str(schema_version)},
        )

    version = str(document.get("policy_version") or "").strip()
    if not version:
        raise workflow_policy_invalid_error("policy_version é obrigatório")

    candidate_ttl = _to_ttl(
        document.get("candidate_ttl_seconds"), field_name="candidate_ttl_seconds"
    )
    opportunity_ttl = _to_ttl(
        document.get("opportunity_ttl_seconds"), field_name="opportunity_ttl_seconds"
    )
    normalized = {
        "schema_version": WORKFLOW_POLICY_SCHEMA_VERSION,
        "policy_version": version,
        "candidate_ttl_seconds": candidate_ttl,
        "opportunity_ttl_seconds": opportunity_ttl,
    }
    return WorkflowPolicy(
        policy_version=version,
        content_hash=_content_hash(normalized),
        candidate_ttl_seconds=candidate_ttl,
        opportunity_ttl_seconds=opportunity_ttl,
    )


#: Approved baseline: no TTL is invented because the SDDs do not approve one.
APPROVED_WORKFLOW_POLICY_DOCUMENT: dict[str, Any] = {
    "schema_version": WORKFLOW_POLICY_SCHEMA_VERSION,
    "policy_version": "workflow-policy-1.0",
}

#: The approved baseline workflow policy.
APPROVED_WORKFLOW_POLICY: WorkflowPolicy = build_workflow_policy(APPROVED_WORKFLOW_POLICY_DOCUMENT)


@dataclass(frozen=True, slots=True)
class WorkflowPlan:
    """Deterministic plan the Workflow Engine executes for one Candidate."""

    outcome: WorkflowOutcome
    reason: str
    next_job_type: JobType | None = None
    next_state: OpportunityState | None = None
    ttl_configured: bool = False

    def to_contract(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "next_job_type": None if self.next_job_type is None else self.next_job_type.value,
            "next_state": None if self.next_state is None else self.next_state.value,
            "ttl_configured": self.ttl_configured,
        }


def plan_advance(
    *,
    candidate_state: CandidateState,
    evaluation: Evaluation,
    now: datetime,
    policy: WorkflowPolicy = APPROVED_WORKFLOW_POLICY,
) -> WorkflowPlan:
    """Plan the next workflow step for a Candidate (RDR-041).

    An Opportunity is only planned when the latest Evaluation decided ``APPROVE``
    and the Candidate is not in a blocked terminal state (AUT-032). ``REJECT``
    never advances; ``REVIEW`` requires an explicit human resolution. Before the
    dependent step, an aged Evaluation raises ``RAD-WF-005`` when the Candidate TTL
    is configured (AUT-144).
    """

    if candidate_state in BLOCKED_CANDIDATE_STATES:
        return WorkflowPlan(
            outcome=WorkflowOutcome.REJECTED,
            reason="CANDIDATE_NOT_ELIGIBLE",
            ttl_configured=policy.candidate_ttl_configured,
        )
    if evaluation.decision is Decision.REJECT:
        return WorkflowPlan(
            outcome=WorkflowOutcome.REJECTED,
            reason="EVALUATION_REJECTED",
            ttl_configured=policy.candidate_ttl_configured,
        )
    if evaluation.decision is Decision.REVIEW:
        return WorkflowPlan(
            outcome=WorkflowOutcome.REVIEW_REQUIRED,
            reason="EVALUATION_REVIEW_REQUIRED",
            ttl_configured=policy.candidate_ttl_configured,
        )

    # APPROVE: the approval gate passed. Revalidate aged facts before the step.
    if policy.candidate_is_aged(created_at=evaluation.created_at, now=now):
        age_seconds = int((_to_utc(now) - _to_utc(evaluation.created_at)).total_seconds())
        raise revalidation_required_error(
            entity_type="candidate",
            entity_id=evaluation.candidate_id,
            age_seconds=age_seconds,
            ttl_seconds=policy.candidate_ttl_seconds or 0,
            evaluation_id=evaluation.evaluation_id,
        )
    return WorkflowPlan(
        outcome=WorkflowOutcome.CREATE_OPPORTUNITY,
        reason="EVALUATION_APPROVED",
        next_job_type=NEXT_JOB_AFTER_APPROVAL,
        next_state=STATE_AFTER_APPROVAL,
        ttl_configured=policy.candidate_ttl_configured,
    )


__all__ = [
    "APPROVED_WORKFLOW_POLICY",
    "APPROVED_WORKFLOW_POLICY_DOCUMENT",
    "BLOCKED_CANDIDATE_STATES",
    "CANDIDATE_REVIEW_REQUIRED",
    "NEXT_JOB_AFTER_APPROVAL",
    "REVALIDATION_REQUIRED",
    "STATE_AFTER_APPROVAL",
    "WARNING_TTL_NOT_CONFIGURED",
    "WORKFLOW_POLICY_INVALID",
    "WORKFLOW_POLICY_SCHEMA_VERSION",
    "WORKFLOW_SCHEMA_VERSION",
    "WorkflowError",
    "WorkflowOutcome",
    "WorkflowPlan",
    "WorkflowPolicy",
    "build_workflow_policy",
    "plan_advance",
    "revalidation_required_error",
    "workflow_policy_invalid_error",
]
