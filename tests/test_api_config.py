from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from radar.api.app import create_app
from radar.domain.config import ConfigInvalidError
from radar.infrastructure.config import ConfigLoader

pytestmark = pytest.mark.contract


def test_invalid_configuration_blocks_app_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "radar.json"
    path.write_text(json.dumps({"log_level": "LOUD"}), encoding="utf-8")
    monkeypatch.setenv("RADAR_CONFIG_FILE", str(path))

    with pytest.raises(ConfigInvalidError):
        create_app()


def test_config_endpoint_is_sanitized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "radar.json"
    path.write_text(
        json.dumps({"secrets": {"telegram_bot_token": "RADAR_SECRET_TELEGRAM_BOT_TOKEN"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RADAR_CONFIG_FILE", str(path))
    monkeypatch.setenv("RADAR_SECRET_TELEGRAM_BOT_TOKEN", "fake-secret-value")
    config = ConfigLoader.from_env().load()

    response = TestClient(create_app(config=config)).get(
        "/config", headers={"X-Correlation-ID": "cid-config"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "VALID"
    assert body["schema_version"] == "1.0"
    assert body["correlation_id"] == "cid-config"
    assert response.headers["x-correlation-id"] == "cid-config"
    assert body["config_hash"]
    assert body["secret_refs"] == ["telegram_bot_token"]
    assert "fake-secret-value" not in json.dumps(body)
