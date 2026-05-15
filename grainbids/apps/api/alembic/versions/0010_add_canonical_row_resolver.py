"""add canonical row resolver primitives

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Supabase pooled roles can have low statement_timeout; disable statement timeout/lock timeout
    # so migration can complete despite transient catalog lock contention.
    op.execute("SET LOCAL statement_timeout = 0")
    op.execute("SET LOCAL lock_timeout = 0")

    op.create_table(
        "company_source_priority",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_key", sa.String(length=200), nullable=False),
        sa.Column("priority_rank", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "org_id",
            "company_id",
            "source_key",
            name="uq_company_source_priority_org_company_source",
        ),
    )
    op.create_index(
        "ix_company_source_priority_org_company_rank",
        "company_source_priority",
        ["org_id", "company_id", "priority_rank"],
        unique=False,
    )

    # Keep this lightweight: nullable + no server default avoids expensive table rewrite/scan on large tables.
    # Resolver marks winners explicitly after ingest; NULL is treated as non-canonical.
    op.add_column("normalized_prices", sa.Column("is_canonical", sa.Boolean(), nullable=True))
    op.add_column("normalized_prices", sa.Column("canonical_rank", sa.Integer(), nullable=True))
    op.add_column("normalized_prices", sa.Column("canonical_reason", sa.String(length=250), nullable=True))

    # Intentionally skip full-table backfill and large index creation here to keep migration fast/safe.


def downgrade() -> None:
    op.drop_column("normalized_prices", "canonical_reason")
    op.drop_column("normalized_prices", "canonical_rank")
    op.drop_column("normalized_prices", "is_canonical")

    op.drop_index("ix_company_source_priority_org_company_rank", table_name="company_source_priority")
    op.drop_table("company_source_priority")
