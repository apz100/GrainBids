from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, require_admin
from app.db.session import get_db
from app.models.content_draft import ContentDraft


router = APIRouter(prefix="/api/content-drafts", tags=["content-drafts"])


@router.get("")
def list_content_drafts(
    region: str | None = Query(None),
    cadence: str | None = Query(None, pattern="^(daily|weekly)$"),
    status: str | None = Query(None, pattern="^(draft|draft_needs_review|blocked)$"),
    limit: int = Query(50, ge=1, le=200),
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    query = select(ContentDraft).where(ContentDraft.org_id == context.org_id)
    if region:
        query = query.where(ContentDraft.region_key == region.strip())
    if cadence:
        query = query.where(ContentDraft.cadence == cadence)
    if status:
        query = query.where(ContentDraft.status == status)
    rows = db.execute(query.order_by(desc(ContentDraft.generated_at)).limit(limit)).scalars().all()
    return {"rows": [_serialize_summary(row) for row in rows], "count": len(rows)}


@router.get("/{draft_id}")
def get_content_draft(
    draft_id: uuid.UUID,
    context: RequestContext = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    row = db.execute(
        select(ContentDraft).where(ContentDraft.id == draft_id, ContentDraft.org_id == context.org_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="content draft not found")
    return {
        **_serialize_summary(row),
        "facts": row.facts_json,
        "artifacts": row.artifacts_json,
        "qa": row.qa_json,
        "error_message": row.error_message,
    }


def _serialize_summary(row: ContentDraft) -> dict[str, object]:
    return {
        "id": str(row.id),
        "issue_key": row.issue_key,
        "region_key": row.region_key,
        "region_name": row.region_name,
        "cadence": row.cadence,
        "status": row.status,
        "data_as_of": row.data_as_of.isoformat() if row.data_as_of else None,
        "generated_at": row.generated_at.isoformat(),
        "input_fingerprint": row.input_fingerprint,
        "fact_schema_version": row.fact_schema_version,
        "template_version": row.template_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
