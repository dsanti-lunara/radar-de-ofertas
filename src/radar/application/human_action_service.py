"""HumanAction queries through the public boundary (RDR-040).

The retry/Dead Job flow creates HumanActions; this read service exposes them so
the pending intervention, its impact and the next steps are observable without
reading SQL. Resolution/mutation belongs to the Human Actions center (RDR-063).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from radar.domain.human_action import (
    HumanAction,
    human_action_not_found_error,
)


class HumanActionStore(Protocol):
    """Read port for persisted HumanAction records."""

    def get(self, human_action_id: str) -> HumanAction | None: ...

    def list(self, *, status: str | None = None) -> list[HumanAction]: ...


@dataclass(slots=True)
class HumanActionService:
    """Query persisted HumanActions."""

    repository: HumanActionStore

    def get(self, human_action_id: str) -> HumanAction:
        """Return a persisted HumanAction, raising a structured not-found error."""

        action = self.repository.get(human_action_id)
        if action is None:
            raise human_action_not_found_error(human_action_id)
        return action

    def list(self, *, status: str | None = None) -> list[HumanAction]:
        """Return HumanActions, optionally filtered by status."""

        return self.repository.list(status=status)


__all__ = [
    "HumanActionService",
    "HumanActionStore",
]
