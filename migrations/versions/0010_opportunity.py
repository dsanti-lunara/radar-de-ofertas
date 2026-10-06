"""opportunities created by the Workflow Engine

Revision ID: 0010_opportunity
Revises: 0009_schedule
Create Date: 2026-10-05

Introduces the durable ``opportunity`` table (RDR-017, AUT-032). An Opportunity is
only created after an approved Candidate and references both the ``candidate`` and
the immutable ``evaluation`` (AUT-030). The ``uq_opportunity_evaluation`` unique
constraint makes the advance idempotent: the same Evaluation can never produce two
Opportunities. ``ix_opportunity_candidate`` backs the per-Candidate query. The
current state is stored on the row; every valid/rejected transition is recorded
append-only in ``audit_event`` (AUT-010, AUT-141). Timestamps are ISO-8601 UTC
strings (AUT-231).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0010_opportunity"
down_revision: str | None = "0009_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"


def upgrade() -> None:
    op.create_table(
        "opportunity",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(length=64),
            sa.ForeignKey("candidate.id"),
            nullable=False,
        ),
        sa.Column(
            "evaluation_id",
            sa.String(length=64),
            sa.ForeignKey("evaluation.id"),
            nullable=False,
        ),
        sa.Column("brand", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column(
            "audit_event_id",
            sa.String(length=64),
            sa.ForeignKey("audit_event.id"),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.UniqueConstraint("evaluation_id", name="uq_opportunity_evaluation"),
    )
    op.create_index("ix_opportunity_candidate", "opportunity", ["candidate_id", "created_at"])
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
    op.drop_index("ix_opportunity_candidate", table_name="opportunity")
    op.drop_table("opportunity")
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
