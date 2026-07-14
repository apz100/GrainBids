"""add market report delivery tracking

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "newsletter_subscribers",
        sa.Column("unsubscribe_token", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_newsletter_subscribers_unsubscribe_token",
        "newsletter_subscribers",
        ["unsubscribe_token"],
        unique=True,
    )

    op.create_table(
        "market_report_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscriber_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issue_key", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("subject", sa.String(length=250), nullable=False),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["subscriber_id"], ["newsletter_subscribers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscriber_id",
            "issue_key",
            name="uq_market_report_delivery_subscriber_issue",
        ),
    )
    op.create_index(
        "ix_market_report_deliveries_subscriber_id",
        "market_report_deliveries",
        ["subscriber_id"],
        unique=False,
    )
    op.create_index(
        "ix_market_report_deliveries_issue_key",
        "market_report_deliveries",
        ["issue_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_market_report_deliveries_issue_key", table_name="market_report_deliveries")
    op.drop_index("ix_market_report_deliveries_subscriber_id", table_name="market_report_deliveries")
    op.drop_table("market_report_deliveries")
    op.drop_index("ix_newsletter_subscribers_unsubscribe_token", table_name="newsletter_subscribers")
    op.drop_column("newsletter_subscribers", "unsubscribe_token")
