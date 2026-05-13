"""add saved searches and notification logs

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("filters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("delivery_months_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("target_cash_price_bu", sa.Numeric(18, 6), nullable=True),
        sa.Column("target_basis", sa.Numeric(18, 6), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saved_searches_org_id", "saved_searches", ["org_id"], unique=False)

    op.add_column("alert_rules", sa.Column("saved_search_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "alert_rules",
        sa.Column("delivery_months_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_alert_rules_saved_search_id", "alert_rules", ["saved_search_id"], unique=False)
    op.create_foreign_key(
        "fk_alert_rules_saved_search_id",
        "alert_rules",
        "saved_searches",
        ["saved_search_id"],
        ["id"],
    )

    op.create_table(
        "notification_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_logs_org_id", "notification_logs", ["org_id"], unique=False)
    op.create_index("ix_notification_logs_alert_id", "notification_logs", ["alert_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_notification_logs_alert_id", table_name="notification_logs")
    op.drop_index("ix_notification_logs_org_id", table_name="notification_logs")
    op.drop_table("notification_logs")

    op.drop_constraint("fk_alert_rules_saved_search_id", "alert_rules", type_="foreignkey")
    op.drop_index("ix_alert_rules_saved_search_id", table_name="alert_rules")
    op.drop_column("alert_rules", "delivery_months_json")
    op.drop_column("alert_rules", "saved_search_id")

    op.drop_index("ix_saved_searches_org_id", table_name="saved_searches")
    op.drop_table("saved_searches")
