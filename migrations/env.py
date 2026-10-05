"""Alembic environment for the Radar Engine database."""

from __future__ import annotations

import contextlib
from logging.config import fileConfig

from alembic import context

from radar.infrastructure.database import create_database_engine

config = context.config

if config.config_file_name is not None:
    with contextlib.suppress(Exception):
        fileConfig(config.config_file_name)

target_metadata = None


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_database_engine(_database_url())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
