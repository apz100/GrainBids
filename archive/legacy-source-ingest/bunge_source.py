"""
Bunge cash bid scraper.

Loads each location page and extracts the main cash-bids table.
Uses networkidle + extra wait to allow JS-rendered tables to populate.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PWTimeout

from processing import add_mt_cash_price, extract_table_to_df, pick_cash_table_html

# Map location URL -> friendly label
BUNGE_LOCATIONS: Dict[str, str] = {
    "https://www.bungeag.com/locations/altona-mb/":   "Bunge - Altona MB",
    "https://www.bungeag.com/locations/hamilton-on/": "Bunge - Hamilton ON",
    "https://www.bungeag.com/locations/harrowby-mb/": "Bunge - Harrowby MB",
    "https://www.bungeag.com/locations/morden-mb/":   "Bunge - Morden MB",
}

# Minimum number of columns a table must have to be considered a bid table
_MIN_COLS = 3

# Keywords that must appear somewhere in a table's headers/cells to qualify
_BID_KEYWORDS = {"basis", "cash", "price", "delivery", "futures", "bushel", "tonne"}


def _score_table(soup_tbl) -> int:
    """Score a BeautifulSoup <table> by how many bid-related keywords it contains."""
    text = soup_tbl.get_text(" ", strip=True).lower()
    return sum(1 for kw in _BID_KEYWORDS if kw in text)


def _best_table_html(html: str) -> str | None:
    """Return the outerHTML of the most bid-like table, or None."""
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    if not tables:
        return None

    # First try the scored picker from processing.py
    scored = pick_cash_table_html(html)
    if scored:
        return scored

    # Fallback: pick the table with the most bid-related keywords and enough columns
    best = None
    best_score = 0
    for tbl in tables:
        rows = tbl.find_all("tr")
        if not rows:
            continue
        max_cols = max(len(r.find_all(["td", "th"])) for r in rows)
        if max_cols < _MIN_COLS:
            continue
        sc = _score_table(tbl)
        if sc > best_score:
            best_score = sc
            best = tbl

    return str(best) if best and best_score > 0 else None


def _parse_html(html: str, location_name: str) -> pd.DataFrame:
    tbl_html = _best_table_html(html)
    if not tbl_html:
        return pd.DataFrame()
    df = extract_table_to_df(tbl_html)
    if df.empty:
        return pd.DataFrame()
    df.insert(0, "Location", location_name)
    df = add_mt_cash_price(df)
    return df


def fetch_bunge_all(playwright) -> pd.DataFrame:
    """
    Render each Bunge location page with Playwright and parse the bids table.
    Uses networkidle + extra wait to handle JS-rendered cash bid widgets.
    """
    all_rows: List[pd.DataFrame] = []
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        )
    )
    page = context.new_page()

    for url, label in BUNGE_LOCATIONS.items():
        try:
            # networkidle ensures the JS bid widget has fired its requests
            page.goto(url, wait_until="networkidle", timeout=60_000)

            # Give any post-load JS (iframes, lazy widgets) time to render
            page.wait_for_timeout(5_000)

            # Try main page first
            try:
                page.wait_for_selector("table", timeout=10_000)
                html = page.content()
                df = _parse_html(html, label)
                if df is not None and not df.empty:
                    all_rows.append(df)
                    print(f"[BUNGE OK] {label}: {len(df)} rows")
                    continue
            except PWTimeout:
                pass

            # Try iframes (some Bunge pages embed the bid widget in an iframe)
            found = False
            for fr in page.frames:
                if fr == page.main_frame:
                    continue
                try:
                    fr.wait_for_selector("table", timeout=8_000)
                    html = fr.content()
                    df = _parse_html(html, label)
                    if df is not None and not df.empty:
                        all_rows.append(df)
                        print(f"[BUNGE OK] {label}: {len(df)} rows (iframe)")
                        found = True
                        break
                except PWTimeout:
                    continue

            if not found:
                # Last attempt: dump full page source and try parsing anyway
                html = page.content()
                df = _parse_html(html, label)
                if df is not None and not df.empty:
                    all_rows.append(df)
                    print(f"[BUNGE OK] {label}: {len(df)} rows (full-page fallback)")
                else:
                    print(f"[BUNGE WARN] {label}: no rendered bids table found")

        except Exception as e:
            print(f"[BUNGE ERR] {label}: {e}")

    context.close()
    browser.close()

    if not all_rows:
        return pd.DataFrame()
    return pd.concat(all_rows, ignore_index=True)
