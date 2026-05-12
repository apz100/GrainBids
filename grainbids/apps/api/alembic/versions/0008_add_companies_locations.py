"""add companies and locations

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("canonical_key", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "canonical_key", name="uq_companies_org_canonical_key"),
    )
    op.create_index("ix_companies_org_id", "companies", ["org_id"], unique=False)

    op.create_table(
        "locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("canonical_key", sa.String(length=200), nullable=False),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "canonical_key", name="uq_locations_org_canonical_key"),
    )
    op.create_index("ix_locations_org_id", "locations", ["org_id"], unique=False)
    op.create_index("ix_locations_company_id", "locations", ["company_id"], unique=False)

    op.add_column("normalized_prices", sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("normalized_prices", sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_normalized_prices_company_id", "normalized_prices", ["company_id"], unique=False)
    op.create_index("ix_normalized_prices_location_id", "normalized_prices", ["location_id"], unique=False)
    op.create_foreign_key("fk_normalized_prices_company_id", "normalized_prices", "companies", ["company_id"], ["id"])
    op.create_foreign_key("fk_normalized_prices_location_id", "normalized_prices", "locations", ["location_id"], ["id"])

    # Backfill canonical company rows from existing normalized data.
    op.execute(
        """
        INSERT INTO companies (id, org_id, name, canonical_key)
        SELECT DISTINCT
            gen_random_uuid(),
            s.org_id,
            trim(np.source_name),
            lower(trim(np.source_name))
        FROM normalized_prices np
        JOIN price_snapshots ps ON ps.id = np.snapshot_id
        JOIN sources s ON s.id = ps.source_id
        WHERE np.source_name IS NOT NULL AND trim(np.source_name) <> ''
        ON CONFLICT (org_id, canonical_key) DO NOTHING
        """
    )

    # Backfill canonical location rows from existing normalized data.
    op.execute(
        """
        INSERT INTO locations (id, org_id, name, canonical_key, region)
        SELECT DISTINCT
            gen_random_uuid(),
            s.org_id,
            trim(np.location),
            lower(trim(np.location)),
            s.region
        FROM normalized_prices np
        JOIN price_snapshots ps ON ps.id = np.snapshot_id
        JOIN sources s ON s.id = ps.source_id
        WHERE np.location IS NOT NULL AND trim(np.location) <> ''
        ON CONFLICT (org_id, canonical_key) DO NOTHING
        """
    )

    # Link normalized rows to canonical company and location entities.
    op.execute(
        """
        UPDATE normalized_prices AS np
        SET company_id = m.company_id
        FROM (
            SELECT np2.id AS normalized_price_id, c.id AS company_id
            FROM normalized_prices np2
            JOIN price_snapshots ps ON ps.id = np2.snapshot_id
            JOIN sources s ON s.id = ps.source_id
            JOIN companies c
              ON c.org_id = s.org_id
             AND c.canonical_key = lower(trim(np2.source_name))
            WHERE np2.source_name IS NOT NULL
              AND trim(np2.source_name) <> ''
        ) AS m
        WHERE np.id = m.normalized_price_id
          AND np.company_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE normalized_prices AS np
        SET location_id = m.location_id
        FROM (
            SELECT np2.id AS normalized_price_id, l.id AS location_id
            FROM normalized_prices np2
            JOIN price_snapshots ps ON ps.id = np2.snapshot_id
            JOIN sources s ON s.id = ps.source_id
            JOIN locations l
              ON l.org_id = s.org_id
             AND l.canonical_key = lower(trim(np2.location))
            WHERE np2.location IS NOT NULL
              AND trim(np2.location) <> ''
        ) AS m
        WHERE np.id = m.normalized_price_id
          AND np.location_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_normalized_prices_location_id", "normalized_prices", type_="foreignkey")
    op.drop_constraint("fk_normalized_prices_company_id", "normalized_prices", type_="foreignkey")
    op.drop_index("ix_normalized_prices_location_id", table_name="normalized_prices")
    op.drop_index("ix_normalized_prices_company_id", table_name="normalized_prices")
    op.drop_column("normalized_prices", "location_id")
    op.drop_column("normalized_prices", "company_id")

    op.drop_index("ix_locations_company_id", table_name="locations")
    op.drop_index("ix_locations_org_id", table_name="locations")
    op.drop_table("locations")

    op.drop_index("ix_companies_org_id", table_name="companies")
    op.drop_table("companies")
