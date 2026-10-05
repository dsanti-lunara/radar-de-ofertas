"""Shared fixtures for the Radar Engine test suite.

Integration tests use a real temporary SQLite file (QA Matrix: ``Database``),
never an in-memory shortcut, so WAL/FK behavior is representative.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from radar.infrastructure.database import create_database_engine
from radar.infrastructure.migrations import upgrade_to_head


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "radar.db"


@pytest.fixture
def database_url(database_path: Path) -> str:
    return f"sqlite+pysqlite:///{database_path.as_posix()}"


@pytest.fixture
def migrated_database_url(database_url: str) -> str:
    upgrade_to_head(database_url)
    return database_url


@pytest.fixture
def migrated_engine(migrated_database_url: str) -> Iterator[Engine]:
    engine = create_database_engine(migrated_database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def unavailable_database_url(tmp_path: Path) -> str:
    directory = tmp_path / "not-a-database"
    directory.mkdir()
    return f"sqlite+pysqlite:///{directory.as_posix()}"
