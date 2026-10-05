from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from radar.cli import main as cli

pytestmark = pytest.mark.contract


def _payload(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["version"]) == 0
    payload = _payload(capsys)
    assert payload["schema_version"] == "1.0"
    assert payload["app_version"]
    assert payload["correlation_id"]


def test_status_healthy(
    migrated_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RADAR_DATABASE_URL", migrated_database_url)
    assert cli.main(["status"]) == 0
    payload = _payload(capsys)
    assert payload["status"] == "HEALTHY"
    assert payload["schema_version"] == "1.0"


def test_status_unavailable_database(
    unavailable_database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RADAR_DATABASE_URL", unavailable_database_url)
    assert cli.main(["status"]) == 1
    payload = _payload(capsys)
    assert payload["status"] == "UNHEALTHY"
    codes = [check["error"]["code"] for check in payload["checks"] if "error" in check]
    assert "RAD-DB-003" in codes


def test_migrate_then_status_is_healthy(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RADAR_DATABASE_URL", database_url)
    assert cli.main(["migrate"]) == 0
    assert _payload(capsys)["status"] == "HEALTHY"
    assert cli.main(["status"]) == 0
    assert _payload(capsys)["status"] == "HEALTHY"


def test_migrate_creates_missing_data_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "nested" / "data"
    monkeypatch.delenv("RADAR_DATABASE_URL", raising=False)
    monkeypatch.setenv("RADAR_DATA_DIR", str(data_dir))
    assert cli.main(["migrate"]) == 0
    capsys.readouterr()
    assert (data_dir / "radar.db").exists()
    assert cli.main(["status"]) == 0
    assert _payload(capsys)["status"] == "HEALTHY"


def test_migrate_failure_is_blocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = tmp_path / "dir-as-database"
    directory.mkdir()
    monkeypatch.setenv("RADAR_DATABASE_URL", f"sqlite+pysqlite:///{directory.as_posix()}")
    assert cli.main(["migrate"]) == 1
    payload = _payload(capsys)
    assert payload["status"] == "UNHEALTHY"
    assert payload["error"]["code"] == "RAD-DB-002"
    assert payload["error"]["retryable"] is False
