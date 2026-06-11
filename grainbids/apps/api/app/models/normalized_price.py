import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NormalizedPrice(Base):
    __tablename__ = "normalized_prices"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "composite_key", name="uq_normalized_prices_snapshot_key"),
        Index(
            "ix_normalized_prices_snapshot_company_location_market",
            "snapshot_id",
            "company_id",
            "location_id",
            "commodity_name",
            "delivery_end",
            "futures_month",
        ),
        Index("ix_normalized_prices_is_canonical", "is_canonical"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("price_snapshots.id"), nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("locations.id"), nullable=True)

    location: Mapped[str] = mapped_column(String(200), nullable=False)
    commodity_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    delivery_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    delivery_start: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delivery_end: Mapped[str | None] = mapped_column(String(50), nullable=True)

    futures_month: Mapped[str | None] = mapped_column(String(50), nullable=True)
    futures_price: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    futures_change: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    basis: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    cash_price_bu: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    cash_price_mt: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)

    basis_change: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    basis_change_strict: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    basis_last_changed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cash_price_bu_change: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    cash_price_mt_change: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    is_canonical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    canonical_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    canonical_reason: Mapped[str | None] = mapped_column(String(250), nullable=True)
    composite_key: Mapped[str] = mapped_column(String(400), nullable=False)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
