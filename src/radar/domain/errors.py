"""Structured, actionable error contract shared across the public boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RadarError:
    """Actionable error as described by the Error Catalog.

    ``code`` follows the ``RAD-<AREA>-<NNN>`` convention, ``retryable`` states
    whether an automatic retry is safe and ``action`` tells the operator what to
    do next. ``context`` must never carry secrets, cookies or tokens.
    """

    code: str
    message: str
    retryable: bool = False
    action: str | None = None
    context: Mapping[str, Any] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.action:
            payload["action"] = self.action
        if self.context:
            payload["context"] = dict(self.context)
        return payload
