"""ai input hash for the content generation result cache

Revision ID: 0016_ai_input_cache
Revises: 0015_content_generation
Create Date: 2026-10-06

Adds the ``ai_input_hash`` column to the append-only ``content_generation`` table
(RDR-055, AUT-088) plus the ``ix_content_generation_ai_input`` index used to look
up an equivalent persisted generation. The hash is the canonical hash of the
versioned provider input (product/offer, Evaluation scores, backend-sustained
claims, warnings and Knowledge/Prompt versions); a relevant change produces a new
hash and invalidates reuse. Rows written before this migration keep an empty hash
(default ``''``) and can never match a real sha256, so they are never served as
cache hits. ``content_generation`` remains append-only (the 0015 triggers are
untouched); the ``schema_version`` row is updated like every other migration.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0016_ai_input_cache"
down_revision: str | None = "0015_content_generation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"


def upgrade() -> None:
    op.add_column(
        "content_generation",
        sa.Column("ai_input_hash", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_content_generation_ai_input",
        "content_generation",
        ["opportunity_id", "ai_input_hash"],
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
    op.drop_index("ix_content_generation_ai_input", table_name="content_generation")
    op.drop_column("content_generation", "ai_input_hash")
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
