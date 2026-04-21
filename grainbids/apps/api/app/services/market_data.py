from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
import sys
import time
from typing import Any

import pandas as pd
from playwright.sync_api import sync_playwright

from app.platform.market_data.service import get_sources_path


@dataclass
class RefreshResult:
    source: str
    row_count: int
    columns: list[str]
    duration_ms: int


SOURCE_SPECS: dict[str, dict[str, str]] = {
    "agricharts": {"module": "agricharts_source", "function": "fetch_agricharts_bids", "mode": "playwright"},
    "andersons": {"module": "andersons_source", "function": "fetch_andersons_all", "mode": "direct"},
    "bunge": {"module": "bunge_source", "function": "fetch_bunge_all", "mode": "playwright"},
    "dg_global": {"module": "dg_global_source", "function": "fetch_dg_global", "mode": "playwright"},
    "ganaraska": {"module": "ganaraska_source", "function": "fetch_ganaraska", "mode": "playwright"},
    "glg": {"module": "glg_source", "function": "fetch_glg_all", "mode": "playwright"},
    "hensall": {"module": "hensall_source", "function": "fetch_hensall", "mode": "playwright"},
    "lac": {"module": "lac_source", "function": "fetch_lac_all", "mode": "playwright"},
    "snobelen": {"module": "snobelen_source", "function": "fetch_snobelen_all", "mode": "playwright"},
    "wanstead": {"module": "wanstead_source", "function": "fetch_wanstead_all", "mode": "playwright"},
}


def _ensure_sources_path_on_sys_path() -> Path:
    path = get_sources_path()
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    return path


def list_supported_sources() -> list[str]:
    return sorted(SOURCE_SPECS.keys())


def _execute_source(spec: dict[str, str]) -> pd.DataFrame:
    module_name = spec["module"]
    function_name = spec["function"]
    mode = spec["mode"]

    module = import_module(f"app.platform.market_data.sources.{module_name}")
    fetch_fn = getattr(module, function_name)

    if mode == "direct":
        result = fetch_fn()
    elif mode == "playwright":
        with sync_playwright() as playwright:
            result = fetch_fn(playwright)
    else:
        raise ValueError(f"Unsupported source execution mode: {mode}")

    if result is None:
        return pd.DataFrame()
    if isinstance(result, pd.DataFrame):
        return result

    raise TypeError(f"Unexpected result type from {module_name}.{function_name}: {type(result)!r}")


def fetch_source_dataframe(source: str) -> pd.DataFrame:
    normalized = source.strip().lower()
    if normalized not in SOURCE_SPECS:
        raise KeyError(f"Unsupported source '{source}'. Supported values: {', '.join(list_supported_sources())}")

    _ensure_sources_path_on_sys_path()
    return _execute_source(SOURCE_SPECS[normalized])


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
    path = _ensure_sources_path_on_sys_path()
    return {
        "path": str(path),
        "exists": path.exists(),
        "available_sources": list_supported_sources(),
    }
