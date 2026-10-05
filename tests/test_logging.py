from __future__ import annotations

import io
import json
import logging

import pytest

from radar.domain.correlation import bind_correlation_id
from radar.domain.secrets import SECRET_MASK
from radar.infrastructure.logging import JsonLogFormatter, SecretRedactor, configure_logging

pytestmark = pytest.mark.unit

FAKE_SECRET = "fake-super-secret"


def _record(message: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("radar.cli", logging.INFO, __file__, 1, message, args, None)


def test_formatter_includes_correlation_id_and_message() -> None:
    bind_correlation_id("cid-unit")
    payload = json.loads(JsonLogFormatter().format(_record("hello %s", "world")))
    assert payload["correlation_id"] == "cid-unit"
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "radar.cli"


def test_formatter_redacts_registered_secret_values() -> None:
    redactor = SecretRedactor([FAKE_SECRET])
    record = _record("token=%s", FAKE_SECRET)
    record.context_value = {"nested": FAKE_SECRET}
    payload = json.loads(JsonLogFormatter(redactor).format(record))
    assert FAKE_SECRET not in payload["message"]
    assert SECRET_MASK in payload["message"]
    assert FAKE_SECRET not in json.dumps(payload)
    assert payload["context_value"] == {"nested": SECRET_MASK}


def test_formatter_masks_sensitive_field_names() -> None:
    record = _record("ok")
    record.password = "some-password"
    record.authorization = "Bearer abc"
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["password"] == SECRET_MASK
    assert payload["authorization"] == SECRET_MASK


def test_configure_logging_emits_redacted_json() -> None:
    stream = io.StringIO()
    configure_logging("DEBUG", redactor=SecretRedactor([FAKE_SECRET]), stream=stream)
    logging.getLogger("radar.test").info("value=%s", FAKE_SECRET)
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert lines
    payload = json.loads(lines[-1])
    assert FAKE_SECRET not in lines[-1]
    assert SECRET_MASK in payload["message"]


def test_reconfiguration_does_not_duplicate_handlers() -> None:
    stream = io.StringIO()
    configure_logging("INFO", stream=stream)
    configure_logging("INFO", stream=stream)
    logger = logging.getLogger("radar")
    assert len(logger.handlers) == 1
    assert logger.propagate is False
