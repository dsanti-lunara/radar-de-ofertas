from __future__ import annotations

import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from radar.infrastructure.migrations import current_revision, head_revision, upgrade_to_head

pytestmark = pytest.mark.integration


def test_empty_database_migrates_to_head(
    migrated_engine: Engine, migrated_database_url: str
) -> None:
    assert head_revision(migrated_database_url) == "0001_initial"
    assert current_revision(migrated_engine) == head_revision(migrated_database_url)


def test_wal_and_foreign_keys_active(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert str(journal_mode).lower() == "wal"
    assert foreign_keys == 1


def test_foreign_keys_are_enforced(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE child ("
            "id INTEGER PRIMARY KEY, "
            "parent_id INTEGER NOT NULL REFERENCES parent(id)"
            ")"
        )
    with pytest.raises(IntegrityError), migrated_engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO child (id, parent_id) VALUES (1, 999)")


def test_migration_is_idempotent(migrated_engine: Engine, migrated_database_url: str) -> None:
    upgrade_to_head(migrated_database_url)
    assert current_revision(migrated_engine) == head_revision(migrated_database_url)


def test_bootstrap_table_records_schema_version(migrated_engine: Engine) -> None:
    assert "schema_version" in inspect(migrated_engine).get_table_names()
    with migrated_engine.connect() as connection:
        version = connection.exec_driver_sql(
            "SELECT version FROM schema_version WHERE component = 'db_schema'"
        ).scalar()
    assert version == "0001_initial"
