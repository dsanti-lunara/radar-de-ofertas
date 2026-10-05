"""Minimal operational settings.

This is the small bootstrap configuration the health boundary needs. The full
configuration loader is a separate ticket (RDR-004); do not grow this module
into that system.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from radar import __version__

DEFAULT_LOG_LEVEL = "INFO"


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    app_version: str = __version__
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = os.environ if env is None else env
        data_dir = Path(source.get("RADAR_DATA_DIR") or Path.cwd() / "data")
        database_url = source.get("RADAR_DATABASE_URL") or (
            f"sqlite+pysqlite:///{(data_dir / 'radar.db').as_posix()}"
        )
        return cls(
            database_url=database_url,
            log_level=source.get("RADAR_LOG_LEVEL", DEFAULT_LOG_LEVEL),
        )
