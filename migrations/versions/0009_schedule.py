"""persistent schedules for the Scheduler

Revision ID: 0009_schedule
Revises: 0008_human_action
Create Date: 2026-10-05

Introduces the durable ``schedule`` table (RDR-039, AUT-117). A schedule persists
its cadence (``INTERVAL``/``CRON``/``ON_DEMAND``), the Job it creates, the
operational ``timezone`` and quiet windows (AUT-143), the equivalent lock name
and the ``last_tick_at`` cursor used to coalesce missed ticks (AUT-134). The
scheduler only creates Jobs; the Job itself stays in ``job`` and the equivalent
logical lock in ``job_lock`` (AUT-140). Timestamps are ISO-8601 UTC strings
(AUT-231) and the ``ix_schedule_enabled`` index backs the due-schedule query.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0009_schedule"
down_revision: str | None = "0008_human_action"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"


def upgrade() -> None:
    op.create_table(
        "schedule",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("job_type", sa.String(length=48), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=True),
        sa.Column("cron", sa.String(length=128), nullable=True),
        sa.Column("quiet_windows", sa.Text(), nullable=False),
        sa.Column("lock_name", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("last_tick_at", sa.String(length=40), nullable=True),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.UniqueConstraint("name", name="uq_schedule_name"),
    )
    op.create_index("ix_schedule_enabled", "schedule", ["enabled", "type"])
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
    op.drop_index("ix_schedule_enabled", table_name="schedule")
    op.drop_table("schedule")
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
