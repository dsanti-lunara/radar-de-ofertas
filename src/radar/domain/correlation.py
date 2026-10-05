"""Correlation ID context (AUT-040).

Every pipeline execution keeps the same ``correlation_id`` from discovery to
publication (``docs/04_DATA_CONTRACTS.md``). The value is stored in a
:class:`~contextvars.ContextVar` so infrastructure logging can attach it to
every structured record without threading it manually.

The module is framework-free and lives in the domain layer so infrastructure
may depend on it without inverting the dependency direction.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_CORRELATION_ID: ContextVar[str | None] = ContextVar("radar_correlation_id", default=None)


def new_correlation_id() -> str:
    """Return a fresh opaque correlation ID without any personal data."""

    return uuid.uuid4().hex


def bind_correlation_id(correlation_id: str | None = None) -> str:
    """Bind a correlation ID to the current context and return it.

    A blank/missing value produces a new opaque ID, so callers never propagate
    an empty identifier.
    """

    value = correlation_id or new_correlation_id()
    _CORRELATION_ID.set(value)
    return value


def current_correlation_id() -> str | None:
    """Return the correlation ID bound to the current context, if any."""

    return _CORRELATION_ID.get()
