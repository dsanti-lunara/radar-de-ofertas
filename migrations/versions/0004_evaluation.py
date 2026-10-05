"""append-only immutable evaluation

Revision ID: 0004_evaluation
Revises: 0003_price_observation
Create Date: 2026-10-05

Introduces the append-only ``evaluation`` table (RDR-016, AUT-030, AUT-065). Each
row is one immutable, versioned Evaluation of a ``candidate``: the Deal,
Monetization and Confidence results plus the decision, the passed/failed Hard
Rules, the feature snapshot, the score breakdown and the scoring versions. Money
scores are stored as decimal strings and timestamps as ISO-8601 UTC strings
(AUT-231, AUT-232). SQLite triggers reject any UPDATE or DELETE so an old
evaluation is never overwritten, and foreign keys tie the row to its Candidate
and audit event (AUT-233).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0004_evaluation"
down_revision: str | None = "0003_price_observation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"

_TRIGGER_NO_UPDATE = "trg_evaluation_no_update"
_TRIGGER_NO_DELETE = "trg_evaluation_no_delete"


def upgrade() -> None:
    op.create_table(
        "evaluation",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("candidate_id", sa.String(length=64), nullable=False),
        sa.Column("brand", sa.String(length=32), nullable=False),
        sa.Column("deal_score", sa.String(length=40), nullable=True),
        sa.Column("monetization_score", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("auto_eligible", sa.Boolean(), nullable=False),
        sa.Column("passed_rules", sa.Text(), nullable=False),
        sa.Column("failed_rules", sa.Text(), nullable=False),
        sa.Column("warnings", sa.Text(), nullable=False),
        sa.Column("breakdown", sa.Text(), nullable=False),
        sa.Column("feature_snapshot", sa.Text(), nullable=False),
        sa.Column("scoring_version", sa.String(length=32), nullable=False),
        sa.Column("deal_scoring_version", sa.String(length=32), nullable=False),
        sa.Column("monetization_scoring_version", sa.String(length=32), nullable=False),
        sa.Column("confidence_scoring_version", sa.String(length=32), nullable=False),
        sa.Column("taxonomy_version", sa.String(length=64), nullable=True),
        sa.Column("taxonomy_hash", sa.String(length=64), nullable=True),
        sa.Column("audit_event_id", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidate.id"]),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_event.id"]),
    )
    op.create_index(
        "ix_evaluation_candidate_created",
        "evaluation",
        ["candidate_id", "created_at"],
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_evaluation_no_update BEFORE UPDATE ON evaluation "
            "BEGIN SELECT RAISE(ABORT, 'evaluation is append-only'); END"
        )
    )
    op.execute(
        sa.text(
            "CREATE TRIGGER trg_evaluation_no_delete BEFORE DELETE ON evaluation "
            "BEGIN SELECT RAISE(ABORT, 'evaluation is append-only'); END"
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
    op.drop_index("ix_evaluation_candidate_created", table_name="evaluation")
    op.drop_table("evaluation")
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
