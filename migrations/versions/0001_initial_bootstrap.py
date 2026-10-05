"""bootstrap schema_version table

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-05

Establishes the first real migration so an empty database can be upgraded to
``head``. The table records independent component versions (AUT-227) and is not
a domain entity.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"


def upgrade() -> None:
    schema_version = op.create_table(
        "schema_version",
        sa.Column("component", sa.String(length=64), primary_key=True),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("recorded_at", sa.String(length=40), nullable=False),
    )
    op.bulk_insert(
        schema_version,
        [
            {
                "component": DB_SCHEMA_COMPONENT,
                "version": revision,
                "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("schema_version")
