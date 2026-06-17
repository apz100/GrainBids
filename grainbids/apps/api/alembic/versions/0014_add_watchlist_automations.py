"""add watchlist automations

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-17
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
        "watchlist_automations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("watchlist_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("watchlists.id"), nullable=False, unique=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("digest_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("alert_promotion_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("linked_saved_search_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("saved_searches.id"), nullable=True),
        sa.Column("linked_alert_rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alert_rules.id"), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_digest_row_count", sa.Integer(), nullable=True),
        sa.Column("last_error_message", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_watchlist_automations_org_id", "watchlist_automations", ["org_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_watchlist_automations_org_id", table_name="watchlist_automations")
    op.drop_table("watchlist_automations")
