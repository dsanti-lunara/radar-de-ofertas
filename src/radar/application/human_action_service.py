"""HumanAction queries through the public boundary (RDR-040).

The retry/Dead Job flow creates HumanActions; this read service exposes them so
the pending intervention, its impact and the next steps are observable without
reading SQL. Resolution/mutation belongs to the Human Actions center (RDR-063).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from radar.domain.human_action import (
    HumanAction,
    human_action_not_found_error,
    resolve_human_action,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class HumanActionStore(Protocol):
    """Read/resolution port for persisted HumanAction records."""

    def get(self, human_action_id: str) -> HumanAction | None: ...

    def list(self, *, status: str | None = None) -> list[HumanAction]: ...

    def resolve(
        self, human_action_id: str, *, now: datetime, correlation_id: str
    ) -> tuple[HumanAction, bool] | None: ...


@dataclass(slots=True)
class HumanActionService:
    """Query and resolve persisted HumanActions (RDR-040, RDR-063)."""

    repository: HumanActionStore
    clock: Callable[[], datetime] = _utcnow

    def get(self, human_action_id: str) -> HumanAction:
        """Return a persisted HumanAction, raising a structured not-found error."""

        action = self.repository.get(human_action_id)
        if action is None:
            raise human_action_not_found_error(human_action_id)
        return action

    def list(self, *, status: str | None = None) -> list[HumanAction]:
        """Return HumanActions, optionally filtered by status."""

        return self.repository.list(status=status)

    def resolve(
        self, human_action_id: str, *, reason: object, correlation_id: str
    ) -> tuple[HumanAction, bool]:
        """Resolve an operator-acknowledged intervention, auditing it.

        A not-found action raises ``RAD-WF-011``; a delegated/guarded kind
        raises ``RAD-WF-020`` before any write, so the center can never bypass
        the Candidate review or the evidence-backed Publication resolution.
        """

        action = self.get(human_action_id)
        if action.status.value == "RESOLVED":
            return action, False
        # Validate the transition in the framework-free domain before writing;
        # a delegated/guarded kind fails closed with RAD-WF-020 here.
        now = self.clock()
        resolve_human_action(action, reason=reason, now=now)
        resolved = self.repository.resolve(human_action_id, now=now, correlation_id=correlation_id)
        if resolved is None:  # pragma: no cover - guarded by the get above
            raise human_action_not_found_error(human_action_id)
        return resolved


__all__ = [
    "HumanActionService",
    "HumanActionStore",
]
