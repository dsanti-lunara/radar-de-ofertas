"""Alembic migration helpers (RDR-007).

Migrations run from an empty database to ``head`` and report the current
revision against the expected head so startup can block on drift
(AUT-224, AUT-225).
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine

from radar.infrastructure.database import ensure_sqlite_database_directory

IN_MEMORY_DATABASE_URL = "sqlite+pysqlite:///:memory:"


def default_migrations_dir() -> Path:
    """Locate the ``migrations/`` directory for source checkouts."""

    override = os.environ.get("RADAR_MIGRATIONS_DIR")
    if override:
        return Path(override)
    checkout_candidate = Path(__file__).resolve().parents[3] / "migrations"
    if checkout_candidate.is_dir():
        return checkout_candidate
    return Path.cwd() / "migrations"


def make_alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(default_migrations_dir()))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_to_head(database_url: str) -> None:
    ensure_sqlite_database_directory(database_url)
    command.upgrade(make_alembic_config(database_url), "head")


def head_revision(database_url: str | None = None) -> str | None:
    config = make_alembic_config(database_url or IN_MEMORY_DATABASE_URL)
    return ScriptDirectory.from_config(config).get_current_head()


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision()
