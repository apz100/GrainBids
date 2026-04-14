"""
London Agricultural Commodities (LAC) cash bid scraper.

Uses Playwright to let DTN's JavaScript render the page, then reads the
finished <table name="cashbids-data-table"> as text via pandas.read_html.

That way we get the *displayed* numbers:
  Basis, Cash Price, Price / (Tonnes), Basis / (Tonnes)
instead of the internal displayNumber(...) values.
"""

from __future__ import annotations

import re
from typing import Dict

import io
import pandas as pd
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Playwright
from urllib.parse import urlencode

LAC_BASE_URL = "https://dtn.londonag.com/index.cfm"
DEFAULT_PARAMS = {"show": "11", "mid": "3", "layout": "19", "cmid": "all"}

NUM_RE = re.compile(r"[-+]?\d*\.\d+|[-+]?\d+")


def extract_visible_number(val: object) -> str:
    """
    Given a cell like:
      '<!-- displayNumber(-57.3956,4); //-->  14.5425'
    return the LAST numeric literal: '14.5425'.

    If no numbers, return ''.
    """
    if val is None:
        return ""
    text = str(val)
    nums = NUM_RE.findall(text)
    if not nums:
        return ""
    return nums[-1]  # last = what user sees in the table


# ---------------------------------------------------------------------------
# Location dropdown (via requests)
# ---------------------------------------------------------------------------

def _fetch_location_options() -> Dict[str, str]:
    resp = requests.get(LAC_BASE_URL, params=DEFAULT_PARAMS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    select = soup.find("select", attrs={"name": re.compile("Location", re.I)})
    if not select:
        raise RuntimeError("Could not find Location dropdown on LAC DTN page")

    options: Dict[str, str] = {}
    for opt in select.find_all("option"):
        value = (opt.get("value") or "").strip()
        label = opt.get_text(" ", strip=True)
        if value.isdigit() and label:
            options[value] = label

    if not options:
        raise RuntimeError("Parsed zero LAC locations from dropdown")
    return options


# ---------------------------------------------------------------------------
# Parse a *rendered* LAC HTML page into our canonical DataFrame
# ---------------------------------------------------------------------------

def _parse_lac_dom(html: str, location_name: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table", attrs={"name": "cashbids-data-table"})
    if not tables:
        return pd.DataFrame()

    frames = []

    for tbl in tables:
        # Commodity label just above the table (SOYBEANS, CORN, WHEAT, SRW, etc.)
        label_node = tbl.find_previous(
            lambda tag: tag.name in ["h1", "h2", "h3", "h4", "b", "strong", "font", "span"]
            and tag.get_text(strip=True)
        )
        commodity = label_node.get_text(" ", strip=True).strip() if label_node else "LAC Cash Bid"

        try:
            df_raw = pd.read_html(io.StringIO(str(tbl)))[0]
        except ValueError:
            continue

        # Normalize column labels
        df_raw.columns = [str(c).strip() for c in df_raw.columns]

        # Map DTN headers -> our internal schema
        mapping = {}
        for col in df_raw.columns:
            lc = col.lower()
            if "delivery" in lc:
                mapping[col] = "Delivery"
            elif "month" in lc:
                mapping[col] = "Futures Month"
            elif "futures" in lc:
                mapping[col] = "Futures Price"
            elif "change" in lc:
                mapping[col] = "Change"
            elif "basis" in lc and "tonnes" not in lc:
                mapping[col] = "Basis"
            elif "cash" in lc:
                mapping[col] = "Bushel Cash Price"
            elif "price" in lc and "tonnes" in lc:
                mapping[col] = "MT Cash Price"
            elif "basis" in lc and "tonnes" in lc:
                mapping[col] = "Basis / (Tonnes)"

        df_tmp = df_raw.rename(columns=mapping)

        # Add our extra fields
        df_tmp["Location"] = location_name
        df_tmp["Name"] = commodity

        # Clean numeric columns: keep only the visible value
        for col in ["Basis", "Bushel Cash Price", "MT Cash Price", "Basis / (Tonnes)"]:
            if col in df_tmp.columns:
                df_tmp[col] = df_tmp[col].apply(extract_visible_number)

        # Ensure all expected columns exist
        expected_cols = [
            "Location",
            "Name",
            "Delivery",
            "Futures Month",
            "Futures Price",
            "Change",
            "Basis",
            "Bushel Cash Price",
            "MT Cash Price",
            "Basis / (Tonnes)",
        ]
        for c in expected_cols:
            if c not in df_tmp.columns:
                df_tmp[c] = ""

        df_clean = df_tmp[expected_cols]
        frames.append(df_clean)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Excel headers to match the LAC webpage
    df.attrs["web_headers"] = {
        "Location":          "Location",
        "Name":              "Commodity",
        "Delivery":          "Delivery",
        "Futures Month":     "Month",
        "Futures Price":     "Futures",
        "Change":            "Change",
        "Basis":             "Basis",
        "Bushel Cash Price": "Cash Price",
        "MT Cash Price":     "Price / (Tonnes)",
        "Basis / (Tonnes)":  "Basis / (Tonnes)",
    }

    return df


# ---------------------------------------------------------------------------
# Public fetch – via Playwright
# ---------------------------------------------------------------------------

def fetch_lac_all(p: Playwright) -> pd.DataFrame:
    """
    Fetch cash bids for all LAC locations by letting the DTN page render in
    Chromium (Playwright) and then scraping the visible table text.

    Reuses the Playwright instance passed in from grainBidder.py.
    """
    locations = _fetch_location_options()
    all_rows = []

    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    for loc_id, loc_name in locations.items():
        params = DEFAULT_PARAMS | {"theLocation": loc_id}
        url = f"{LAC_BASE_URL}?{urlencode(params)}"

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            html = page.content()
            df_loc = _parse_lac_dom(html, f"LAC - {loc_name}")
            if df_loc is not None and not df_loc.empty:
                all_rows.append(df_loc)
                print(f"[LAC OK] {loc_name}: {len(df_loc)} rows")
            else:
                print(f"[LAC WARN] {loc_name}: no rows parsed")
        except Exception as e:
            print(f"[LAC ERR] {loc_name}: {e}")

    browser.close()

    if not all_rows:
        return pd.DataFrame()

    return pd.concat(all_rows, ignore_index=True)


# Backwards-compatible wrapper expected by some tests
def parse_lac_html(html: str, location_name: str) -> pd.DataFrame:
    """Compatibility wrapper: parse rendered LAC HTML into DataFrame."""
    return _parse_lac_dom(html, location_name)