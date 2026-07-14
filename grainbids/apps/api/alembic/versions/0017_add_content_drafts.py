"""add QA-gated content drafts

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_key", sa.String(length=160), nullable=False),
        sa.Column("region_key", sa.String(length=80), nullable=False),
        sa.Column("region_name", sa.String(length=120), nullable=False),
        sa.Column("cadence", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=80), nullable=False),
        sa.Column("fact_schema_version", sa.String(length=20), nullable=False),
        sa.Column("template_version", sa.String(length=20), nullable=False),
        sa.Column("facts_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("artifacts_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("qa_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "org_id",
            "issue_key",
            "input_fingerprint",
            name="uq_content_drafts_org_issue_fingerprint",
        ),
    )
    op.create_index("ix_content_drafts_issue_key", "content_drafts", ["issue_key"], unique=False)
    op.create_index("ix_content_drafts_region_key", "content_drafts", ["region_key"], unique=False)
    op.create_index("ix_content_drafts_cadence", "content_drafts", ["cadence"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_content_drafts_cadence", table_name="content_drafts")
    op.drop_index("ix_content_drafts_region_key", table_name="content_drafts")
    op.drop_index("ix_content_drafts_issue_key", table_name="content_drafts")
    op.drop_table("content_drafts")
