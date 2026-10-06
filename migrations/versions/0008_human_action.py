"""human action records for retry/Dead Job routing

Revision ID: 0008_human_action
Revises: 0007_job
Create Date: 2026-10-05

Introduces the ``human_action`` table (RDR-040, AUT-126, AUT-244). A HumanAction
records a required intervention raised by the retry/Dead Job flow (RDR-037,
RDR-038): it references the existing entity (``entity_type``/``entity_id``) so the
job is never recreated, carries the Correlation ID of the pipeline that raised it
and persists the impact/next steps so an operator can act without reading SQL.
Timestamps are ISO-8601 UTC strings (AUT-231) and the ``ix_human_action_status``
index backs the open-actions query. The ``0007_job`` schema already persists
``status``/``attempts``/``available_at``, which the retry/dead transitions reuse,
so no job-table change is required.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0008_human_action"
down_revision: str | None = "0007_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"


def upgrade() -> None:
    op.create_table(
        "human_action",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("action_type", sa.String(length=48), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=48), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=False),
        sa.Column("impact", sa.Text(), nullable=False),
        sa.Column("next_steps", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
    )
    op.create_index(
        "ix_human_action_status",
        "human_action",
        ["status", "created_at"],
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
    op.drop_index("ix_human_action_status", table_name="human_action")
    op.drop_table("human_action")
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
