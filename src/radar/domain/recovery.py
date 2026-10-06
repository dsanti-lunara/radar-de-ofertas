"""Startup Recovery Manager: reconcile local work after a crash (RDR-042).

This module implements the framework-free core of the recovery step of
``docs/08_WORKFLOW_ENGINE.md`` (AUT-133, AUT-155) and the unclean-shutdown
handling of ``docs/10_PERSISTENCE_AND_RECOVERY.md`` (AUT-228, AUT-229):

* :class:`RuntimeState` is the durable shutdown marker. A clean shutdown records
  the marker; a startup that finds the marker unset detects an **unclean
  shutdown** and audits it (AUT-229);
* an interrupted ``CLAIMED``/``RUNNING`` job is reconciled: its orphan lease is
  cleared and, when its execution is safe to retry, it returns to ``PENDING`` so
  another worker can recover it (AUT-133, AUT-140);
* a job that could have produced an **unknown external side effect** is **not**
  requeued automatically. It is blocked (``DEAD``) and audited, so recovery
  never resends a side effect whose result is unknown. The publication
  suspension/HumanAction integration belongs to TKT-24 (GRILL-002);
* orphan logical locks are cleared and missed schedules are coalesced by the
  Scheduler (AUT-134).

The module is deliberately side-effect free and framework-free (no
FastAPI/SQLAlchemy/Chrome) so the domain stays independent from infrastructure
(AUT-397). It never calls AI, never creates an affiliate link and never
publishes (AUT-031, AUT-164).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from radar.domain.errors import RadarError, RadarException
from radar.domain.job import Job, JobStatus, JobType, Lock

#: Version of the public Recovery contract (``docs/04_DATA_CONTRACTS.md``).
RECOVERY_SCHEMA_VERSION = "1.0"

#: Error code (see ``docs/ERROR_CATALOG.md``).
RECOVERY_INPUT_INVALID = "RAD-WF-019"

#: Primary key of the single runtime-state row.
CORE_STATE_ID = "core"

#: Provenance source recorded on recovery audit events.
AUDIT_SOURCE_RECOVERY = "recovery"

#: Entity type recorded on recovery audit events.
ENTITY_RUNTIME = "runtime"

#: Reason codes recorded when reconciling an interrupted job.
REASON_ORPHAN_LEASE = "ORPHAN_LEASE"
REASON_UNKNOWN_RESULT = "UNKNOWN_RESULT"


class RecoveryTrigger(StrEnum):
    """Origin of a recovery run."""

    STARTUP = "STARTUP"
    MANUAL = "MANUAL"


class RecoveryAction(StrEnum):
    """Reconciliation outcome for one interrupted job."""

    REQUEUE = "REQUEUE"
    BLOCK = "BLOCK"


#: Job types whose execution may have produced an external side effect with an
#: unknown result. Recovery never auto-resends these (GRILL-002, RECON-004).
EXTERNAL_EFFECT_JOB_TYPES: frozenset[JobType] = frozenset(
    {
        JobType.GENERATE_AFFILIATE_LINK,
        JobType.PUBLISH_TELEGRAM,
        JobType.PUBLISH_WHATSAPP,
    }
)


class RecoveryError(RadarException):
    """Base error raised when a recovery operation cannot be completed."""


def recovery_input_invalid_error(
    message: str, *, context: Mapping[str, Any] | None = None
) -> RecoveryError:
    """Build the structured ``RAD-WF-019`` error for invalid recovery input."""

    return RecoveryError(
        RadarError(
            code=RECOVERY_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o input de recovery e enviar novamente",
            context=dict(context or {}),
        )
    )


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def require_schema_version(value: object) -> str:
    """Validate the public recovery ``schema_version``."""

    if str(value) != RECOVERY_SCHEMA_VERSION:
        raise recovery_input_invalid_error(
            "schema_version de recovery não suportada",
            context={"field": "schema_version", "supported": RECOVERY_SCHEMA_VERSION},
        )
    return RECOVERY_SCHEMA_VERSION


def coerce_trigger(value: object) -> RecoveryTrigger:
    """Validate and normalize a recovery trigger, failing closed when unknown."""

    if value is None:
        return RecoveryTrigger.STARTUP
    if isinstance(value, RecoveryTrigger):
        return value
    try:
        return RecoveryTrigger(str(value))
    except ValueError as exc:
        raise recovery_input_invalid_error(
            "trigger de recovery inválido",
            context={"field": "trigger", "allowed": [item.value for item in RecoveryTrigger]},
        ) from exc


def is_external_effect_job(job_type: JobType) -> bool:
    """True when a job type may have produced an unknown external side effect."""

    return job_type in EXTERNAL_EFFECT_JOB_TYPES


@dataclass(frozen=True, slots=True)
class RuntimeState:
    """Durable shutdown/recovery marker of the Core (AUT-229).

    ``clean_shutdown`` is ``True`` only after an explicit clean shutdown. A
    startup that reads ``clean_shutdown=False`` (or a state created by a previous
    startup that never shut down cleanly) detects an unclean shutdown.
    """

    clean_shutdown: bool
    recovery_count: int
    started_at: datetime | None = None
    shutdown_at: datetime | None = None
    last_recovery_at: datetime | None = None
    schema_version: str = RECOVERY_SCHEMA_VERSION
    updated_at: datetime | None = None

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "clean_shutdown": self.clean_shutdown,
            "started_at": None if self.started_at is None else _to_utc(self.started_at).isoformat(),
            "shutdown_at": (
                None if self.shutdown_at is None else _to_utc(self.shutdown_at).isoformat()
            ),
            "last_recovery_at": (
                None
                if self.last_recovery_at is None
                else _to_utc(self.last_recovery_at).isoformat()
            ),
            "recovery_count": self.recovery_count,
            "updated_at": (
                None if self.updated_at is None else _to_utc(self.updated_at).isoformat()
            ),
        }


@dataclass(frozen=True, slots=True)
class JobRecoveryDecision:
    """Deterministic reconciliation decision for one interrupted job."""

    action: RecoveryAction
    reason: str

    def to_contract(self) -> dict[str, Any]:
        return {"action": self.action.value, "reason": self.reason}


def plan_job_recovery(job: Job, *, now: datetime) -> JobRecoveryDecision:
    """Decide how to reconcile one interrupted ``CLAIMED``/``RUNNING`` job.

    A safe job returns to the queue (``REQUEUE``). A job that may have produced an
    unknown external side effect is blocked (``BLOCK``) so recovery never resends
    it automatically (GRILL-002). A job that is not interrupted is rejected.
    """

    if job.status not in (JobStatus.CLAIMED, JobStatus.RUNNING):
        raise recovery_input_invalid_error(
            "Job não está interrompido; recovery só reconcilia CLAIMED/RUNNING",
            context={"field": "job", "job_id": job.id, "status": job.status.value},
        )
    if is_external_effect_job(job.type):
        return JobRecoveryDecision(RecoveryAction.BLOCK, REASON_UNKNOWN_RESULT)
    return JobRecoveryDecision(RecoveryAction.REQUEUE, REASON_ORPHAN_LEASE)


def requeue_job(job: Job, *, now: datetime) -> Job:
    """Return the interrupted job as a claimable ``PENDING`` job.

    The orphan lease is cleared, so the previous worker can never confirm the new
    execution (AUT-140) and the job becomes recoverable by another worker.
    """

    reference = _to_utc(now)
    return replace(
        job,
        status=JobStatus.PENDING,
        available_at=reference,
        locked_by=None,
        locked_at=None,
        lease_expires_at=None,
        updated_at=reference,
    )


def block_job(job: Job, *, now: datetime) -> Job:
    """Return the interrupted job as ``DEAD`` with the orphan lease cleared.

    A blocked job is terminal and never claimable again, so recovery cannot resend
    an unknown external side effect. Publication-specific suspension and human
    review are integrated by TKT-24.
    """

    reference = _to_utc(now)
    return replace(
        job,
        status=JobStatus.DEAD,
        locked_by=None,
        locked_at=None,
        lease_expires_at=None,
        updated_at=reference,
    )


def should_clear_lock(lock: Lock, *, now: datetime, unclean_shutdown: bool) -> bool:
    """True when a logical lock is orphaned and must be cleared.

    Under an unclean shutdown every lock is orphaned because its owner process is
    gone; otherwise only an already expired lock is cleared (AUT-140).
    """

    if unclean_shutdown:
        return True
    return not lock.is_active(now)


__all__ = [
    "AUDIT_SOURCE_RECOVERY",
    "CORE_STATE_ID",
    "ENTITY_RUNTIME",
    "EXTERNAL_EFFECT_JOB_TYPES",
    "REASON_ORPHAN_LEASE",
    "REASON_UNKNOWN_RESULT",
    "RECOVERY_INPUT_INVALID",
    "RECOVERY_SCHEMA_VERSION",
    "JobRecoveryDecision",
    "RecoveryAction",
    "RecoveryError",
    "RecoveryTrigger",
    "RuntimeState",
    "block_job",
    "coerce_trigger",
    "is_external_effect_job",
    "plan_job_recovery",
    "recovery_input_invalid_error",
    "requeue_job",
    "require_schema_version",
    "should_clear_lock",
]
