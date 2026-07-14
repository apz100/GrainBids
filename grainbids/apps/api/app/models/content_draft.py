import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContentDraft(Base):
    __tablename__ = "content_drafts"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "issue_key",
            "input_fingerprint",
            name="uq_content_drafts_org_issue_fingerprint",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    issue_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    region_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    region_name: Mapped[str] = mapped_column(String(120), nullable=False)
    cadence: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    data_as_of: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(80), nullable=False)
    fact_schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    template_version: Mapped[str] = mapped_column(String(20), nullable=False)
    facts_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    artifacts_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    qa_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
