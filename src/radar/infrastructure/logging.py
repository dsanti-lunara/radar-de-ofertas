"""Structured JSON logging with secret redaction (RDR-008).

Application logs are structured JSON (AUT-215) and stay separate from audit
events (AUT-216). Sensitive values never reach the stream: registered secret
values and known-sensitive field names are masked before formatting
(AUT-210). ``correlation_id`` is attached from the domain context so a log line
can be traced back to the pipeline execution (AUT-040).
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any, TextIO

from radar.domain.correlation import current_correlation_id
from radar.domain.secrets import SECRET_MASK

#: Field names that must always be masked regardless of their value.
SENSITIVE_FIELDS: frozenset[str] = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "cookies",
        "credential",
        "credentials",
        "id_token",
        "oauth_token",
        "pairing_secret",
        "password",
        "refresh_token",
        "secret",
        "token",
    }
)

_STANDARD_RECORD_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)


class SecretRedactor:
    """Replace registered secret values with :data:`~radar.domain.secrets.SECRET_MASK`."""

    def __init__(self, values: Iterable[str] | None = None) -> None:
        self._values: set[str] = {value for value in (values or ()) if value}

    def register(self, value: str | None) -> None:
        if value:
            self._values.add(value)

    @property
    def registered(self) -> frozenset[str]:
        return frozenset(self._values)

    def redact(self, text: str) -> str:
        redacted = text
        for value in self._values:
            if value in redacted:
                redacted = redacted.replace(value, SECRET_MASK)
        return redacted

    def redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, Mapping):
            return {key: self.redact_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.redact_value(item) for item in value]
        return value


class JsonLogFormatter(logging.Formatter):
    """Render a log record as a single JSON object."""

    def __init__(self, redactor: SecretRedactor | None = None) -> None:
        super().__init__()
        self._redactor = redactor or SecretRedactor()

    def format(self, record: logging.LogRecord) -> str:
        redactor = self._redactor
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redactor.redact(record.getMessage()),
        }

        correlation_id = current_correlation_id()
        if correlation_id:
            payload["correlation_id"] = correlation_id

        if record.exc_info:
            payload["exception"] = redactor.redact(self.formatException(record.exc_info))

        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_KEYS or key.startswith("_"):
                continue
            if key in SENSITIVE_FIELDS:
                payload[key] = SECRET_MASK
                continue
            payload[key] = redactor.redact_value(value)

        return json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)


def configure_logging(
    level: str = "INFO",
    *,
    redactor: SecretRedactor | None = None,
    stream: TextIO | None = None,
) -> SecretRedactor:
    """Configure the ``radar`` logger with a JSON handler.

    Returns the redactor in use so secret providers can register values with the
    same instance. Re-configuration replaces existing handlers and does not
    propagate to the root logger, keeping uvicorn/test output untouched.
    """

    resolved_redactor = redactor or SecretRedactor()
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonLogFormatter(resolved_redactor))

    logger = logging.getLogger("radar")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return resolved_redactor


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced application logger."""

    return logging.getLogger(f"radar.{name}")
