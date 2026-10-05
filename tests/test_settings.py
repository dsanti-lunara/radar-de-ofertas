from __future__ import annotations

from pathlib import Path

import pytest

from radar.infrastructure.settings import Settings

pytestmark = pytest.mark.unit


def test_defaults_to_local_data_dir(tmp_path: Path) -> None:
    settings = Settings.from_env({"RADAR_DATA_DIR": str(tmp_path)})
    expected = f"sqlite+pysqlite:///{(tmp_path / 'radar.db').as_posix()}"
    assert settings.database_url == expected
    assert settings.app_version
    assert settings.log_level == "INFO"


def test_explicit_database_url_wins() -> None:
    settings = Settings.from_env(
        {
            "RADAR_DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "RADAR_DATA_DIR": "/tmp/ignored",
        }
    )
    assert settings.database_url == "sqlite+pysqlite:///:memory:"


def test_log_level_override() -> None:
    assert Settings.from_env({"RADAR_LOG_LEVEL": "DEBUG"}).log_level == "DEBUG"
