"""operational modes, kill switch and integration health

Revision ID: 0011_operations_control
Revises: 0010_opportunity
Create Date: 2026-10-05

Introduces the durable ``operations_state`` and ``integration_health`` tables
(RDR-043, RDR-044). ``operations_state`` is a single row (``id='global'``) with
the global mode and the ``STOP_EXTERNAL_ACTIONS`` kill switch; safe
reading/diagnostic/recovery never depend on it (AUT-317). ``integration_health``
keeps one row per integration so one unhealthy integration isolates its own scope
(AUT-315). Both are upserted atomically with their audit events; timestamps are
ISO-8601 UTC strings (AUT-231).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0011_operations_control"
down_revision: str | None = "0010_opportunity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"


def upgrade() -> None:
    op.create_table(
        "operations_state",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("global_mode", sa.String(length=16), nullable=False),
        sa.Column("stop_external_actions", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("correlation_id", sa.String(length=64)),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
    )
    op.create_table(
        "integration_health",
        sa.Column("name", sa.String(length=32), primary_key=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64)),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
    )
    op.create_index(
        "ix_integration_health_state",
        "integration_health",
        ["state", "updated_at"],
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
    op.drop_index("ix_integration_health_state", table_name="integration_health")
    op.drop_table("integration_health")
    op.drop_table("operations_state")
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
