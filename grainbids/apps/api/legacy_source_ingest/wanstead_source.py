# wanstead_source.py
"""
Wanstead Farmers Co-op / FS Cooperatives cash bids scraper.

URL:
  https://fscooperatives.com/wansteadfarmerscoop/agriculture/cash-bids

Flow:
- Use Playwright to render the page.
- Grab all <table> elements on the page.
- For each table, look at the heading just above it to determine the commodity
  (Corn, Soybeans, Soft Red Winter, Soft White Winter, Hard Red Winter).
- Parse with pandas.read_html.
- Normalize into the common Ontario_CashBids schema:

Location | Commodity | Name | Delivery | Delivery End
Futures Month | Futures Price | Change | Basis
Bushel Cash Price | MT Cash Price
"""

from __future__ import annotations

from typing import List, Tuple
from io import StringIO

import pandas as pd
from playwright.sync_api import TimeoutError as PWTimeout
from bs4 import BeautifulSoup

from processing import add_mt_cash_price

FS_WANSTEAD_URL = "https://fscooperatives.com/wansteadfarmerscoop/agriculture/cash-bids"
WANSTEAD_LABEL = "Any Wanstead Branch"


# ---------- helpers for headings / commodities ----------

def _clean_commodity(raw: str) -> str:
    """
    Take the heading text above a table and turn it into a clean commodity name.
    """
    if not raw:
        return ""

    txt = raw.strip().upper()

    if "CORN" in txt:
        return "Corn"
    if "SOYBEAN" in txt:
        return "Soybeans"
    if "SOFT RED WINTER" in txt:
        return "Soft Red Winter Wheat"
    if "SOFT WHITE WINTER" in txt:
        return "Soft White Winter Wheat"
    if "HARD RED WINTER" in txt:
        return "Hard Red Winter Wheat"

    # Fallback – just title-case whatever is there
    return raw.strip().title()


def _tables_from_html(html: str) -> List[Tuple[pd.DataFrame, str]]:
    """
    Parse all <table> elements and pair each DataFrame with its commodity name,
    using the nearest heading (H1–H4) above the table.
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")

    out: List[Tuple[pd.DataFrame, str]] = []

    for tbl in tables:
        # find the closest heading tag above this table
        heading_tag = tbl.find_previous(["h1", "h2", "h3", "h4"])
        heading_text = heading_tag.get_text(strip=True) if heading_tag else ""
        commodity = _clean_commodity(heading_text)

        try:
            df_list = pd.read_html(StringIO(str(tbl)))
        except ValueError:
            continue

        for df in df_list:
            if df is not None and not df.empty:
                out.append((df, commodity))

    return out


# ---------- normalization ----------

def _normalize_wanstead_df(df_raw: pd.DataFrame, commodity: str) -> pd.DataFrame:
    """
    Map a single Wanstead table into the standard schema.

    Expected columns (case-insensitive, substring-matched):

      LOCATION | DELIVERY LABEL | CASH PRICE | BASIS | SYMBOL | FUTURES PRICE | CHANGE
    """
    if df_raw is None or df_raw.empty:
        return pd.DataFrame()

    df = df_raw.copy()
    df = df.dropna(how="all")

    cols = list(df.columns)
    cols_lower = {str(c).lower(): c for c in cols}

    def pick(*candidates: str) -> str | None:
        # exact match first
        for cand in candidates:
            if cand in cols:
                return cand
        # case-insensitive dict
        for cand in candidates:
            key = cand.lower()
            if key in cols_lower:
                return cols_lower[key]
        # substring fallback
        for c in cols:
            cl = str(c).lower()
            for cand in candidates:
                if cand.lower() in cl:
                    return c
        return None

    loc_col = pick("Location")
    deliv_label_col = pick("Delivery Label", "Delivery")
    cash_col = pick("Cash Price", "Cash")
    basis_col = pick("Basis")
    symbol_col = pick("Symbol")
    fut_price_col = pick("Futures Price", "Futures")
    change_col = pick("Change", "Futures Change")

    if any(col is None for col in (deliv_label_col, cash_col, basis_col, symbol_col, fut_price_col)):
        print("[WANSTEAD WARN] normalize: required columns missing; got:", cols)
        return pd.DataFrame()

    out = pd.DataFrame()

    # Location
    out["Location"] = df[loc_col] if loc_col else WANSTEAD_LABEL

    # Commodity / Name from heading
    clean_comm = _clean_commodity(commodity)
    out["Commodity"] = clean_comm
    out["Name"] = clean_comm

    # You said you prefer the date/period label in Delivery
    out["Delivery"] = df[deliv_label_col].astype(str)
    out["Delivery End"] = ""

    # Symbol (e.g. @C6H, @S6F, @W6H) as Futures Month
    sym_series = df[symbol_col].astype(str)
    out["Futures Month"] = sym_series
    out["Futures Price"] = df[fut_price_col].astype(str)

    out["Change"] = df[change_col].astype(str) if change_col else ""
    out["Basis"] = df[basis_col].astype(str)

    out["Bushel Cash Price"] = df[cash_col]

    # Convert to MT cash price using your shared helper
    out = add_mt_cash_price(out)

    # Optional: header mapping used when you write to Excel
    out.attrs["web_headers"] = {
        "Location": "Location",
        "Commodity": "Commodity",
        "Delivery": "Delivery Label",
        "Bushel Cash Price": "Cash Price",
        "Basis": "Basis",
        "Futures Month": "Symbol",
        "Futures Price": "Futures Price",
        "Change": "Futures Change",
        "MT Cash Price": "Cash Price (tonne)",
    }

    return out


# ---------- main fetch entrypoint ----------

def fetch_wanstead_all(playwright) -> pd.DataFrame:
    """
    Use Playwright to load the FS Wanstead cash-bids page, extract all tables,
    attach the correct commodity from headings, and normalize.
    """
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        print(f"[WANSTEAD] Navigating to {FS_WANSTEAD_URL}")
        page.goto(FS_WANSTEAD_URL, wait_until="domcontentloaded", timeout=60_000)

        # Give DTN widget some time to render
        page.wait_for_timeout(5_000)

        all_norm_frames: List[pd.DataFrame] = []

        # MAIN PAGE ONLY (no iframes needed here)
        main_html = page.content()
        tbls = _tables_from_html(main_html)
        print(f"[WANSTEAD DEBUG] tables found: {len(tbls)}")

        for df_raw, commodity in tbls:
            df_norm = _normalize_wanstead_df(df_raw, commodity)
            if not df_norm.empty:
                all_norm_frames.append(df_norm)

        if not all_norm_frames:
            print("[WANSTEAD WARN] normalization produced no rows")
            return pd.DataFrame()

        df_all = pd.concat(all_norm_frames, ignore_index=True)
        print(f"[WANSTEAD OK] {len(df_all)} normalized rows")
        return df_all

    except PWTimeout as e:
        print(f"[WANSTEAD ERR] timeout: {e}")
        return pd.DataFrame()
    except Exception as e:
        print(f"[WANSTEAD ERR] {e}")
        return pd.DataFrame()
    finally:
        context.close()
        browser.close()
