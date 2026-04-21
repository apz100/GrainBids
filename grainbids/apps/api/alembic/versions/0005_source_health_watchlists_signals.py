"""source health, watchlists, signals, and ingestion metadata

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("adapter_key", sa.String(length=100), nullable=True))
    op.add_column("sources", sa.Column("region", sa.String(length=120), nullable=True))
    op.add_column("sources", sa.Column("polling_interval_minutes", sa.Integer(), nullable=False, server_default="15"))
    op.add_column("sources", sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="90"))
    op.add_column("sources", sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("sources", sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("last_ingestion_latency_ms", sa.BigInteger(), nullable=True))
    op.add_column("sources", sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sources", sa.Column("confidence_score", sa.Numeric(6, 3), nullable=True))
    op.add_column("sources", sa.Column("latest_error_message", sa.String(length=2000), nullable=True))

    op.add_column("ingestion_runs", sa.Column("trigger_type", sa.String(length=30), nullable=False, server_default="manual"))
    op.add_column("ingestion_runs", sa.Column("attempt_number", sa.BigInteger(), nullable=False, server_default="1"))
    op.add_column("ingestion_runs", sa.Column("max_attempts", sa.BigInteger(), nullable=False, server_default="1"))
    op.add_column("ingestion_runs", sa.Column("duration_ms", sa.BigInteger(), nullable=True))
    op.add_column("ingestion_runs", sa.Column("parse_success_rate", sa.Numeric(6, 3), nullable=True))
    op.add_column("ingestion_runs", sa.Column("schema_drift_count", sa.BigInteger(), nullable=True))

    op.create_table(
        "watchlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("filters_json", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "source_health_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ingestion_latency_ms", sa.Integer(), nullable=True),
        sa.Column("parse_success_rate", sa.Numeric(6, 3), nullable=True),
        sa.Column("stale_age_minutes", sa.Integer(), nullable=True),
        sa.Column("schema_drift_incidents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="unknown"),
    )

    op.create_table(
        "signal_forecasts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("composite_key", sa.String(length=400), nullable=False),
        sa.Column("horizon_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("basis_forecast", sa.Numeric(18, 6), nullable=True),
        sa.Column("cash_price_bu_forecast", sa.Numeric(18, 6), nullable=True),
        sa.Column("cash_price_mt_forecast", sa.Numeric(18, 6), nullable=True),
        sa.Column("confidence_low", sa.Numeric(18, 6), nullable=True),
        sa.Column("confidence_high", sa.Numeric(18, 6), nullable=True),
        sa.Column("confidence_score", sa.Numeric(6, 3), nullable=True),
        sa.Column("model_version", sa.String(length=80), nullable=False, server_default="baseline-v1"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("signal_forecasts")
    op.drop_table("source_health_snapshots")
    op.drop_table("watchlists")

    op.drop_column("ingestion_runs", "schema_drift_count")
    op.drop_column("ingestion_runs", "parse_success_rate")
    op.drop_column("ingestion_runs", "duration_ms")
    op.drop_column("ingestion_runs", "max_attempts")
    op.drop_column("ingestion_runs", "attempt_number")
    op.drop_column("ingestion_runs", "trigger_type")

    op.drop_column("sources", "latest_error_message")
    op.drop_column("sources", "confidence_score")
    op.drop_column("sources", "consecutive_failures")
    op.drop_column("sources", "last_ingestion_latency_ms")
    op.drop_column("sources", "last_error_at")
    op.drop_column("sources", "last_success_at")
    op.drop_column("sources", "last_polled_at")
    op.drop_column("sources", "next_poll_at")
    op.drop_column("sources", "max_retries")
    op.drop_column("sources", "timeout_seconds")
    op.drop_column("sources", "polling_interval_minutes")
    op.drop_column("sources", "region")
    op.drop_column("sources", "adapter_key")
