from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

import pandas as pd

from app.platform.market_data.service import get_sources_path
from app.services.source_registry import fetch_with_adapter, get_adapter, list_adapters


def fetch_source_dataframe(source: str) -> pd.DataFrame:
    adapter = get_adapter(source)
    return fetch_with_adapter(adapter)


def list_supported_sources() -> list[str]:
    return [adapter.key for adapter in list_adapters()]


@dataclass
class RefreshResult:
    source: str
    row_count: int
    columns: list[str]
    duration_ms: int


def refresh_source(source: str) -> RefreshResult:
    normalized = source.strip().lower()
    started = time.perf_counter()
    df = fetch_source_dataframe(normalized)
    duration_ms = int((time.perf_counter() - started) * 1000)

    return RefreshResult(
        source=normalized,
        row_count=int(len(df.index)),
        columns=[str(col) for col in df.columns.tolist()],
        duration_ms=duration_ms,
    )


def get_sources_path_info() -> dict[str, Any]:
    path = get_sources_path()
    return {
        "path": str(path),
        "exists": path.exists(),
        "available_sources": list_supported_sources(),
    }
