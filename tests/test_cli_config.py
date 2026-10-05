from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from radar.cli import main as cli

pytestmark = pytest.mark.contract

FAKE_SECRET = "fake-super-secret-value"


def _write_config(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "radar.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _json_lines(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_config_reports_invalid_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_config(tmp_path, {"log_level": "LOUD"})
    monkeypatch.setenv("RADAR_CONFIG_FILE", str(path))

    assert cli.main(["config"]) == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["status"] == "INVALID"
    assert payload["schema_version"] == "1.0"
    assert payload["error"]["code"] == "RAD-CFG-001"
    assert payload["error"]["retryable"] is False
    assert payload["error"]["action"]
    assert payload["correlation_id"]

    log_records = _json_lines(captured.err)
    assert any(
        record.get("correlation_id") == payload["correlation_id"]
        and record.get("error_code") == "RAD-CFG-001"
        for record in log_records
    )


def test_invalid_configuration_blocks_other_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_config(tmp_path, {"timezone": "Nowhere/Invalid"})
    monkeypatch.setenv("RADAR_CONFIG_FILE", str(path))

    assert cli.main(["status"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "RAD-CFG-001"


def test_config_reports_secret_presence_without_leaking_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_config(
        tmp_path, {"secrets": {"telegram_bot_token": "RADAR_SECRET_TELEGRAM_BOT_TOKEN"}}
    )
    monkeypatch.setenv("RADAR_CONFIG_FILE", str(path))
    monkeypatch.setenv("RADAR_SECRET_TELEGRAM_BOT_TOKEN", FAKE_SECRET)

    assert cli.main(["config"]) == 0
    captured = capsys.readouterr()
    assert FAKE_SECRET not in captured.out
    assert FAKE_SECRET not in captured.err

    payload = json.loads(captured.out)
    assert payload["status"] == "VALID"
    assert payload["correlation_id"]
    assert payload["config"]["schema_version"] == "1.0"
    assert payload["config"]["config_hash"]
    assert payload["config"]["secret_refs"] == ["telegram_bot_token"]
    assert payload["secrets"]["status"]["telegram_bot_token"] == "present"
    assert FAKE_SECRET not in json.dumps(payload)


def test_config_reports_missing_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_config(
        tmp_path, {"secrets": {"telegram_bot_token": "RADAR_SECRET_TELEGRAM_BOT_TOKEN"}}
    )
    monkeypatch.setenv("RADAR_CONFIG_FILE", str(path))
    monkeypatch.delenv("RADAR_SECRET_TELEGRAM_BOT_TOKEN", raising=False)

    assert cli.main(["config"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["secrets"]["status"]["telegram_bot_token"] == "missing"


def test_config_error_never_echoes_environment_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_config(tmp_path, {"automation_mode": "TURBO"})
    monkeypatch.setenv("RADAR_CONFIG_FILE", str(path))
    monkeypatch.setenv("RADAR_SECRET_TELEGRAM_BOT_TOKEN", FAKE_SECRET)

    assert cli.main(["config"]) == 1
    captured = capsys.readouterr()
    assert FAKE_SECRET not in captured.out
    assert FAKE_SECRET not in captured.err
