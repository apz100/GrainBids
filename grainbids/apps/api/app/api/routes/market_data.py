from __future__ import annotations

from dataclasses import asdict
import io
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.market_data import (
    fetch_source_dataframe,
    get_sources_path_info,
    list_supported_sources,
    refresh_source,
)
from app.services.upload_csv import process_csv_upload


router = APIRouter(prefix="/api/market-data", tags=["market-data"])


@router.get("/sources")
def list_market_sources():
    return get_sources_path_info()


@router.get("/adapters")
def list_market_adapters():
    return {"rows": list_supported_sources()}


@router.post("/refresh")
def refresh_market_source(
    source: str = Query(..., description="Source key, e.g. agricharts, glg, bunge"),
    persist: bool = Query(False, description="Persist fetched rows through the standard normalization pipeline"),
    source_id: uuid.UUID | None = Query(None, description="Required when persist=true"),
    commodity_id: uuid.UUID | None = Query(None, description="Required when persist=true"),
    db: Session = Depends(get_db),
):
    try:
        if not persist:
            result = refresh_source(source)
            return {"result": asdict(result), "persisted": None}

        if source_id is None or commodity_id is None:
            raise HTTPException(status_code=400, detail="source_id and commodity_id are required when persist=true")

        started = time.perf_counter()
        df = fetch_source_dataframe(source)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if df.empty:
            raise HTTPException(status_code=400, detail="source returned no rows")

        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        upload = process_csv_upload(
            db,
            source_id=source_id,
            commodity_id=commodity_id,
            file_name=f"{source.strip().lower()}_refresh.csv",
            content_type="text/csv",
            payload=buffer.getvalue().encode("utf-8"),
        )

        return {
            "result": {
                "source": source.strip().lower(),
                "row_count": int(len(df.index)),
                "columns": [str(col) for col in df.columns.tolist()],
                "duration_ms": duration_ms,
            },
            "persisted": {
                "upload_id": str(upload.upload_id),
                "snapshot_id": str(upload.snapshot_id),
                "inserted_rows": upload.inserted_rows,
                "mapping": upload.mapping,
            },
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Refresh failed: {exc}") from exc
