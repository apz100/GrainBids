import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SourceHealthSnapshot(Base):
    __tablename__ = "source_health_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False)
    captured_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ingestion_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_success_rate: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    stale_age_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schema_drift_incidents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
