"""init schema

Revision ID: 0001
Revises:
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("plan", sa.String(length=50), nullable=False, server_default="trial"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="member"),
        sa.Column("auth_user_id", sa.String(length=128), nullable=True, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("org_id", "email", name="uq_users_org_email"),
    )

    op.create_table(
        "sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("location_name", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "commodities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("unit", sa.String(length=20), nullable=False, server_default="bu"),
        sa.Column("conversion_factor", sa.Numeric(18, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "price_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("commodity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("commodities.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("futures_month", sa.String(length=50), nullable=True),
        sa.Column("futures_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("basis", sa.Numeric(18, 6), nullable=True),
        sa.Column("cash_price_bu", sa.Numeric(18, 6), nullable=True),
        sa.Column("cash_price_mt", sa.Numeric(18, 6), nullable=True),
        sa.Column("delivery_start", sa.String(length=50), nullable=True),
        sa.Column("delivery_end", sa.String(length=50), nullable=True),
        sa.Column("raw_payload_json", postgresql.JSONB(), nullable=True),
    )

    op.create_table(
        "normalized_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("price_snapshots.id"), nullable=False),
        sa.Column("location", sa.String(length=200), nullable=False),
        sa.Column("commodity_name", sa.String(length=120), nullable=False),
        sa.Column("delivery_label", sa.String(length=120), nullable=True),
        sa.Column("futures_month", sa.String(length=50), nullable=True),
        sa.Column("futures_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("basis", sa.Numeric(18, 6), nullable=True),
        sa.Column("cash_price_bu", sa.Numeric(18, 6), nullable=True),
        sa.Column("cash_price_mt", sa.Numeric(18, 6), nullable=True),
        sa.Column("basis_change", sa.Numeric(18, 6), nullable=True),
        sa.Column("composite_key", sa.String(length=400), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("snapshot_id", "composite_key", name="uq_normalized_prices_snapshot_key"),
    )

    op.create_table(
        "alert_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("commodity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("commodities.id"), nullable=True),
        sa.Column("rule_type", sa.String(length=50), nullable=False),
        sa.Column("threshold_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("comparison_operator", sa.String(length=10), nullable=False, server_default=">"),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("alert_rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alert_rules.id"), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("message", sa.String(length=2000), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="new"),
    )

    op.create_table(
        "quote_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("commodity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("commodities.id"), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("assumptions_json", postgresql.JSONB(), nullable=True),
        sa.Column("output_file_url", sa.String(length=2000), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("quote_runs")
    op.drop_table("alerts")
    op.drop_table("alert_rules")
    op.drop_table("normalized_prices")
    op.drop_table("price_snapshots")
    op.drop_table("commodities")
    op.drop_table("sources")
    op.drop_table("users")
    op.drop_table("organizations")
