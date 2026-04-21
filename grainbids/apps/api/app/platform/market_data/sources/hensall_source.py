"""
Hensall Co-op cash bid scraper.

Uses Playwright to grab the DTN cash-bids tables under <dtn-table>
and normalizes them to the standard schema:

Location | Name | Delivery | Delivery End | Futures Month | Futures Price
Change | Basis | Bushel Cash Price | MT Cash Price
"""

from __future__ import annotations

from typing import List, Dict

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PWTimeout

HENSALL_URL = "https://hensallco-op.ca/Cash-Bids.htm"
HENSALL_LABEL = "Hensall Co-op"


def _html_table_to_df(html: str) -> pd.DataFrame:
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
        # tolerate extra "Chart" column
        if len(vals) < len(headers):
            continue
        vals = vals[: len(headers)]
        # 🚫 skip rows that are completely empty
        if all(v == "" for v in vals):
            continue
        rows.append(dict(zip(headers, vals)))

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def _normalize_hensall_df(df_raw: pd.DataFrame, commodity_name: str) -> pd.DataFrame:
    """
    Take a raw DataFrame from a single Hensall <table> and reshape it
    into the columns our main pipeline expects.
    """
    if df_raw.empty:
        return df_raw

    df = df_raw.copy()
    # drop rows that are fully empty/NaN
    df = df.dropna(how="all")

    # Hensall headers look like:
    # LOCATION | DELIVERY LABEL | CASH PRICE | BASIS | SYMBOL | FUTURES PRICE | CHANGE | CONVERTED CASH PRICE | Chart
    cols_lower = {c.lower(): c for c in df.columns}

    def pick(*candidates: str) -> str | None:
        for cand in candidates:
            cand_l = cand.lower()
            if cand_l in cols_lower:
                return cols_lower[cand_l]
        # substring fallback
        for c in df.columns:
            cl = c.lower()
            for cand in candidates:
                if cand.lower() in cl:
                    return c
        return None

    loc_col = pick("location")
    deliv_col = pick("delivery label", "delivery")
    cash_col = pick("cash price", "cash")
    basis_col = pick("basis")
    symbol_col = pick("symbol")
    fut_price_col = pick("futures price", "futures")
    change_col = pick("change")
    mt_col = pick("converted cash price", "converted price", "converted", "price (tonne)")

    out = pd.DataFrame()

    out["Location"] = df[loc_col] if loc_col else HENSALL_LABEL
    out["Name"] = commodity_name or "Hensall"

    out["Delivery"] = df[deliv_col] if deliv_col else ""
    out["Delivery End"] = ""

    out["Futures Month"] = df[symbol_col] if symbol_col else ""
    out["Futures Price"] = df[fut_price_col] if fut_price_col else ""

    out["Change"] = df[change_col] if change_col else ""
    out["Basis"] = df[basis_col] if basis_col else ""

    out["Bushel Cash Price"] = df[cash_col] if cash_col else ""
    out["MT Cash Price"] = df[mt_col] if mt_col else ""

    return out


def fetch_hensall(playwright) -> pd.DataFrame:
    """
    Load the Hensall cash-bids page with Playwright, extract all <dtn-table>
    widgets and parse their inner <table> elements.
    """
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    all_frames: List[pd.DataFrame] = []

    try:
        page.goto(HENSALL_URL, wait_until="domcontentloaded", timeout=60_000)

        # Let JS render the widget
        page.wait_for_timeout(5_000)

        try:
            items: List[Dict[str, str]] = page.eval_on_selector_all(
                "dtn-table",
                """
                els => els.map(el => {
                    const parent = el.parentElement;
                    let name = "";
                    if (parent) {
                        const h1 = parent.querySelector("h1");
                        if (h1) name = h1.textContent.trim();
                    }
                    const tbl = el.querySelector("table");
                    return {
                        name,
                        html: tbl ? tbl.outerHTML : ""
                    };
                })
                """,
            )
        except PWTimeout:
            print("[HENSALL WARN] no dtn-table elements found (timeout)")
            return pd.DataFrame()

        if not items:
            print("[HENSALL WARN] no dtn-table elements found")
            return pd.DataFrame()

        for item in items:
            html = (item.get("html") or "").strip()
            commodity_name = (item.get("name") or "").strip()
            if not html:
                continue

            df_tbl = _html_table_to_df(html)
            if df_tbl is None or df_tbl.empty:
                continue

            df_norm = _normalize_hensall_df(df_tbl, commodity_name)
            if not df_norm.empty:
                all_frames.append(df_norm)

        if not all_frames:
            print("[HENSALL WARN] parsed 0 rows from Hensall tables")
            return pd.DataFrame()

        df_all = pd.concat(all_frames, ignore_index=True)

        # Drop junk rows that don't have a real delivery label
        df_all = df_all.dropna(subset=["Delivery"])
        df_all = df_all[df_all["Delivery"].astype(str).str.strip() != ""]

        print(f"[HENSALL OK] {len(df_all)} rows")
        return df_all

    except Exception as e:
        print(f"[HENSALL ERR] {e}")
        return pd.DataFrame()
    finally:
        context.close()
        browser.close()
