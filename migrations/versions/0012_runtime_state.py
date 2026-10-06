"""runtime shutdown marker for crash recovery

Revision ID: 0012_runtime_state
Revises: 0011_operations_control
Create Date: 2026-10-05

Introduces the durable ``runtime_state`` table (RDR-042, AUT-229): a single row
(``id='core'``) with the ``clean_shutdown`` marker plus the last recovery/start/
shutdown instants and the recovery counter. A clean shutdown sets the marker; a
startup that finds it unset detects an unclean shutdown, audits it and runs the
Recovery Manager. Timestamps are ISO-8601 UTC strings (AUT-231).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0012_runtime_state"
down_revision: str | None = "0011_operations_control"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"


def upgrade() -> None:
    op.create_table(
        "runtime_state",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("clean_shutdown", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.String(length=40), nullable=True),
        sa.Column("shutdown_at", sa.String(length=40), nullable=True),
        sa.Column("last_recovery_at", sa.String(length=40), nullable=True),
        sa.Column("recovery_count", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
    )
    op.execute(
        sa.text(
            "UPDATE schema_version SET version = :version, recorded_at = :recorded_at "
            "WHERE component = :component"
        ).bindparams(
            version=revision,
            recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            component=DB_SCHEMA_COMPONENT,
        )
    )


def downgrade() -> None:
    op.drop_table("runtime_state")
    op.execute(
        sa.text(
            "UPDATE schema_version SET version = :version, recorded_at = :recorded_at "
            "WHERE component = :component"
        ).bindparams(
            version=down_revision,
            recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            component=DB_SCHEMA_COMPONENT,
        )
    )
