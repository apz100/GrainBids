from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.raw_upload import RawUpload
from app.services.upload_csv import process_csv_upload


router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.get("")
def list_uploads(
    source_id: uuid.UUID | None = None,
    limit: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query: Select[tuple[RawUpload]] = select(RawUpload)
    if source_id is not None:
        query = query.where(RawUpload.source_id == source_id)

    rows = db.execute(query.order_by(desc(RawUpload.uploaded_at)).limit(limit)).scalars().all()

    return {
        "rows": [
            {
                "id": str(row.id),
                "source_id": str(row.source_id),
                "snapshot_id": str(row.snapshot_id) if row.snapshot_id else None,
                "file_name": row.file_name,
                "content_type": row.content_type,
                "file_size_bytes": row.file_size_bytes,
                "row_count": row.row_count,
                "status": row.status,
                "error_message": row.error_message,
                "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
                "column_mapping": row.column_mapping,
                "raw_headers": row.raw_headers,
            }
            for row in rows
        ]
    }


@router.post("/csv")
async def upload_csv(
    source_id: uuid.UUID = Form(...),
    commodity_id: uuid.UUID = Form(...),
    captured_at: datetime | None = Form(None),
    column_map_json: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="only .csv files are supported")

    mapping_override = None
    if column_map_json:
        try:
            parsed = json.loads(column_map_json)
            if not isinstance(parsed, dict):
                raise ValueError("column_map_json must be an object")
            mapping_override = {str(k): str(v) for k, v in parsed.items()}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid column_map_json: {exc}") from exc

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="uploaded file is empty")

    try:
        result = process_csv_upload(
            db,
            source_id=source_id,
            commodity_id=commodity_id,
            file_name=file.filename,
            content_type=file.content_type,
            payload=payload,
            captured_at=captured_at,
            column_mapping_override=mapping_override,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "upload_id": str(result.upload_id),
        "snapshot_id": str(result.snapshot_id),
        "inserted_rows": result.inserted_rows,
        "headers": result.headers,
        "mapping": result.mapping,
    }
