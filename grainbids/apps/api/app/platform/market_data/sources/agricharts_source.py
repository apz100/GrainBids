"""
Agricharts scraper: single-page version.

Loads https://fmn1.agricharts.com/markets/cash.php once with Playwright,
then walks the Agricharts quote tables to extract all locations / bids.
"""

from __future__ import annotations
from typing import List, Optional

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PWTimeout

from processing import (
    add_mt_cash_price,
    extract_table_to_df,
)

AGRICHARTS_BASE_URL = "https://fmn1.agricharts.com/markets/cash.php"
REQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Words that indicate a header row (not a location title)
HEAD_WORDS = {
    "name",
    "delivery",
    "futures",
    "change",
    "basis",
    "cash",
    "settlement",
    "price",
}


def _extract_all_tables(html: str) -> List[pd.DataFrame]:
    """
    Parse an HTML chunk from cash.php and return one DataFrame per *data* table.

    We only consider tables with class 'homepage_quoteboard'. For each such table:

    - If the FIRST row is a single <th/td colspan=".."> and doesn't contain
      header words, treat it as a LOCATION TITLE row ("Alliston Corn").
      Some layouts use this table purely as a title; others include header
      + data rows in the same table. We handle both.
    - Any table that has a row containing header words like "Name", "Delivery",
      "Futures", etc. is treated as a DATA table. It is tagged with the most
      recent location title we saw.
    """
    soup = BeautifulSoup(html, "lxml")

    tables = soup.select("table.homepage_quoteboard")
    dfs: List[pd.DataFrame] = []

    print(f"[DEBUG] Agricharts: scanning {len(tables)} homepage_quoteboard tables in one HTML chunk")

    current_location: Optional[str] = None

    for idx, tbl in enumerate(tables, start=1):
        rows = tbl.find_all("tr")
        if not rows:
            continue

        # ----- 1) Check the first row for a title cell -----------------------
        first_cells = rows[0].find_all(["td", "th"])
        first_text = first_cells[0].get_text(" ", strip=True) if first_cells else ""
        first_text_lower = first_text.lower() if first_text else ""

        has_title_shape = (
            len(first_cells) == 1
            and first_cells[0].has_attr("colspan")
            and first_text
            and not any(hw in first_text_lower for hw in HEAD_WORDS)
        )

        # We'll also scan rows for header-like content
        all_rows_text_lower = " ".join(
            r.get_text(" ", strip=True).lower() for r in rows
        )
        has_header_words = any(hw in all_rows_text_lower for hw in HEAD_WORDS)

        # Case A: pure TITLE table (e.g. just "Alliston Corn")
        if has_title_shape and not has_header_words:
            current_location = first_text
            print(f"[DEBUG] Agricharts: title table -> '{current_location}'")
            # No actual data in this table
            continue

        # Case B: combined TITLE + DATA table
        if has_title_shape and has_header_words:
            current_location = first_text
            print(f"[DEBUG] Agricharts: combined title+data table -> '{current_location}'")
            # fall through and treat same table as a data table below

        # Case C: data-only table with header words but no explicit title
        if not has_header_words:
            # Neither title nor data we care about
            continue

        # At this point, tbl should be a DATA table.
        try:
            df = extract_table_to_df(str(tbl))
        except Exception as e:
            print(f"[DEBUG] Agricharts: data table {idx} skipped in extract_table_to_df: {e}")
            continue

        if df is None or df.empty:
            continue

        location_name = current_location or f"Location_{idx}"

        try:
            df.insert(0, "Location", location_name)
            df = add_mt_cash_price(df)
        except Exception as e:
            print(f"[DEBUG] Agricharts: data table {idx} skipped in add_mt_cash_price: {e}")
            continue

        dfs.append(df)

    total_rows = sum(len(d) for d in dfs)
    print(f"[DEBUG] Agricharts: extracted {total_rows} rows from {len(dfs)} data tables")
    return dfs


def fetch_agricharts_bids(playwright, limit_locations: Optional[int] = None) -> pd.DataFrame:
    """
    Single-shot scraper: render AGRICHARTS_BASE_URL once, parse all locations/tables.

    `limit_locations` is kept just for API compatibility with older code but is ignored
    in this single-page implementation.
    """
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(user_agent=REQ_HEADERS["User-Agent"])
    page = context.new_page()

    page.goto(AGRICHARTS_BASE_URL, wait_until="domcontentloaded", timeout=45000)

    try:
        page.wait_for_selector("table.homepage_quoteboard", timeout=15000)
    except PWTimeout:
        print("[DEBUG] Agricharts: no homepage_quoteboard tables found in main doc within timeout")

    # Small extra delay to let JS finish if needed
    page.wait_for_timeout(3000)

    all_dfs: List[pd.DataFrame] = []

    # 1) Main document
    html_main = page.content()
    all_dfs.extend(_extract_all_tables(html_main))

    # 2) All frames (DTN/Barchart sometimes uses iframes)
    for fr in page.frames:
        try:
            html_fr = fr.content()
        except Exception as e:
            print(f"[DEBUG] Agricharts: frame content() failed: {e}")
            continue
        all_dfs.extend(_extract_all_tables(html_fr))

    context.close()
    browser.close()

    if not all_dfs:
        return pd.DataFrame()

    result = pd.concat(all_dfs, ignore_index=True)

    # Optional: drop duplicates, since frames + main doc may overlap.
    result = result.drop_duplicates(
        subset=["Location", "Name", "Delivery", "Delivery End", "Futures Month", "Futures Price"],
        keep="first",
    )

    return result
