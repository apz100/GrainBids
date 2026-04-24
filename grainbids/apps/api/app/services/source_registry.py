from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import sys
from typing import Callable

import pandas as pd

from app.platform.market_data.service import get_sources_path


@dataclass(frozen=True)
class SourceAdapter:
    key: str
    module: str
    function: str
    mode: str
    source_class: str
    default_poll_minutes: int
    default_timeout_seconds: int


ADAPTERS: dict[str, SourceAdapter] = {
    "agricharts": SourceAdapter("agricharts", "agricharts_source", "fetch_agricharts_bids", "playwright", "scraper", 15, 90),
    "andersons": SourceAdapter("andersons", "andersons_source", "fetch_andersons_all", "direct", "api", 10, 60),
    "bunge": SourceAdapter("bunge", "bunge_source", "fetch_bunge_all", "playwright", "scraper", 15, 90),
    "dg_global": SourceAdapter("dg_global", "dg_global_source", "fetch_dg_global", "playwright", "scraper", 15, 90),
    "ganaraska": SourceAdapter("ganaraska", "ganaraska_source", "fetch_ganaraska", "playwright", "scraper", 15, 90),
    "glg": SourceAdapter("glg", "glg_source", "fetch_glg_all", "playwright", "scraper", 15, 90),
    "hensall": SourceAdapter("hensall", "hensall_source", "fetch_hensall", "playwright", "scraper", 15, 90),
    "lac": SourceAdapter("lac", "lac_source", "fetch_lac_all", "playwright", "scraper", 15, 90),
    "snobelen": SourceAdapter("snobelen", "snobelen_source", "fetch_snobelen_all", "playwright", "scraper", 15, 90),
    "wanstead": SourceAdapter("wanstead", "wanstead_source", "fetch_wanstead_all", "playwright", "scraper", 15, 90),
}
PILOT_ADAPTER_KEYS = ("agricharts", "glg", "hensall", "snobelen", "andersons")


def list_adapters() -> list[SourceAdapter]:
    return [ADAPTERS[key] for key in sorted(ADAPTERS.keys())]


def list_pilot_adapter_keys() -> list[str]:
    return [key for key in PILOT_ADAPTER_KEYS if key in ADAPTERS]


def get_adapter(key: str) -> SourceAdapter:
    normalized = key.strip().lower()
    if normalized not in ADAPTERS:
        raise KeyError(f"Unsupported source adapter '{key}'")
    return ADAPTERS[normalized]


def fetch_with_adapter(adapter: SourceAdapter) -> pd.DataFrame:
    _ensure_sources_path_on_sys_path()
    fetch_fn = _load_fetch_fn(adapter)
    result = fetch_fn()
    if result is None:
        return pd.DataFrame()
    if isinstance(result, pd.DataFrame):
        return result
    raise TypeError(f"Unexpected adapter output type for {adapter.key}: {type(result)!r}")


def _ensure_sources_path_on_sys_path() -> None:
    path = get_sources_path()
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _load_fetch_fn(adapter: SourceAdapter) -> Callable[[], pd.DataFrame]:
    module = import_module(f"app.platform.market_data.sources.{adapter.module}")
    target = getattr(module, adapter.function)

    if adapter.mode == "direct":
        return target

    if adapter.mode == "playwright":
        def _runner() -> pd.DataFrame:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                return target(playwright)

        return _runner

    raise ValueError(f"Unsupported adapter mode: {adapter.mode}")
