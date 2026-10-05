from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from radar.domain.config import CONFIG_INVALID, CONFIG_UNREADABLE, ConfigInvalidError
from radar.infrastructure.config import ConfigLoader

pytestmark = pytest.mark.unit


def _write(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_defaults_without_config_file(tmp_path: Path) -> None:
    config = ConfigLoader.from_env(env={}, cwd=tmp_path).load()
    assert config.schema_version == "1.0"
    assert config.environment == "development"
    assert config.automation_mode == "SHADOW"
    assert config.log_level == "INFO"
    assert config.timezone == "America/Maceio"
    assert config.source == "defaults"
    assert config.database_url.endswith("radar.db")
    assert len(config.config_hash) == 64


def test_env_overrides_file(tmp_path: Path) -> None:
    path = _write(tmp_path / "radar.json", {"log_level": "WARNING", "environment": "staging"})
    config = ConfigLoader.from_env(
        env={"RADAR_LOG_LEVEL": "DEBUG"}, config_path=path, cwd=tmp_path
    ).load()
    assert config.log_level == "DEBUG"
    assert config.environment == "staging"
    assert str(path) in config.source
    assert "env" in config.source


def test_hash_is_stable_and_changes_with_values(tmp_path: Path) -> None:
    first = ConfigLoader.from_env(env={}, cwd=tmp_path).load()
    second = ConfigLoader.from_env(env={}, cwd=tmp_path).load()
    assert first.config_hash == second.config_hash

    changed = ConfigLoader.from_env(env={"RADAR_AUTOMATION_MODE": "ASSISTED"}, cwd=tmp_path).load()
    assert changed.config_hash != first.config_hash


@pytest.mark.parametrize(
    "data",
    [
        {"log_level": "LOUD"},
        {"timezone": "Nowhere/Invalid"},
        {"automation_mode": "TURBO"},
        {"environment": "Not Valid!"},
        {"database_url": "not a url"},
        {"unknown_key": 1},
        {"secrets": {"bad name!": "RADAR_SECRET_X"}},
    ],
)
def test_invalid_config_is_actionable(tmp_path: Path, data: dict[str, Any]) -> None:
    path = _write(tmp_path / "radar.json", data)
    with pytest.raises(ConfigInvalidError) as excinfo:
        ConfigLoader.from_env(env={}, config_path=path, cwd=tmp_path).load()
    error = excinfo.value.error
    assert error.code == CONFIG_INVALID
    assert error.retryable is False
    assert error.action
    assert str(path) in error.context.get("path", "")


def test_invalid_config_does_not_echo_input_values(tmp_path: Path) -> None:
    path = _write(tmp_path / "radar.json", {"environment": "SUPER-SECRET"})
    with pytest.raises(ConfigInvalidError) as excinfo:
        ConfigLoader.from_env(env={}, config_path=path, cwd=tmp_path).load()
    assert "SUPER-SECRET" not in excinfo.value.error.message


def test_missing_explicit_config_file_is_unreadable(tmp_path: Path) -> None:
    with pytest.raises(ConfigInvalidError) as excinfo:
        ConfigLoader.from_env(env={}, config_path=tmp_path / "absent.json", cwd=tmp_path).load()
    assert excinfo.value.error.code == CONFIG_UNREADABLE
    assert excinfo.value.error.retryable is False


def test_malformed_json_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "radar.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ConfigInvalidError) as excinfo:
        ConfigLoader.from_env(env={}, config_path=path, cwd=tmp_path).load()
    assert excinfo.value.error.code == CONFIG_INVALID


def test_config_contract_exposes_secret_references_only(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "radar.json",
        {"secrets": {"telegram_bot_token": "RADAR_SECRET_TELEGRAM_BOT_TOKEN"}},
    )
    config = ConfigLoader.from_env(
        env={"RADAR_SECRET_TELEGRAM_BOT_TOKEN": "should-not-appear"},
        config_path=path,
        cwd=tmp_path,
    ).load()
    contract = config.to_contract()
    assert contract["secret_refs"] == ["telegram_bot_token"]
    assert "should-not-appear" not in json.dumps(contract)
