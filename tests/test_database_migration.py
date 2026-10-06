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
    assert head_revision(migrated_database_url) == "0011_operations_control"
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
        assert current_revision(engine) == "0011_operations_control"
        tables = set(inspect(engine).get_table_names())
        assert "candidate" in tables
        assert "price_observation" in tables
        assert "evaluation" in tables
        assert "purchase_source_decision" in tables
        assert "repost_decision" in tables
        assert "job" in tables
        assert "job_lock" in tables
        assert "human_action" in tables
        assert "schedule" in tables
        assert "opportunity" in tables
        assert "operations_state" in tables
        assert "integration_health" in tables
    finally:
        engine.dispose()


def test_migration_adds_price_observation_from_capture_revision(database_url: str) -> None:
    ensure_sqlite_database_directory(database_url)
    config = make_alembic_config(database_url)
    command.upgrade(config, "0002_manual_capture")

    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0002_manual_capture"
        assert "price_observation" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    upgrade_to_head(database_url)
    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0011_operations_control"
        assert "price_observation" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_migration_adds_evaluation_from_price_history_revision(database_url: str) -> None:
    ensure_sqlite_database_directory(database_url)
    config = make_alembic_config(database_url)
    command.upgrade(config, "0003_price_observation")

    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0003_price_observation"
        assert "evaluation" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    upgrade_to_head(database_url)
    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0011_operations_control"
        assert "evaluation" in inspect(engine).get_table_names()
        with engine.connect() as connection:
            triggers = set(
                connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                    "AND tbl_name = 'evaluation'"
                )
                .scalars()
                .all()
            )
        assert triggers == {"trg_evaluation_no_update", "trg_evaluation_no_delete"}
    finally:
        engine.dispose()


def test_migration_adds_purchase_source_decision_from_evaluation_revision(
    database_url: str,
) -> None:
    ensure_sqlite_database_directory(database_url)
    config = make_alembic_config(database_url)
    command.upgrade(config, "0004_evaluation")

    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0004_evaluation"
        assert "purchase_source_decision" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    upgrade_to_head(database_url)
    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0011_operations_control"
        assert "purchase_source_decision" in inspect(engine).get_table_names()
        with engine.connect() as connection:
            triggers = set(
                connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                    "AND tbl_name = 'purchase_source_decision'"
                )
                .scalars()
                .all()
            )
        assert triggers == {
            "trg_purchase_source_decision_no_update",
            "trg_purchase_source_decision_no_delete",
        }
    finally:
        engine.dispose()


def test_migration_adds_repost_decision_from_purchase_source_revision(
    database_url: str,
) -> None:
    ensure_sqlite_database_directory(database_url)
    config = make_alembic_config(database_url)
    command.upgrade(config, "0005_purchase_source_decision")

    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0005_purchase_source_decision"
        assert "repost_decision" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    upgrade_to_head(database_url)
    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0011_operations_control"
        assert "repost_decision" in inspect(engine).get_table_names()
        with engine.connect() as connection:
            triggers = set(
                connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                    "AND tbl_name = 'repost_decision'"
                )
                .scalars()
                .all()
            )
        assert triggers == {
            "trg_repost_decision_no_update",
            "trg_repost_decision_no_delete",
        }
    finally:
        engine.dispose()


def test_migration_adds_job_queue_from_repost_revision(database_url: str) -> None:
    ensure_sqlite_database_directory(database_url)
    config = make_alembic_config(database_url)
    command.upgrade(config, "0006_repost_decision")

    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0006_repost_decision"
        tables = set(inspect(engine).get_table_names())
        assert "job" not in tables
        assert "job_lock" not in tables
    finally:
        engine.dispose()

    upgrade_to_head(database_url)
    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0011_operations_control"
        tables = set(inspect(engine).get_table_names())
        assert "job" in tables
        assert "job_lock" in tables
        indexes = {index["name"] for index in inspect(engine).get_indexes("job")}
        assert "ix_job_claim" in indexes
    finally:
        engine.dispose()


def test_migration_adds_human_action_from_job_revision(database_url: str) -> None:
    ensure_sqlite_database_directory(database_url)
    config = make_alembic_config(database_url)
    command.upgrade(config, "0007_job")

    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0007_job"
        assert "human_action" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    upgrade_to_head(database_url)
    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0011_operations_control"
        assert "human_action" in inspect(engine).get_table_names()
        indexes = {index["name"] for index in inspect(engine).get_indexes("human_action")}
        assert "ix_human_action_status" in indexes
    finally:
        engine.dispose()


def test_migration_adds_schedule_from_human_action_revision(database_url: str) -> None:
    ensure_sqlite_database_directory(database_url)
    config = make_alembic_config(database_url)
    command.upgrade(config, "0008_human_action")

    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0008_human_action"
        assert "schedule" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    upgrade_to_head(database_url)
    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0011_operations_control"
        assert "schedule" in inspect(engine).get_table_names()
        indexes = {index["name"] for index in inspect(engine).get_indexes("schedule")}
        assert "ix_schedule_enabled" in indexes
        unique = {
            constraint["name"] for constraint in inspect(engine).get_unique_constraints("schedule")
        }
        assert "uq_schedule_name" in unique
    finally:
        engine.dispose()


def test_migration_adds_opportunity_from_schedule_revision(database_url: str) -> None:
    ensure_sqlite_database_directory(database_url)
    config = make_alembic_config(database_url)
    command.upgrade(config, "0009_schedule")

    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0009_schedule"
        assert "opportunity" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    upgrade_to_head(database_url)
    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0011_operations_control"
        assert "opportunity" in inspect(engine).get_table_names()
        indexes = {index["name"] for index in inspect(engine).get_indexes("opportunity")}
        assert "ix_opportunity_candidate" in indexes
        unique = {
            constraint["name"]
            for constraint in inspect(engine).get_unique_constraints("opportunity")
        }
        assert "uq_opportunity_evaluation" in unique
    finally:
        engine.dispose()


def test_migration_adds_operations_control_from_opportunity_revision(database_url: str) -> None:
    ensure_sqlite_database_directory(database_url)
    config = make_alembic_config(database_url)
    command.upgrade(config, "0010_opportunity")

    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0010_opportunity"
        tables = set(inspect(engine).get_table_names())
        assert "operations_state" not in tables
        assert "integration_health" not in tables
    finally:
        engine.dispose()

    upgrade_to_head(database_url)
    engine = create_database_engine(database_url)
    try:
        assert current_revision(engine) == "0011_operations_control"
        tables = set(inspect(engine).get_table_names())
        assert "operations_state" in tables
        assert "integration_health" in tables
        indexes = {index["name"] for index in inspect(engine).get_indexes("integration_health")}
        assert "ix_integration_health_state" in indexes
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
        assert "price_observation" not in tables
        assert "evaluation" not in tables
        assert "purchase_source_decision" not in tables
        assert "repost_decision" not in tables
        assert "job" not in tables
        assert "job_lock" not in tables
        assert "human_action" not in tables
        assert "schedule" not in tables
        assert "opportunity" not in tables
        assert "operations_state" not in tables
        assert "integration_health" not in tables
        with engine.connect() as connection:
            version = connection.exec_driver_sql(
                "SELECT version FROM schema_version WHERE component = 'db_schema'"
            ).scalar()
        assert version == "0001_initial"
    finally:
        engine.dispose()
