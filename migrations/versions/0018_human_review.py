"""append-only versioned human review

Revision ID: 0018_human_review
Revises: 0017_publication
Create Date: 2026-10-06

Introduces the append-only ``human_review`` table (RDR-060, AUT-035, AUT-036).
Each row is one immutable operator review of a ``candidate``: the snapshotted
``ai_decision`` and the ``human_decision`` are stored separately, together with
the operator ``reason``/``note`` and, for an ``EDIT_CONTENT`` decision, the
sanitized edited copy. SQLite triggers reject UPDATE/DELETE so the decision
history is never rewritten, and foreign keys tie the row to its Candidate,
optional AIReview and audit event (AUT-233). Text is stored sanitized and
timestamps ISO-8601 UTC (AUT-203, AUT-299).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0018_human_review"
down_revision: str | None = "0017_publication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"

_TRIGGER_NO_UPDATE = "trg_human_review_no_update"
_TRIGGER_NO_DELETE = "trg_human_review_no_delete"


def upgrade() -> None:
    op.create_table(
        "human_review",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("candidate_id", sa.String(length=64), nullable=False),
        sa.Column("ai_review_id", sa.String(length=64), nullable=True),
        sa.Column("ai_decision", sa.String(length=32), nullable=True),
        sa.Column("human_decision", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("edited_content", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("audit_event_id", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate.id"]),
        sa.ForeignKeyConstraint(["ai_review_id"], ["ai_review.id"]),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_event.id"]),
    )
    op.create_index(
        "ix_human_review_candidate",
        "human_review",
        ["candidate_id", "created_at"],
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_human_review_no_update BEFORE UPDATE ON human_review "
            "BEGIN SELECT RAISE(ABORT, 'human_review is append-only'); END"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_human_review_no_delete BEFORE DELETE ON human_review "
            "BEGIN SELECT RAISE(ABORT, 'human_review is append-only'); END"
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
    op.drop_index("ix_human_review_candidate", table_name="human_review")
    op.drop_table("human_review")
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
