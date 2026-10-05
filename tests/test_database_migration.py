from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from radar.infrastructure.database import (
    create_database_engine,
    ensure_sqlite_database_directory,
)
from radar.infrastructure.migrations import (
    current_revision,
    head_revision,
    make_alembic_config,
    upgrade_to_head,
)

pytestmark = pytest.mark.integration


def test_empty_database_migrates_to_head(
    migrated_engine: Engine, migrated_database_url: str
) -> None:
    assert head_revision(migrated_database_url) == "0002_manual_capture"
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


def test_bootstrap_table_records_schema_version(
    migrated_engine: Engine, migrated_database_url: str
) -> None:
    assert "schema_version" in inspect(migrated_engine).get_table_names()
    with migrated_engine.connect() as connection:
        version = connection.exec_driver_sql(
            "SELECT version FROM schema_version WHERE component = 'db_schema'"
        ).scalar()
    assert version == head_revision(migrated_database_url)


def test_migration_from_previous_revision_to_head(database_url: str) -> None:
    ensure_sqlite_database_directory(database_url)
    config = make_alembic_config(database_url)
    command.upgrade(config, "0001_initial")

    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0001_initial"
        assert "candidate" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    upgrade_to_head(database_url)
    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0002_manual_capture"
        assert "candidate" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_downgrade_reverts_capture_schema(database_url: str) -> None:
    upgrade_to_head(database_url)
    config = make_alembic_config(database_url)
    command.downgrade(config, "0001_initial")

    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0001_initial"
        tables = set(inspect(engine).get_table_names())
        assert "candidate" not in tables
        assert "marketplace_product" not in tables
        with engine.connect() as connection:
            version = connection.exec_driver_sql(
                "SELECT version FROM schema_version WHERE component = 'db_schema'"
            ).scalar()
        assert version == "0001_initial"
    finally:
        engine.dispose()
