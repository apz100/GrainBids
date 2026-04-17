import uuid

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False)
    commodity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("commodities.id"), nullable=False)

    captured_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    futures_month: Mapped[str | None] = mapped_column(String(50), nullable=True)
    futures_price: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    basis: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    cash_price_bu: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    cash_price_mt: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)

    delivery_start: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delivery_end: Mapped[str | None] = mapped_column(String(50), nullable=True)

    raw_payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
