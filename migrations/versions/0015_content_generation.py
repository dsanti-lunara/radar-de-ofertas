"""append-only versioned content generation preview

Revision ID: 0015_content_generation
Revises: 0014_affiliate_link
Create Date: 2026-10-06

Introduces the append-only ``content_generation`` table (RDR-019, RDR-051..054,
RDR-069, AUT-034/AUT-081). Each row is one versioned content preview of an
``opportunity``: the AI-generated ``headline``/``body``/``cta`` and the final
rendered content (backend price, validated affiliate URL, disclosure and tracking)
are stored separately with their own versions. The ``facts``/``fact_hash`` snapshot
lets the boundary derive ``STALE`` without mutating the row. SQLite triggers reject
UPDATE/DELETE so a preview is never overwritten, and foreign keys tie the row to
its Opportunity, Candidate and audit event (AUT-233). Money is a decimal string and
timestamps ISO-8601 UTC (AUT-231, AUT-232).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0015_content_generation"
down_revision: str | None = "0014_affiliate_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"

_TRIGGER_NO_UPDATE = "trg_content_generation_no_update"
_TRIGGER_NO_DELETE = "trg_content_generation_no_delete"


def upgrade() -> None:
    op.create_table(
        "content_generation",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.String(length=64),
            sa.ForeignKey("opportunity.id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.String(length=64),
            sa.ForeignKey("candidate.id"),
            nullable=False,
        ),
        sa.Column("brand", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("generation_version", sa.String(length=64), nullable=False),
        sa.Column("knowledge_version", sa.String(length=64), nullable=False),
        sa.Column("knowledge_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("renderer_version", sa.String(length=64), nullable=False),
        sa.Column("generated_content", sa.Text(), nullable=False),
        sa.Column("final_content", sa.Text(), nullable=False),
        sa.Column("guards", sa.Text(), nullable=False),
        sa.Column("warnings", sa.Text(), nullable=False),
        sa.Column("facts", sa.Text(), nullable=False),
        sa.Column("fact_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column(
            "audit_event_id",
            sa.String(length=64),
            sa.ForeignKey("audit_event.id"),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
    )
    op.create_index(
        "ix_content_generation_opportunity",
        "content_generation",
        ["opportunity_id", "created_at"],
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_content_generation_no_update "
            "BEFORE UPDATE ON content_generation "
            "BEGIN SELECT RAISE(ABORT, 'content_generation is append-only'); END"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_content_generation_no_delete "
            "BEFORE DELETE ON content_generation "
            "BEGIN SELECT RAISE(ABORT, 'content_generation is append-only'); END"
        )
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
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRIGGER_NO_UPDATE}"))
    op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRIGGER_NO_DELETE}"))
    op.drop_index("ix_content_generation_opportunity", table_name="content_generation")
    op.drop_table("content_generation")
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
