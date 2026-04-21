import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    adapter_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)

    polling_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    next_poll_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_polled_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ingestion_latency_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    latest_error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
