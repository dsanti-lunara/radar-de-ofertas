"""Correlation ID helpers (AUT-040).

The canonical implementation lives in :mod:`radar.domain.correlation`; this
module keeps the historical application-layer import path stable.
"""

from __future__ import annotations

from radar.domain.correlation import (
    bind_correlation_id,
    current_correlation_id,
    new_correlation_id,
)

__all__ = ["bind_correlation_id", "current_correlation_id", "new_correlation_id"]
