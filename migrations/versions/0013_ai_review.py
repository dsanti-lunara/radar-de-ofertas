"""append-only versioned editorial AI review

Revision ID: 0013_ai_review
Revises: 0012_runtime_state
Create Date: 2026-10-06

Introduces the append-only ``ai_review`` table (RDR-050, AUT-035, AUT-065). Each
row is one immutable Editorial Review of a ``candidate`` bound to an immutable
``evaluation``: the provider/model, the knowledge/prompt versions, the structured
decision (``editorial_angle``/``reason_codes``/``warnings``) and the
``allowed_claims``/input snapshot as JSON. Marketplace free text is stored
sanitized (no HTML, no secrets) and money as decimal strings (AUT-203, AUT-232,
AUT-299). SQLite triggers reject UPDATE/DELETE so a review is never overwritten,
and foreign keys tie the row to its Candidate, Evaluation and audit event
(AUT-233).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0013_ai_review"
down_revision: str | None = "0012_runtime_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"

_TRIGGER_NO_UPDATE = "trg_ai_review_no_update"
_TRIGGER_NO_DELETE = "trg_ai_review_no_delete"


def upgrade() -> None:
    op.create_table(
        "ai_review",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("candidate_id", sa.String(length=64), nullable=False),
        sa.Column("evaluation_id", sa.String(length=64), nullable=False),
        sa.Column("task", sa.String(length=48), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("knowledge_version", sa.String(length=64), nullable=False),
        sa.Column("knowledge_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("editorial_angle", sa.String(length=128), nullable=True),
        sa.Column("reason_codes", sa.Text(), nullable=False),
        sa.Column("warnings", sa.Text(), nullable=False),
        sa.Column("allowed_claims", sa.Text(), nullable=False),
        sa.Column("input_snapshot", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("audit_event_id", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate.id"]),
        sa.ForeignKeyConstraint(["evaluation_id"], ["evaluation.id"]),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_event.id"]),
    )
    op.create_index(
        "ix_ai_review_candidate",
        "ai_review",
        ["candidate_id", "created_at"],
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ai_review_no_update BEFORE UPDATE ON ai_review "
            "BEGIN SELECT RAISE(ABORT, 'ai_review is append-only'); END"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_ai_review_no_delete BEFORE DELETE ON ai_review "
            "BEGIN SELECT RAISE(ABORT, 'ai_review is append-only'); END"
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
    op.drop_index("ix_ai_review_candidate", table_name="ai_review")
    op.drop_table("ai_review")
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
