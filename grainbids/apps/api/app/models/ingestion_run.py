import uuid

from sqlalchemy import BigInteger, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_identifier: Mapped[str] = mapped_column(String(1000), nullable=False)

    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    attempt_number: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    max_attempts: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    raw_row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    normalized_row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_alert_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    deduped_alert_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duplicate_key_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rejected_row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    missing_required_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    row_reject_reasons_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    parse_success_rate: Mapped[float | None] = mapped_column(Numeric(6, 3), nullable=True)
    schema_drift_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
