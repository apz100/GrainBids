"""add newsletter subscribers

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "newsletter_subscribers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=160), nullable=True),
        sa.Column("audience", sa.String(length=40), nullable=False, server_default="farmer"),
        sa.Column("signup_source", sa.String(length=100), nullable=False, server_default="homepage"),
        sa.Column("consent_version", sa.String(length=40), nullable=False, server_default="market-report-v1"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_newsletter_subscribers_email"),
    )
    op.create_index(
        "ix_newsletter_subscribers_email",
        "newsletter_subscribers",
        ["email"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_newsletter_subscribers_email", table_name="newsletter_subscribers")
    op.drop_table("newsletter_subscribers")
