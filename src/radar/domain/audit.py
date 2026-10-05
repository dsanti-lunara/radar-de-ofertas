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
