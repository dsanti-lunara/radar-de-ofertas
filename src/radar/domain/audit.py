"""Append-only audit/domain events (RDR-021, AUT-141).

Audit events record what the system did, when and under which Correlation ID.
They are persisted and kept separate from application logs (AUT-216) and never
carry secrets or unnecessary personal data (AUT-299).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

AUDIT_SCHEMA_VERSION = "1.0"

#: Event type recorded when a manual capture is accepted.
CAPTURE_RECEIVED = "CAPTURE_RECEIVED"

#: Event type recorded when an immutable Evaluation is persisted (RDR-016).
EVALUATION_RECORDED = "EVALUATION_RECORDED"

#: Event type recorded when a purchase source decision is persisted (RDR-031).
PURCHASE_SOURCE_DECIDED = "PURCHASE_SOURCE_DECIDED"

#: Event type recorded when a repost decision is persisted (RDR-033).
REPOST_DECIDED = "REPOST_DECIDED"

#: Event types recorded by the Job queue (RDR-034..036).
JOB_ENQUEUED = "JOB_ENQUEUED"
JOB_CLAIMED = "JOB_CLAIMED"
JOB_STARTED = "JOB_STARTED"
JOB_SUCCEEDED = "JOB_SUCCEEDED"
#: Event types recorded by the retry/Dead Job flow (RDR-037/RDR-038, RDR-040).
JOB_RETRY_SCHEDULED = "JOB_RETRY_SCHEDULED"
JOB_DEAD = "JOB_DEAD"
JOB_FAILED = "JOB_FAILED"
HUMAN_ACTION_CREATED = "HUMAN_ACTION_CREATED"
LOCK_ACQUIRED = "LOCK_ACQUIRED"
LOCK_RELEASED = "LOCK_RELEASED"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """An append-only, correlation-tagged record of a relevant action."""

    id: str
    event_type: str
    entity_type: str
    entity_id: str
    source: str
    correlation_id: str
    recorded_at: datetime
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        return {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "id": self.id,
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "source": self.source,
            "correlation_id": self.correlation_id,
            "recorded_at": self.recorded_at.isoformat(),
            "payload": dict(self.payload),
        }
