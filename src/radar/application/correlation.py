"""Correlation ID helpers (AUT-040)."""

from __future__ import annotations

import uuid


def new_correlation_id() -> str:
    """Return a fresh opaque correlation ID without any personal data."""

    return uuid.uuid4().hex
