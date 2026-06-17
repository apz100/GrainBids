import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    commodity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("commodities.id"), nullable=True)
    saved_search_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("saved_searches.id"), nullable=True
    )

    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)  # basis, basis_change, delivered_value
    threshold_value: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    comparison_operator: Mapped[str] = mapped_column(String(10), nullable=False, default=">")
    delivery_months_json: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    notification_channels_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    location: Mapped[str | None] = mapped_column(String(200), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
