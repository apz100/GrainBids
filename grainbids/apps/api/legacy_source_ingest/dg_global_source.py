# dg_global_source.py
"""
DG Global cash bid scraper.

Uses Playwright to grab the cash-bids tables and normalizes them to:

Location | Name | Delivery | Delivery End | Futures Month | Futures Price
Change | Basis | Bushel Cash Price | MT Cash Price
"""

from __future__ import annotations

from typing import List, Dict

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PWTimeout

DG_GLOBAL_URL = "https://dgglobal.ca/cash-bids"
DG_GLOBAL_LABEL = "DG Global"


def _html_table_to_df(html: str) -> pd.DataFrame:
    """
    Manually parse a single HTML <table> into a DataFrame.

    Expected headers (or close to):
      Type | Delivery Period | Destination | Future Month | Futures
      | Change | Basis | Price ($/BU) | Price ($/MT) | Price (Flat)
    """
    soup = BeautifulSoup(html, "html.parser")
    tbl = soup.find("table")
    if not tbl:
        return pd.DataFrame()

    thead = tbl.find("thead")
    if not thead:
        return pd.DataFrame()
    header_cells = thead.find_all("th")
    headers = [th.get_text(strip=True) for th in header_cells]
    if not headers:
        return pd.DataFrame()

    tbody = tbl.find("tbody")
    if not tbody:
        return pd.DataFrame()

    rows = []
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        vals = [td.get_text(strip=True) for td in tds]
        if len(vals) < len(headers):
            continue
        vals = vals[: len(headers)]
        if all(v == "" for v in vals):
            continue
        rows.append(dict(zip(headers, vals)))

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def _normalize_dg_df(df_raw: pd.DataFrame, commodity_name: str) -> pd.DataFrame:
    """
    Map DG Global headers into the standard Ontario_CashBids schema.
    """
    if df_raw.empty:
        return df_raw

    df = df_raw.copy()
    df = df.dropna(how="all")

    cols_lower = {c.lower(): c for c in df.columns}

    def pick(*candidates: str) -> str | None:
        for cand in candidates:
            cl = cand.lower()
            if cl in cols_lower:
                return cols_lower[cl]
        for c in df.columns:
            cl = c.lower()
            for cand in candidates:
                if cand.lower() in cl:
                    return c
        return None

    dest_col = pick("destination")
    deliv_col = pick("delivery period", "delivery")
    futm_col = pick("future month", "futures month")
    futp_col = pick("futures")
    change_col = pick("change")
    basis_col = pick("basis")
    cash_bu_col = pick("price ($/bu)", "price/bu", "price bu")
    mt_col = pick("price ($/mt)", "price/mt", "price (mt)")

    out = pd.DataFrame()

    # Location = destination (elevator location); fall back to label
    if dest_col:
        out["Location"] = df[dest_col]
    else:
        out["Location"] = DG_GLOBAL_LABEL

    out["Name"] = commodity_name or DG_GLOBAL_LABEL

    out["Delivery"] = df[deliv_col] if deliv_col else ""
    out["Delivery End"] = ""

    out["Futures Month"] = df[futm_col] if futm_col else ""
    out["Futures Price"] = df[futp_col] if futp_col else ""

    out["Change"] = df[change_col] if change_col else ""
    out["Basis"] = df[basis_col] if basis_col else ""

    out["Bushel Cash Price"] = df[cash_bu_col] if cash_bu_col else ""
    out["MT Cash Price"] = df[mt_col] if mt_col else ""

    return out


def fetch_dg_global(playwright) -> pd.DataFrame:
    """
    Load the DG Global cash-bids page with Playwright and parse all
    commodity tables (Corn, Soybeans, etc.).
    """
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    all_frames: List[pd.DataFrame] = []

    try:
        page.goto(DG_GLOBAL_URL, wait_until="domcontentloaded", timeout=60_000)

        # Let Vue app render
        page.wait_for_timeout(5_000)

        try:
            # Grab all main tables and their nearest commodity heading.
            items: List[Dict[str, str]] = page.eval_on_selector_all(
                "main table",
                """
                els => els.map(el => {
                    let name = "";
                    let container = el.parentElement;
                    let depth = 0;
                    while (container && depth < 5 && !name) {
                        const h = container.querySelector("h1,h2,h3");
                        if (h) name = h.textContent.trim();
                        container = container.parentElement;
                        depth++;
                    }
                    return {
                        name,
                        html: el.outerHTML
                    };
                })
                """,
            )
        except PWTimeout:
            print("[DG GLOBAL WARN] no tables found (timeout)")
            return pd.DataFrame()

        if not items:
            print("[DG GLOBAL WARN] no tables found on DG Global page")
            return pd.DataFrame()

        for item in items:
            html = (item.get("html") or "").strip()
            commodity_name = (item.get("name") or "").strip()
            if not html:
                continue

            df_tbl = _html_table_to_df(html)
            if df_tbl is None or df_tbl.empty:
                continue

            df_norm = _normalize_dg_df(df_tbl, commodity_name)
            if not df_norm.empty:
                all_frames.append(df_norm)

        if not all_frames:
            print("[DG GLOBAL WARN] parsed 0 rows from DG Global tables")
            return pd.DataFrame()

        df_all = pd.concat(all_frames, ignore_index=True)

        # Drop rows without a Delivery (safety against stray rows)
        if "Delivery" in df_all.columns:
            s = df_all["Delivery"].astype(str).str.strip()
            df_all = df_all[~s.isna() & (s != "")]
        else:
            print("[DG GLOBAL WARN] no 'Delivery' column after normalization")

        print(f"[DG GLOBAL OK] {len(df_all)} rows")
        return df_all

    except Exception as e:
        print(f"[DG GLOBAL ERR] {e}")
        return pd.DataFrame()
    finally:
        context.close()
        browser.close()
