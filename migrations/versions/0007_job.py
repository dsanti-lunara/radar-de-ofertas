"""persistent job queue and logical locks

Revision ID: 0007_job
Revises: 0006_repost_decision
Create Date: 2026-10-05

Introduces the durable ``job`` table (RDR-034, RDR-035) and the ``job_lock``
table (RDR-036). Each job persists priority, availability, attempts/max_attempts,
the Job status and the Correlation ID, plus the expiring lease fields
(``locked_by``/``locked_at``/``lease_expires_at``) that let another worker
recover a crashed execution. Job states are independent from domain states
(AUT-118). Timestamps are ISO-8601 UTC strings so SQLite string ordering matches
chronological ordering for claim recovery (AUT-231).

Unlike the append-only decision tables, jobs are mutable by design: a job
transitions PENDING -> CLAIMED -> RUNNING -> SUCCESS. The ``ix_job_claim`` index
backs the priority/availability claim query, so a claim stays a single atomic
statement under SQLite's single-writer guarantee (AUT-233).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0007_job"
down_revision: str | None = "0006_repost_decision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("type", sa.String(length=48), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.String(length=40), nullable=False),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("locked_at", sa.String(length=40), nullable=True),
        sa.Column("lease_expires_at", sa.String(length=40), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
    )
    op.create_index(
        "ix_job_claim",
        "job",
        ["status", "priority", "available_at"],
    )
    op.create_table(
        "job_lock",
        sa.Column("name", sa.String(length=128), primary_key=True),
        sa.Column("owner", sa.String(length=128), nullable=False),
        sa.Column("acquired_at", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.String(length=40), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
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
    op.drop_table("job_lock")
    op.drop_index("ix_job_claim", table_name="job")
    op.drop_table("job")
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
