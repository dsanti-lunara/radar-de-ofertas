"""manual capture, provenance and audit schema

Revision ID: 0002_manual_capture
Revises: 0001_initial
Create Date: 2026-10-05

Introduces the distinct domain entities a manual capture materializes:
``product``, ``marketplace_product`` (unique by ``marketplace + external_id``),
``offer``, ``raw_capture``, ``evidence``, ``discovery_event``, ``candidate`` and
the append-only ``audit_event``. Timestamps are ISO-8601 UTC strings and money
is stored as decimal strings (AUT-231, AUT-232). Foreign keys and the identity
constraint are enforced by SQLite, not only by the application (AUT-233).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0002_manual_capture"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DB_SCHEMA_COMPONENT = "db_schema"


def upgrade() -> None:
    op.create_table(
        "product",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("subcategory", sa.Text(), nullable=True),
        sa.Column("attributes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
    )
    op.create_table(
        "marketplace_product",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("marketplace", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("seller_id", sa.String(length=128), nullable=True),
        sa.Column("raw_category", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.String(length=40), nullable=False),
        sa.Column("last_seen_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.UniqueConstraint("marketplace", "external_id", name="uq_marketplace_product_identity"),
    )
    op.create_table(
        "offer",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("marketplace_product_id", sa.String(length=64), nullable=False),
        sa.Column("current_price", sa.String(length=40), nullable=False),
        sa.Column("original_price", sa.String(length=40), nullable=True),
        sa.Column("discount_percent", sa.String(length=40), nullable=True),
        sa.Column("sales_count", sa.Integer(), nullable=True),
        sa.Column("seller_id", sa.String(length=128), nullable=True),
        sa.Column("seller_name", sa.Text(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=True),
        sa.Column("shipping_cost", sa.String(length=40), nullable=True),
        sa.Column("coupon", sa.Text(), nullable=True),
        sa.Column("affiliate_commission", sa.String(length=40), nullable=True),
        sa.Column("captured_at", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["marketplace_product_id"], ["marketplace_product.id"]),
    )
    op.create_table(
        "raw_capture",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("marketplace", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.String(length=40), nullable=False),
    )
    op.create_table(
        "evidence",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("raw_reference", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["raw_reference"], ["raw_capture.id"]),
    )
    op.create_index("ix_evidence_entity", "evidence", ["entity_type", "entity_id"])
    op.create_table(
        "audit_event",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.String(length=40), nullable=False),
    )
    op.create_table(
        "discovery_event",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("marketplace", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("raw_capture_id", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["raw_capture_id"], ["raw_capture.id"]),
    )
    op.create_table(
        "candidate",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("offer_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("raw_capture_id", sa.String(length=64), nullable=False),
        sa.Column("discovery_event_id", sa.String(length=64), nullable=False),
        sa.Column("audit_event_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["offer_id"], ["offer.id"]),
        sa.ForeignKeyConstraint(["raw_capture_id"], ["raw_capture.id"]),
        sa.ForeignKeyConstraint(["discovery_event_id"], ["discovery_event.id"]),
        sa.ForeignKeyConstraint(["audit_event_id"], ["audit_event.id"]),
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
    op.drop_table("candidate")
    op.drop_table("discovery_event")
    op.drop_table("audit_event")
    op.drop_index("ix_evidence_entity", table_name="evidence")
    op.drop_table("evidence")
    op.drop_table("raw_capture")
    op.drop_table("offer")
    op.drop_table("marketplace_product")
    op.drop_table("product")
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
