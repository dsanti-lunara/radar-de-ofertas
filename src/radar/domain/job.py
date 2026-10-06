"""Persistent Job model, claim/lease rules and logical locks (RDR-034..036).

This module implements the framework-free core of the Workflow queue described in
``docs/08_WORKFLOW_ENGINE.md``:

* :class:`Job` is the persistent unit of work with ``priority``, ``attempts`` /
  ``max_attempts``, ``available_at`` and the pipeline ``correlation_id``;
* :class:`JobStatus` is the **Job state machine**, deliberately independent from
  any domain state (AUT-118): a Candidate state such as ``NEW`` is never a valid
  Job status;
* a claim grants a single, expiring lease to one worker -- ``locked_by`` /
  ``locked_at`` / ``lease_expires_at`` -- and expiry allows another worker to
  recover the job (AUT-121, AUT-133, AUT-140);
* :class:`Lock` is the separate logical lock with its own expiry (RDR-036), used
  to prevent overlapping equivalent execution.

No AI, HTTP, SQLAlchemy or browser code lives here (AUT-397). Retry/backoff, Dead
Jobs, scheduling and crash recovery are separate tickets; this module only
provides the durable model plus the claim/lease/lock invariants they build on.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from radar.domain.capture import (
    IdFactory,
    default_id_factory,
    find_sensitive_fields,
    sanitize_single_line,
)
from radar.domain.errors import RadarError, RadarException

#: Version of the public Job contract (`docs/04_DATA_CONTRACTS.md`).
JOB_SCHEMA_VERSION = "1.0"

#: Initial reference lease for a claimed job, in seconds (configurable).
DEFAULT_LEASE_SECONDS = 60

#: Conservative initial attempt budget; retry/backoff belongs to RDR-037.
DEFAULT_MAX_ATTEMPTS = 3

#: Error codes (see ``docs/ERROR_CATALOG.md``).
JOB_INPUT_INVALID = "RAD-WF-006"
JOB_NOT_FOUND = "RAD-WF-007"
JOB_NOT_CLAIMABLE = "RAD-WF-008"
JOB_LEASE_NOT_HELD = "RAD-WF-009"
JOB_STATE_INVALID = "RAD-WF-010"
LOCK_UNAVAILABLE = "RAD-WF-004"

#: Entity type recorded on audit events and Evidence-less audit rows.
ENTITY_JOB = "job"

#: Provenance source recorded on job/lock audit events.
AUDIT_SOURCE_JOB = "workflow"


class JobStatus(StrEnum):
    """Persistent states of a Job (SDD-08).

    These are **Job** states, never domain states. ``RETRY_WAIT``, ``FAILED``,
    ``CANCELLED`` and ``DEAD`` are declared here because the SDD defines them;
    their transitions belong to the retry/Dead Job/scheduler tickets.
    """

    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DEAD = "DEAD"


class JobType(StrEnum):
    """Jobs V1 (SDD-08). Only these values are accepted as a Job type."""

    DISCOVER_MARKETPLACE = "DISCOVER_MARKETPLACE"
    NORMALIZE_CAPTURE = "NORMALIZE_CAPTURE"
    PRE_FILTER_CANDIDATE = "PRE_FILTER_CANDIDATE"
    CALCULATE_SCORES = "CALCULATE_SCORES"
    AI_REVIEW = "AI_REVIEW"
    CREATE_OPPORTUNITY = "CREATE_OPPORTUNITY"
    GENERATE_AFFILIATE_LINK = "GENERATE_AFFILIATE_LINK"
    GENERATE_CONTENT = "GENERATE_CONTENT"
    VALIDATE_CONTENT = "VALIDATE_CONTENT"
    REVALIDATE_OFFER = "REVALIDATE_OFFER"
    PUBLISH_TELEGRAM = "PUBLISH_TELEGRAM"
    PUBLISH_WHATSAPP = "PUBLISH_WHATSAPP"
    CHECK_PUBLISHED_OFFER = "CHECK_PUBLISHED_OFFER"
    UPDATE_PUBLICATION = "UPDATE_PUBLICATION"
    EXPIRE_OPPORTUNITY = "EXPIRE_OPPORTUNITY"
    BACKUP_DATABASE = "BACKUP_DATABASE"
    AGGREGATE_DAILY_METRICS = "AGGREGATE_DAILY_METRICS"


def _to_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


class JobError(RadarException):
    """Base error raised when a Job/Lock operation cannot be completed."""


def job_input_invalid_error(message: str, *, context: Mapping[str, Any] | None = None) -> JobError:
    """Build the structured error for an invalid Job/Lock input."""

    return JobError(
        RadarError(
            code=JOB_INPUT_INVALID,
            message=message,
            retryable=False,
            action="Corrigir o input do job e enviar novamente",
            context=dict(context or {}),
        )
    )


def job_not_found_error(job_id: str) -> JobError:
    """Build the structured not-found error for a Job query."""

    return JobError(
        RadarError(
            code=JOB_NOT_FOUND,
            message="Job não encontrado",
            retryable=False,
            action="Verificar o job_id informado",
            context={"job_id": job_id},
        )
    )


def job_not_claimable_error(*, context: Mapping[str, Any] | None = None) -> JobError:
    """Build the structured error for a claim that found no free lease."""

    return JobError(
        RadarError(
            code=JOB_NOT_CLAIMABLE,
            message="Nenhum job disponível para claim",
            retryable=True,
            action="Tentar novamente mais tarde; outro worker pode ter reivindicado o job",
            context=dict(context or {}),
        )
    )


def job_lease_not_held_error(
    job_id: str,
    *,
    worker_id: str,
    reason: str,
    holder: str | None = None,
) -> JobError:
    """Build the structured error for a worker that does not own a valid lease.

    A worker can never confirm another worker's execution, nor confirm a job
    whose lease already expired (AUT-140). The caller must re-claim.
    """

    context: dict[str, Any] = {"job_id": job_id, "worker_id": worker_id, "reason": reason}
    if holder is not None:
        context["holder"] = holder
    return JobError(
        RadarError(
            code=JOB_LEASE_NOT_HELD,
            message="Worker não detém um lease válido deste job",
            retryable=False,
            action="Claimar o job novamente antes de confirmar a execução",
            context=context,
        )
    )


def job_state_invalid_error(job_id: str, *, current: JobStatus, expected: str) -> JobError:
    """Build the structured error for a transition not allowed from the state."""

    return JobError(
        RadarError(
            code=JOB_STATE_INVALID,
            message="Transição de estado de job inválida",
            retryable=False,
            action=f"Confirmar o estado atual do job; esperado {expected}",
            context={"job_id": job_id, "current_status": current.value, "expected": expected},
        )
    )


def lock_unavailable_error(
    name: str,
    *,
    owner: str,
    reason: str,
    holder: str | None = None,
    expires_at: datetime | None = None,
) -> JobError:
    """Build the structured error for a lock held by another worker."""

    context: dict[str, Any] = {"name": name, "owner": owner, "reason": reason}
    if holder is not None:
        context["holder"] = holder
    if expires_at is not None:
        context["expires_at"] = _to_utc(expires_at).isoformat()
    return JobError(
        RadarError(
            code=LOCK_UNAVAILABLE,
            message="Lock lógico indisponível",
            retryable=True,
            action="Aguardar a expiração do lock ou reutilizar o mesmo owner",
            context=context,
        )
    )


@dataclass(frozen=True, slots=True)
class Job:
    """A durable unit of work in the Workflow queue (RDR-034)."""

    id: str
    type: JobType
    status: JobStatus
    priority: int
    attempts: int
    max_attempts: int
    available_at: datetime
    correlation_id: str
    payload: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime
    entity_type: str | None = None
    entity_id: str | None = None
    locked_by: str | None = None
    locked_at: datetime | None = None
    lease_expires_at: datetime | None = None
    schema_version: str = JOB_SCHEMA_VERSION

    def lease_is_active(self, now: datetime) -> bool:
        """True when this job still holds an unexpired lease."""

        return self.lease_expires_at is not None and _to_utc(self.lease_expires_at) > _to_utc(now)

    def is_claimable(self, now: datetime) -> bool:
        """True when a worker may claim this job at ``now``.

        A ``PENDING`` or ``RETRY_WAIT`` job is claimable once available; a
        ``CLAIMED``/``RUNNING`` job with an expired lease is recoverable by
        another worker (AUT-133).
        """

        if self.status in (JobStatus.PENDING, JobStatus.RETRY_WAIT):
            return _to_utc(self.available_at) <= _to_utc(now)
        if self.status in (JobStatus.CLAIMED, JobStatus.RUNNING):
            return self.lease_expires_at is not None and _to_utc(self.lease_expires_at) <= _to_utc(
                now
            )
        return False

    def to_contract(self) -> dict[str, Any]:
        """Return the versioned public contract for this job."""

        return {
            "schema_version": self.schema_version,
            "job_id": self.id,
            "type": self.type.value,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "priority": self.priority,
            "status": self.status.value,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "available_at": _to_utc(self.available_at).isoformat(),
            "locked_by": self.locked_by,
            "locked_at": None if self.locked_at is None else _to_utc(self.locked_at).isoformat(),
            "lease_expires_at": (
                None
                if self.lease_expires_at is None
                else _to_utc(self.lease_expires_at).isoformat()
            ),
            "correlation_id": self.correlation_id,
            "payload": dict(self.payload),
            "created_at": _to_utc(self.created_at).isoformat(),
            "updated_at": _to_utc(self.updated_at).isoformat(),
        }


@dataclass(frozen=True, slots=True)
class Lock:
    """A durable logical lock with an expiration (RDR-036, AUT-140)."""

    name: str
    owner: str
    acquired_at: datetime
    expires_at: datetime
    correlation_id: str | None = None

    def is_active(self, now: datetime) -> bool:
        return _to_utc(self.expires_at) > _to_utc(now)

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": JOB_SCHEMA_VERSION,
            "name": self.name,
            "owner": self.owner,
            "acquired_at": _to_utc(self.acquired_at).isoformat(),
            "expires_at": _to_utc(self.expires_at).isoformat(),
            "correlation_id": self.correlation_id,
        }


def _require_clean_token(value: object, *, field_name: str, max_length: int = 128) -> str:
    if not isinstance(value, str):
        raise job_input_invalid_error("valor deve ser texto", context={"field": field_name})
    cleaned = sanitize_single_line(value)
    if not cleaned:
        raise job_input_invalid_error("valor não pode ser vazio", context={"field": field_name})
    if len(cleaned) > max_length:
        raise job_input_invalid_error(
            "valor excede o tamanho máximo",
            context={"field": field_name, "max_length": max_length},
        )
    return cleaned


def require_worker_id(worker_id: object) -> str:
    """Validate and normalize a worker identifier."""

    return _require_clean_token(worker_id, field_name="worker_id")


def _require_positive_seconds(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise job_input_invalid_error(
            "valor deve ser um inteiro de segundos maior que zero",
            context={"field": field_name},
        )
    return value


def require_lease_seconds(value: object, *, field_name: str = "lease_seconds") -> int:
    """Validate a positive lease/ttl duration in seconds."""

    return _require_positive_seconds(value, field_name=field_name)


def require_correlation_id(correlation_id: object) -> str:
    """Validate a non-empty Correlation ID (AUT-040)."""

    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise job_input_invalid_error(
            "correlation_id é obrigatório", context={"field": "correlation_id"}
        )
    return correlation_id.strip()


def _coerce_job_type(job_type: object) -> JobType:
    if isinstance(job_type, JobType):
        return job_type
    try:
        return JobType(str(job_type))
    except ValueError as exc:
        raise job_input_invalid_error(
            "type de job inválido",
            context={"field": "type", "allowed": [item.value for item in JobType]},
        ) from exc


def validate_job_payload(payload: object) -> dict[str, Any]:
    """Validate a Job payload: a JSON object free of sensitive fields.

    Shared by :func:`create_job` and the Scheduler, so a schedule can never
    persist a payload that the Job queue would later reject (RAD-WF-006).
    """

    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise job_input_invalid_error(
            "payload deve ser um objeto JSON", context={"field": "payload"}
        )
    document = dict(payload)
    try:
        json.dumps(document, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise job_input_invalid_error(
            "payload deve ser serializável em JSON", context={"field": "payload"}
        ) from exc
    hits = find_sensitive_fields(document)
    if hits:
        raise job_input_invalid_error(
            "payload de job contém campos sensíveis",
            context={"field": "payload", "fields": list(hits)},
        )
    return document


def create_job(
    *,
    job_type: object,
    correlation_id: object,
    now: datetime,
    payload: object = None,
    priority: object = 0,
    entity_type: str | None = None,
    entity_id: str | None = None,
    available_at: datetime | None = None,
    max_attempts: object = DEFAULT_MAX_ATTEMPTS,
    schema_version: object = JOB_SCHEMA_VERSION,
    id_factory: IdFactory = default_id_factory,
) -> Job:
    """Build and validate a ``PENDING`` Job (RDR-034).

    Rejects an unsupported ``schema_version``, an unknown/domain ``type``, a
    non-integer priority/attempt budget, a non-JSON or sensitive payload and a
    half-specified entity reference (``RAD-WF-006``). The domain never invents a
    Job state from an external/domain state (AUT-118).
    """

    if str(schema_version) != JOB_SCHEMA_VERSION:
        raise job_input_invalid_error(
            "schema_version de job não suportada",
            context={"field": "schema_version", "supported": JOB_SCHEMA_VERSION},
        )
    resolved_type = _coerce_job_type(job_type)
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise job_input_invalid_error("priority deve ser um inteiro", context={"field": "priority"})
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise job_input_invalid_error(
            "max_attempts deve ser um inteiro maior ou igual a 1",
            context={"field": "max_attempts"},
        )
    if isinstance(available_at, bool) or (
        available_at is not None and not isinstance(available_at, datetime)
    ):
        raise job_input_invalid_error(
            "available_at deve ser um timestamp", context={"field": "available_at"}
        )
    if (entity_type is None) != (entity_id is None):
        raise job_input_invalid_error(
            "entity_type e entity_id devem ser informados juntos",
            context={"field": "entity"},
        )
    resolved_entity_type = (
        None
        if entity_type is None
        else _require_clean_token(entity_type, field_name="entity_type", max_length=32)
    )
    resolved_entity_id = (
        None
        if entity_id is None
        else _require_clean_token(entity_id, field_name="entity_id", max_length=64)
    )

    reference = _to_utc(now)
    scheduled_at = reference if available_at is None else _to_utc(available_at)
    return Job(
        id=id_factory("job"),
        type=resolved_type,
        status=JobStatus.PENDING,
        priority=priority,
        attempts=0,
        max_attempts=max_attempts,
        available_at=scheduled_at,
        entity_type=resolved_entity_type,
        entity_id=resolved_entity_id,
        correlation_id=require_correlation_id(correlation_id),
        payload=validate_job_payload(payload),
        created_at=reference,
        updated_at=reference,
    )


def start_job(job: Job, *, worker_id: str, now: datetime) -> Job:
    """Return the same job transitioned to ``RUNNING`` for the lease owner.

    Idempotent for the owner while the lease is active; a worker without a valid
    lease (wrong owner or expired) is rejected with ``RAD-WF-009``.
    """

    if job.status is JobStatus.RUNNING and job.locked_by == worker_id and job.lease_is_active(now):
        return job
    if job.status is JobStatus.SUCCESS:
        raise job_state_invalid_error(job.id, current=job.status, expected="CLAIMED")
    if job.status is not JobStatus.CLAIMED:
        raise job_state_invalid_error(job.id, current=job.status, expected="CLAIMED")
    if job.locked_by != worker_id or not job.lease_is_active(now):
        raise job_lease_not_held_error(
            job.id, worker_id=worker_id, reason="lease_expired_or_not_owner", holder=job.locked_by
        )
    return replace(job, status=JobStatus.RUNNING, updated_at=_to_utc(now))


def complete_job(job: Job, *, worker_id: str, now: datetime) -> Job:
    """Return the same job transitioned to ``SUCCESS`` for the lease owner.

    Idempotent for the owner once ``SUCCESS``; another worker can never confirm an
    execution it does not own (`RAD-WF-009`).
    """

    if job.status is JobStatus.SUCCESS:
        if job.locked_by == worker_id:
            return job
        raise job_lease_not_held_error(
            job.id, worker_id=worker_id, reason="completed_by_other", holder=job.locked_by
        )
    if job.status not in (JobStatus.CLAIMED, JobStatus.RUNNING):
        raise job_state_invalid_error(job.id, current=job.status, expected="CLAIMED or RUNNING")
    if job.locked_by != worker_id or not job.lease_is_active(now):
        raise job_lease_not_held_error(
            job.id, worker_id=worker_id, reason="lease_expired_or_not_owner", holder=job.locked_by
        )
    return replace(
        job,
        status=JobStatus.SUCCESS,
        lease_expires_at=None,
        updated_at=_to_utc(now),
    )


__all__ = [
    "AUDIT_SOURCE_JOB",
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_MAX_ATTEMPTS",
    "ENTITY_JOB",
    "JOB_INPUT_INVALID",
    "JOB_LEASE_NOT_HELD",
    "JOB_NOT_CLAIMABLE",
    "JOB_NOT_FOUND",
    "JOB_SCHEMA_VERSION",
    "JOB_STATE_INVALID",
    "LOCK_UNAVAILABLE",
    "IdFactory",
    "Job",
    "JobError",
    "JobStatus",
    "JobType",
    "Lock",
    "complete_job",
    "create_job",
    "job_input_invalid_error",
    "job_lease_not_held_error",
    "job_not_claimable_error",
    "job_not_found_error",
    "job_state_invalid_error",
    "lock_unavailable_error",
    "require_correlation_id",
    "require_lease_seconds",
    "require_worker_id",
    "start_job",
    "validate_job_payload",
]
