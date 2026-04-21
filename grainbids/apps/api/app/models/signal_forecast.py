import uuid

from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SignalForecast(Base):
    __tablename__ = "signal_forecasts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    composite_key: Mapped[str] = mapped_column(String(400), nullable=False)
    horizon_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    basis_forecast: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    cash_price_bu_forecast: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    cash_price_mt_forecast: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    confidence_low: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    confidence_high: Mapped[float | None] = mapped_column(Numeric(18, 6), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False, default="baseline-v1")
    generated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
