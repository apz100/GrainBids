# snobelen_source.py

"""
Snobelen Farms cash bid scraper – via Playwright.

We hit the same feed.php URLs the browser uses and parse the
<table class="DataGrid"> blocks into Ontario_CashBids-style rows.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
from bs4 import BeautifulSoup

# Map of feed URL -> friendly location name
SNOBELEN_FEEDS: Dict[str, str] = {
    "https://snobelenfarms.com/wp-content/plugins/mv_blocks/blocks/dtn/feed.php?commodity=all&location=R,%20L,%20D,%20B,%20T,%20L(B)":
        "Snobelen - Northern Locations",
    "https://snobelenfarms.com/wp-content/plugins/mv_blocks/blocks/dtn/feed.php?commodity=all&location=Brantford":
        "Snobelen - Brantford",
}


def _parse_datagrid_table(tbl, location_name: str) -> pd.DataFrame:
    """
    Parse one <table class="DataGrid"> block into normalized rows.

    Expected shape (per commodity):

        <caption>CORN</caption>
        <thead>
          <tr>
            <th></th>
            <th>2025 Crop</th>
            <th>2026 Crop</th>
            <th>2027 Crop</th>
          </tr>
        </thead>
        <tbody>
          <tr>Futures Month ...</tr>
          <tr>Futures ...</tr>
          <tr>Basis ...</tr>
          <tr>CDN Cash (Bushels) ...</tr>
          <tr>Futures Change ...</tr>
          <tr>Converted Price (Tonnes) ...</tr>
        </tbody>
    """
    rows = tbl.find_all("tr")
    if not rows:
        return pd.DataFrame()

    # Header row: ["", "2025 Crop", "2026 Crop", ...]
    header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    if len(header_cells) < 2:
        return pd.DataFrame()
    crop_cols = header_cells[1:]  # skip first blank header

    labels: Dict[str, List[str] | None] = {
        "Futures Month": None,
        "Futures": None,
        "Basis": None,
        "CDN Cash (Bushels)": None,
        "Futures Change": None,
        "Converted Price (Tonnes)": None,
    }

    # Map row label -> values
    for r in rows[1:]:
        cells = r.find_all(["th", "td"])
        if not cells:
            continue

        label = cells[0].get_text(strip=True)
        values = [c.get_text(strip=True) for c in cells[1:]]

        for key in list(labels.keys()):
            if key.lower() in label.lower():
                labels[key] = values
                break

    n = len(crop_cols)
    out_rows: List[dict] = []

    caption_text = tbl.caption.get_text(strip=True) if tbl.caption else ""
    commodity_name = caption_text or "Snobelen"

    for i in range(n):
        out_rows.append(
            {
                "Location": location_name,
                "Name": commodity_name,
                "Delivery": crop_cols[i],
                "Delivery End": "",
                "Futures Month": (labels["Futures Month"][i] if labels["Futures Month"] else ""),
                "Futures Price": (labels["Futures"][i] if labels["Futures"] else ""),
                "Basis": (labels["Basis"][i] if labels["Basis"] else ""),
                "Bushel Cash Price": (
                    labels["CDN Cash (Bushels)"][i] if labels["CDN Cash (Bushels)"] else ""
                ),
                "Change": (labels["Futures Change"][i] if labels["Futures Change"] else ""),
                "MT Cash Price": (
                    labels["Converted Price (Tonnes)"][i]
                    if labels["Converted Price (Tonnes)"]
                    else ""
                ),
            }
        )

    return pd.DataFrame(out_rows)


def fetch_snobelen_all(playwright) -> pd.DataFrame:
    """
    Fetch and combine all Snobelen locations using the provided Playwright instance.
    """
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    all_frames: List[pd.DataFrame] = []

    try:
        for url, loc_name in SNOBELEN_FEEDS.items():
            try:
                page.goto(url, wait_until="load", timeout=60_000)
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")
                tables = soup.find_all("table", class_="DataGrid")

                if not tables:
                    print(f"[SNOBELEN WARN] {loc_name}: no DataGrid tables found")
                    continue

                loc_rows = []
                for tbl in tables:
                    df_tbl = _parse_datagrid_table(tbl, loc_name)
                    if not df_tbl.empty:
                        loc_rows.append(df_tbl)

                if loc_rows:
                    df_loc = pd.concat(loc_rows, ignore_index=True)
                    all_frames.append(df_loc)
                    print(f"[SNOBELEN OK] {loc_name}: {len(df_loc)} rows")
                else:
                    print(f"[SNOBELEN WARN] {loc_name}: parsed 0 rows")

            except Exception as e:
                print(f"[SNOBELEN ERR] {loc_name}: {e}")

    finally:
        context.close()
        browser.close()

    if not all_frames:
        return pd.DataFrame()

    return pd.concat(all_frames, ignore_index=True)
