"""Validated operational configuration contract (RDR-004).

Configuration is operational behaviour, kept separate from the Knowledge Pack
(AUT-205). Values are validated by schema (AUT-206), versioned and hashed
(AUT-207) and never carry secret *values*: secrets are referenced by name and
resolved through the :class:`~radar.domain.secrets.SecretsProvider` (AUT-210).

The model is framework-free so the domain does not depend on Pydantic.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from radar.domain.errors import RadarException

CONFIG_SCHEMA_VERSION = "1.0"

#: Configuration error codes (see ``docs/ERROR_CATALOG.md``).
CONFIG_INVALID = "RAD-CFG-001"
CONFIG_UNREADABLE = "RAD-CFG-002"
SECRET_UNAVAILABLE = "RAD-CFG-003"
SECRET_ACCESS_DENIED = "RAD-CFG-004"

VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
VALID_AUTOMATION_MODES = frozenset({"MANUAL", "SHADOW", "ASSISTED", "AUTO"})


class ConfigInvalidError(RadarException):
    """Raised when configuration fails schema validation or cannot be read."""


@dataclass(frozen=True, slots=True)
class RadarConfig:
    """Effective, validated configuration for one Radar node."""

    environment: str
    timezone: str
    log_level: str
    automation_mode: str
    data_dir: str
    database_url: str
    config_hash: str
    source: str = "defaults"
    schema_version: str = CONFIG_SCHEMA_VERSION
    secret_refs: Mapping[str, str] = field(default_factory=dict)

    def to_contract(self) -> dict[str, Any]:
        """Return a sanitized config contract.

        Secret references are exposed by *logical name only*; no secret value,
        cookie or token is present in this payload (AUT-210, AUT-299).
        """

        return {
            "schema_version": self.schema_version,
            "environment": self.environment,
            "timezone": self.timezone,
            "log_level": self.log_level,
            "automation_mode": self.automation_mode,
            "data_dir": self.data_dir,
            "database_url": self.database_url,
            "config_hash": self.config_hash,
            "source": self.source,
            "secret_refs": sorted(self.secret_refs),
        }
