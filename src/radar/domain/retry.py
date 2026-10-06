"""Failure classification, configured backoff and Dead Job routing (RDR-037/038).

The Workflow Engine classifies a job failure into one of the three retry
categories of ``docs/08_WORKFLOW_ENGINE.md`` (AUT-129):

* ``TRANSIENT`` -- retried with the **configured backoff** while the attempt
  budget lasts, then it exhausts;
* ``PERMANENT`` -- never retried automatically;
* ``HUMAN_REQUIRED`` -- never retried automatically; it requires a human and,
  like exhaustion, routes to the Dead Job Queue with a HumanAction.

Classification is derived from the structured ``error_code`` (AUT-043), never
from an operator's free text: an authentication error such as ``RAD-AI-001``
maps to ``HUMAN_REQUIRED`` regardless of who reports it, so AUTH_REQUIRED can
never enter a retry loop (AUT-125). An unknown error code fails closed as
``PERMANENT`` instead of being retried blindly.

The module is framework-free (no FastAPI/SQLAlchemy/Chrome); the atomic
persistence of the transition lives in infrastructure (AUT-397).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from radar.domain.errors import RadarError, RadarException
from radar.domain.human_action import HumanAction, HumanActionType
from radar.domain.job import (
    JOB_INPUT_INVALID,
    Job,
    JobStatus,
    job_lease_not_held_error,
    job_state_invalid_error,
)

#: Version of the retry policy document schema.
RETRY_POLICY_SCHEMA_VERSION = "1.0"

#: Error code for an invalid retry policy (see ``docs/ERROR_CATALOG.md``).
RETRY_POLICY_INVALID = "RAD-CFG-010"

#: Error code emitted by the catalog when retries are exhausted.
JOB_DEAD = "RAD-WF-003"

#: Approved initial backoff of ``docs/08_WORKFLOW_ENGINE.md``: 30s, 2m, 10m, 30m.
APPROVED_BACKOFF_SECONDS: tuple[int, ...] = (30, 120, 600, 1800)

#: Structured reason recorded on the resolution/audit trail.
REASON_RETRY_SCHEDULED = "RETRY_SCHEDULED"
REASON_RETRIES_EXHAUSTED = "RETRIES_EXHAUSTED"
REASON_PERMANENT_FAILURE = "PERMANENT_FAILURE"
REASON_HUMAN_INTERVENTION_REQUIRED = "HUMAN_INTERVENTION_REQUIRED"

#: Error codes that are safe to retry with backoff (AUT-130).
TRANSIENT_ERROR_CODES: frozenset[str] = frozenset(
    {
        "RAD-WF-001",  # JOB_TIMEOUT
        "RAD-WF-002",  # RATE_LIMITED
        "RAD-AI-002",  # AI_PROVIDER_UNAVAILABLE
        "RAD-ML-004",  # ML_LINK_RESULT_STALE
        "RAD-DB-003",  # DATABASE_UNAVAILABLE
    }
)

#: Error codes that require a human and must never retry automatically.
HUMAN_REQUIRED_ERROR_CODES: frozenset[str] = frozenset(
    {
        "RAD-AI-001",  # AI_AUTH_REQUIRED
        "RAD-WA-001",  # WHATSAPP_AUTH_REQUIRED
        "RAD-SP-002",  # SHOPEE_API_AUTH_REQUIRED
        "RAD-SP-003",  # SHOPEE_API_ACCESS_REQUIRED
        "RAD-SP-005",  # SHOPEE_LINK_RESULT_UNKNOWN
        "RAD-WA-004",  # WHATSAPP_SEND_RESULT_UNKNOWN
        "RAD-WA-005",  # WHATSAPP_DESTINATION_IDENTITY_UNVERIFIED
        "RAD-CMP-002",  # POLICY_REVIEW_REQUIRED
        "RAD-CFG-003",  # SECRET_UNAVAILABLE
        "RAD-CFG-004",  # SECRET_ACCESS_DENIED
        "RAD-BKP-001",  # BACKUP_FAILED
    }
)

#: Authentication codes that map to a dedicated guidance action.
AI_AUTH_ERROR_CODES: frozenset[str] = frozenset({"RAD-AI-001"})
MARKETPLACE_AUTH_ERROR_CODES: frozenset[str] = frozenset({"RAD-WA-001", "RAD-SP-002", "RAD-SP-003"})


class FailureClass(StrEnum):
    """Retry categories of ``docs/08_WORKFLOW_ENGINE.md`` (AUT-129)."""

    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


class FailureAction(StrEnum):
    """Outcome of a classified failure for the Job state machine."""

    RETRY_WAIT = "RETRY_WAIT"
    DEAD = "DEAD"
    FAILED = "FAILED"


class RetryError(RadarException):
    """Raised when a failure cannot be classified or a policy is invalid."""


def retry_policy_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> RetryError:
    """Build the structured error for an invalid retry policy."""

    return RetryError(
        RadarError(
            code=RETRY_POLICY_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o arquivo de policy de retry e validar novamente",
            context=dict(context or {}),
        )
    )


def failure_input_invalid_error(message: str, *, field: str) -> RetryError:
    """Build the structured ``RAD-WF-006`` error for an invalid failure input."""

    return RetryError(
        RadarError(
            code=JOB_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o error_code informado e reenviar a falha",
            context={"field": field},
        )
    )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Versioned, hashed backoff schedule for transient failures (AUT-130).

    The schedule is operational configuration, not hardcoded logic; the approved
    reference is ``APPROVED_BACKOFF_SECONDS`` (30s, 2m, 10m, 30m).
    """

    policy_version: str
    content_hash: str
    backoff_seconds: tuple[int, ...]

    def delay_for(self, attempts: int) -> int:
        """Return the backoff before the attempt following ``attempts`` claims.

        ``attempts`` is the number of attempts already consumed (it increments on
        claim), so ``attempts=1`` yields the first backoff. A schedule shorter
        than the attempt budget clamps to its last value (never an unbounded
        retry: the attempt budget still bounds the loop).
        """

        if not self.backoff_seconds:
            raise retry_policy_invalid_error("backoff_seconds não pode ser vazio")
        index = min(max(attempts, 1), len(self.backoff_seconds)) - 1
        return self.backoff_seconds[index]

    def to_contract(self) -> dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "policy_hash": self.content_hash,
            "backoff_seconds": list(self.backoff_seconds),
        }


@dataclass(frozen=True, slots=True)
class FailureResolution:
    """Deterministic outcome of a classified job failure."""

    action: FailureAction
    failure_class: FailureClass
    retryable: bool
    reason: str
    delay_seconds: int | None = None
    available_at: datetime | None = None
    human_action_type: HumanActionType | None = None
    resolution_code: str | None = None

    def to_contract(self) -> dict[str, Any]:
        return {
            "failure_class": self.failure_class.value,
            "action": self.action.value,
            "retryable": self.retryable,
            "reason": self.reason,
            "delay_seconds": self.delay_seconds,
            "available_at": (
                None if self.available_at is None else _to_utc(self.available_at).isoformat()
            ),
            "human_action_type": (
                None if self.human_action_type is None else self.human_action_type.value
            ),
            "resolution_code": self.resolution_code,
        }


@dataclass(frozen=True, slots=True)
class JobFailureResult:
    """Persisted result of reporting a job failure through the public boundary."""

    job: Job
    resolution: FailureResolution
    error_code: str
    human_action: HumanAction | None = None

    def to_contract(self) -> dict[str, Any]:
        contract = dict(self.job.to_contract())
        contract["failure"] = {"error_code": self.error_code, **self.resolution.to_contract()}
        contract["human_action"] = (
            None if self.human_action is None else self.human_action.to_contract()
        )
        return contract


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def require_error_code(error_code: object) -> str:
    """Validate and normalize the structured error code reported for a failure."""

    if not isinstance(error_code, str):
        raise failure_input_invalid_error("error_code deve ser texto", field="error_code")
    cleaned = error_code.strip()
    if not cleaned:
        raise failure_input_invalid_error("error_code é obrigatório", field="error_code")
    if len(cleaned) > 64:
        raise failure_input_invalid_error("error_code excede o tamanho máximo", field="error_code")
    return cleaned


def classify_failure(error_code: object) -> FailureClass:
    """Classify a structured error code into a retry category (AUT-129).

    Unknown codes fail closed as ``PERMANENT``: an unrecognized failure is never
    retried automatically, so a novel error cannot create a retry loop.
    """

    code = require_error_code(error_code)
    if code in TRANSIENT_ERROR_CODES:
        return FailureClass.TRANSIENT
    if code in HUMAN_REQUIRED_ERROR_CODES:
        return FailureClass.HUMAN_REQUIRED
    return FailureClass.PERMANENT


def human_action_type_for(failure_class: FailureClass, error_code: str) -> HumanActionType:
    """Resolve the intervention kind for a failure that needs a human."""

    if failure_class is FailureClass.HUMAN_REQUIRED:
        if error_code in AI_AUTH_ERROR_CODES:
            return HumanActionType.RESTORE_AI_AUTH
        if error_code in MARKETPLACE_AUTH_ERROR_CODES:
            return HumanActionType.AUTHENTICATE_MARKETPLACE
    return HumanActionType.DEAD_JOB_REVIEW


def resolve_failure(
    job: Job,
    *,
    error_code: str,
    now: datetime,
    policy: RetryPolicy,
) -> FailureResolution:
    """Decide retry/dead/failed for ``job`` given a classified failure.

    ``TRANSIENT`` schedules a retry with the configured backoff while
    ``attempts < max_attempts``; once the attempt budget is exhausted it becomes
    ``DEAD`` with a ``DEAD_JOB_REVIEW`` HumanAction. ``PERMANENT`` becomes
    ``FAILED`` with no retry. ``HUMAN_REQUIRED`` becomes ``DEAD`` immediately
    (never ``RETRY_WAIT``) with a HumanAction, so AUTH_REQUIRED/HUMAN_REQUIRED
    never loop (AUT-125).
    """

    reference = _to_utc(now)
    failure_class = classify_failure(error_code)
    if failure_class is FailureClass.TRANSIENT and job.attempts < job.max_attempts:
        delay = policy.delay_for(job.attempts)
        return FailureResolution(
            action=FailureAction.RETRY_WAIT,
            failure_class=failure_class,
            retryable=True,
            reason=REASON_RETRY_SCHEDULED,
            delay_seconds=delay,
            available_at=reference + timedelta(seconds=delay),
        )
    if failure_class is FailureClass.PERMANENT:
        return FailureResolution(
            action=FailureAction.FAILED,
            failure_class=failure_class,
            retryable=False,
            reason=REASON_PERMANENT_FAILURE,
        )
    exhausted = failure_class is FailureClass.TRANSIENT
    return FailureResolution(
        action=FailureAction.DEAD,
        failure_class=failure_class,
        retryable=False,
        reason=REASON_RETRIES_EXHAUSTED if exhausted else REASON_HUMAN_INTERVENTION_REQUIRED,
        human_action_type=human_action_type_for(failure_class, error_code),
        resolution_code=JOB_DEAD if exhausted else None,
    )


def apply_failure(
    job: Job,
    resolution: FailureResolution,
    *,
    worker_id: str,
    now: datetime,
) -> Job:
    """Return the same job transitioned by the failure resolution.

    Only the worker holding a valid lease can report the failure of a claimed or
    running job; a stale/foreign worker is rejected (AUT-140). The lease is
    always released because the worker stopped executing.
    """

    if job.status not in (JobStatus.CLAIMED, JobStatus.RUNNING):
        raise job_state_invalid_error(job.id, current=job.status, expected="CLAIMED or RUNNING")
    if job.locked_by != worker_id or not job.lease_is_active(now):
        raise job_lease_not_held_error(
            job.id,
            worker_id=worker_id,
            reason="lease_expired_or_not_owner",
            holder=job.locked_by,
        )
    status = {
        FailureAction.RETRY_WAIT: JobStatus.RETRY_WAIT,
        FailureAction.DEAD: JobStatus.DEAD,
        FailureAction.FAILED: JobStatus.FAILED,
    }[resolution.action]
    return replace(
        job,
        status=status,
        available_at=resolution.available_at or job.available_at,
        locked_by=None,
        locked_at=None,
        lease_expires_at=None,
        updated_at=_to_utc(now),
    )


def _to_positive_int(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise retry_policy_invalid_error(
            "valor deve ser um inteiro de segundos maior que zero",
            context={"field": field_name},
        )
    return value


def build_retry_policy(document: Mapping[str, Any]) -> RetryPolicy:
    """Build and validate the retry policy from a plain document.

    A document without an explicit schedule falls back to the approved baseline.
    An empty or non-positive schedule fails closed with ``RAD-CFG-010``.
    """

    if not isinstance(document, Mapping):
        raise retry_policy_invalid_error("Policy deve ser um objeto")

    schema_version = document.get("schema_version")
    if schema_version is not None and str(schema_version) != RETRY_POLICY_SCHEMA_VERSION:
        raise retry_policy_invalid_error(
            "schema_version de policy não suportada",
            context={"schema_version": str(schema_version)},
        )

    version = str(document.get("policy_version") or "").strip()
    if not version:
        raise retry_policy_invalid_error("policy_version é obrigatório")

    raw_schedule = document.get("backoff_seconds")
    if raw_schedule is None:
        schedule = APPROVED_BACKOFF_SECONDS
    else:
        if not isinstance(raw_schedule, (list, tuple)) or not raw_schedule:
            raise retry_policy_invalid_error(
                "backoff_seconds deve ser uma lista não vazia de inteiros",
                context={"field": "backoff_seconds"},
            )
        schedule = tuple(
            _to_positive_int(item, field_name="backoff_seconds") for item in raw_schedule
        )

    normalized = {
        "schema_version": RETRY_POLICY_SCHEMA_VERSION,
        "policy_version": version,
        "backoff_seconds": list(schedule),
    }
    return RetryPolicy(
        policy_version=version,
        content_hash=_content_hash(normalized),
        backoff_seconds=schedule,
    )


def _content_hash(document: Mapping[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: Approved baseline used when no operator file is configured (RDR-037).
APPROVED_RETRY_POLICY_DOCUMENT: dict[str, Any] = {
    "schema_version": RETRY_POLICY_SCHEMA_VERSION,
    "policy_version": "retry-policy-1.0",
    "backoff_seconds": list(APPROVED_BACKOFF_SECONDS),
}

#: The approved baseline retry policy.
APPROVED_RETRY_POLICY: RetryPolicy = build_retry_policy(APPROVED_RETRY_POLICY_DOCUMENT)


__all__ = [
    "AI_AUTH_ERROR_CODES",
    "APPROVED_BACKOFF_SECONDS",
    "APPROVED_RETRY_POLICY",
    "APPROVED_RETRY_POLICY_DOCUMENT",
    "HUMAN_REQUIRED_ERROR_CODES",
    "JOB_DEAD",
    "MARKETPLACE_AUTH_ERROR_CODES",
    "REASON_HUMAN_INTERVENTION_REQUIRED",
    "REASON_PERMANENT_FAILURE",
    "REASON_RETRIES_EXHAUSTED",
    "REASON_RETRY_SCHEDULED",
    "RETRY_POLICY_INVALID",
    "RETRY_POLICY_SCHEMA_VERSION",
    "TRANSIENT_ERROR_CODES",
    "FailureAction",
    "FailureClass",
    "FailureResolution",
    "JobFailureResult",
    "RetryError",
    "RetryPolicy",
    "apply_failure",
    "build_retry_policy",
    "classify_failure",
    "failure_input_invalid_error",
    "human_action_type_for",
    "require_error_code",
    "resolve_failure",
    "retry_policy_invalid_error",
]
