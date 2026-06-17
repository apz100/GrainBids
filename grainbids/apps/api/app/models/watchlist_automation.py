import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WatchlistAutomation(Base):
    __tablename__ = "watchlist_automations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("watchlists.id"), nullable=False, unique=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    alert_promotion_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    linked_saved_search_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("saved_searches.id"), nullable=True
    )
    linked_alert_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alert_rules.id"), nullable=True
    )
    last_run_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_digest_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
