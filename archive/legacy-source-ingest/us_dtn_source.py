# us_dtn_source.py
"""
Generic scraper for US grain elevators using the DTN CashBidTable widget.

These sites embed a widget configured like:
    const tableOptions = {
        targetID: "target",
        companyID: 22641,
        ...
    };
    CashBidTable(tableOptions);

The widget renders asynchronously via JavaScript, so Playwright is required.
After rendering, the widget produces an HTML table inside #target (or similar)
which we extract with BeautifulSoup.

Usage (called by GrainBidder.py via the [[us.elevators]] config):
    fetch_us_dtn(url, company_name, playwright) -> pd.DataFrame
"""

from __future__ import annotations

import re
import time
from typing import Optional

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PWTimeout

_BU_PER_MT = {
    "corn":      39.3683,
    "soybeans":  36.7437,
    "soybean":   36.7437,
    "wheat":     36.7437,
    "milo":      39.3683,
    "sorghum":   39.3683,
    "ethanol":   39.3683,  # ethanol plants use corn
}

_HEADERS_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)

# Column name normalisation: maps common DTN table header variants → internal names
_COL_MAP = {
    "commodity":      "Name",
    "name":           "Name",
    "grain":          "Name",
    "location":       "Sub-Location",
    "elevator":       "Sub-Location",
    "site":           "Sub-Location",
    "delivery":       "Delivery",
    "delivery start": "Delivery",
    "delivery end":   "Delivery End",
    "futures":        "Futures Price",
    "futures price":  "Futures Price",
    "futures month":  "Futures Month",
    "month":          "Futures Month",
    "contract":       "Futures Month",
    "change":         "Change",
    "basis":          "Basis",
    "cash":           "Bushel Cash Price",
    "cash price":     "Bushel Cash Price",
    "cash bid":       "Bushel Cash Price",
    "price":          "Bushel Cash Price",
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to internal standard names using _COL_MAP."""
    rename = {}
    for col in df.columns:
        key = col.strip().lower().rstrip("*").strip()
        if key in _COL_MAP:
            rename[col] = _COL_MAP[key]
    return df.rename(columns=rename)


def _parse_cash_table(html: str, company_name: str) -> pd.DataFrame:
    """Extract all bid tables from rendered HTML and return a normalised DataFrame."""
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    if not tables:
        return pd.DataFrame()

    all_rows: list[pd.DataFrame] = []
    for tbl in tables:
        try:
            df = pd.read_html(str(tbl), flavor="lxml")[0]
        except Exception:
            continue
        if df.empty or len(df.columns) < 3:
            continue
        df = df.dropna(how="all").reset_index(drop=True)
        df = _normalize_columns(df)
        all_rows.append(df)

    if not all_rows:
        return pd.DataFrame()

    combined = pd.concat(all_rows, ignore_index=True)

    # Ensure required columns exist
    for col in ["Name", "Delivery", "Delivery End", "Futures Month",
                "Futures Price", "Change", "Basis", "Bushel Cash Price"]:
        if col not in combined.columns:
            combined[col] = ""

    combined["Location"] = company_name

    # Attempt MT cash price from Bushel Cash Price if not present
    if "MT Cash Price" not in combined.columns:
        def _to_mt(row: pd.Series) -> str:
            try:
                price_str = str(row.get("Bushel Cash Price", "")).replace("$", "").strip()
                price_bu  = float(price_str)
                commodity = str(row.get("Name", "")).lower()
                bpu = _BU_PER_MT.get(commodity, 39.3683)
                return str(round(price_bu * bpu, 2))
            except Exception:
                return ""
        combined["MT Cash Price"] = combined.apply(_to_mt, axis=1)

    # Reorder to standard column set
    keep = [c for c in [
        "Location", "Name", "Delivery", "Delivery End",
        "Futures Month", "Futures Price", "Change", "Basis",
        "Bushel Cash Price", "MT Cash Price",
    ] if c in combined.columns]
    return combined[keep]


def fetch_us_dtn(url: str, company_name: str, playwright) -> pd.DataFrame:
    """
    Scrape a US elevator page powered by the DTN CashBidTable widget.

    Args:
        url:          Cash bids page URL
        company_name: Display name for Location column
        playwright:   Playwright instance from sync_playwright context

    Returns:
        Normalised DataFrame.
    """
    try:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_HEADERS_UA)
        page    = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=60_000)
        except PWTimeout:
            # networkidle can time out on heavy pages; proceed anyway
            pass

        # Wait for the DTN widget to render — it injects into a #target div
        # or any div containing a table with bid data
        rendered = False
        for selector in ["#target table", ".cash-bid-table table", "table"]:
            try:
                page.wait_for_selector(selector, timeout=15_000)
                rendered = True
                break
            except PWTimeout:
                continue

        if not rendered:
            print(f"[US-DTN WARN] {company_name}: table did not appear after waiting")

        # Give any pending JS renders a moment to settle
        page.wait_for_timeout(3_000)
        html = page.content()

        context.close()
        browser.close()

        df = _parse_cash_table(html, company_name)
        if df.empty:
            print(f"[US-DTN WARN] {company_name}: no bid table found in rendered page")
            return pd.DataFrame()

        print(f"[US-DTN OK] {company_name}: {len(df)} rows")
        return df

    except Exception as e:
        print(f"[US-DTN ERR] {company_name}: {e}")
        return pd.DataFrame()
