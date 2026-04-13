"""
Great Lakes Grain (GLG) cash bid scraper.
"""

from __future__ import annotations

from typing import List
import io
import re
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from itertools import zip_longest
from playwright.sync_api import TimeoutError as PWTimeout

from processing import add_mt_cash_price, tidy_df, pick_cash_table_html, extract_table_to_df

GLG_BASE = "https://cashbids.greatlakesgrain.com/index.cfm"
GLG_PARAMS = {
    "show": "11",
    "mid": "25",
    "layout": "19",
}

# List of GLG theLocation IDs you want to pull.
GLG_LOCATION_IDS = [
	40,
	41,
	43,
	44,
	45,
	46,
	47,
	48,
	49,
	50,
	51,
	52,
	53,
	54,
	56,
	58,
	60,
	61,
	62,
	63,
	65,
	66,
	106,
	118,
	119,
	128,
	129,
	130,
	131,
	132,
	133,
	134,
	135,
	139,
	144,
]

# Hardcoded mapping of theLocation id -> printable Location name.
# Edit the values below to the exact location names you want in output.
GLG_LOCATION_NAMES = {
	40: "South Essex Grain",
	41: "Arner",
	43: "Wheatley (IP Soybeans)",
	44: "Rochester",
	45: "Stoney Point",
	46: "Chatham / Oungah",
	47: "Thamesville",
	48: "Brigden",
	49: "Haggerty",
	50: "Muirkirk / Highgate",
	51: "Dutton",
	52: "Glencoe",
	53: "Aylmer",
	54: "Staffordville",
	56: "Delhi",
	58: "Ayr",
	60: "Harmony",
	61: "Mitchell",
	62: "Monkton",
	63: "Milverton",
	65: "Grand Valley",
	66: "Beeton",
	106: "Mitchell (IP Soybeans)",
	118: "Embrun Elevator",
	119: "MacEwen Farms",
	128: "Wheatley Corn",
	129: "Essex Farm Wet",
	130: "Brigden Farm Wet",
	131: "Chatham Farm Wet",
	132: "Thamesville Farm Wet",
	133: "Muirkirk Farm Wet",
	134: "Dutton Farm Wet",
	135: "Glencoe Farm Wet",
	139: "Bacres",
	144: "Minesing",
}

# Debug folder (optional, useful during investigation)
DEBUG_DIR = Path(__file__).resolve().parent / "Debug" / "GLG"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


def _col_like(df: pd.DataFrame, patterns) -> str:
    for p in patterns:
        for c in df.columns:
            if p in c.lower():
                return c
    return ""


def _extract_location_name(html: str, loc_id: int) -> str:
    """
    Try to find the human-readable location name from the page HTML.
    Prefer the <select name="theLocation"> selected option; otherwise
    look for an option with the matching value or inline 'Location' text.
    Fall back to an empty string if not found.
    """
    # 1) selected option inside select[name=theLocation]
    m = re.search(r'<select[^>]*name=["\']?theLocation[^>]*>(.*?)</select>', html, re.IGNORECASE | re.DOTALL)
    if m:
        inner = m.group(1)
        # selected option
        m2 = re.search(r'<option[^>]*selected[^>]*>([^<]+)</option>', inner, re.IGNORECASE)
        if m2:
            return m2.group(1).strip()
        # option matching the value
        m3 = re.search(rf'<option[^>]*value=["\']?{loc_id}["\']?[^>]*>([^<]+)</option>', inner, re.IGNORECASE)
        if m3:
            return m3.group(1).strip()

    # 2) fallback: look for "Location" label then some text
    m = re.search(r'Location\s*[:\-\s]*<\/?\w+[^>]*>\s*([^<\n]+)', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # 3) last resort: search for something like "Location: Rochester"
    m = re.search(r'Location[:\s]+([A-Za-z][A-Za-z0-9 \-\']+)', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return ""


def parse_glg_html(html: str, loc_id: int) -> pd.DataFrame:
    """
    Parse GLG page HTML and produce rows with canonical internal columns.
    Uses the website's converted/tonne price as MT Cash Price.
    """
    # use hardcoded name when available, otherwise fall back to extractor
    location_name = (
        GLG_LOCATION_NAMES.get(loc_id)
        or _extract_location_name(html, loc_id)
        or f"GLG theLocation={loc_id}"
    )
    soup = BeautifulSoup(html, "html.parser")
    out_rows = []
    seen = set()

    # mapping tokens -> internal column names
    def header_token(s: str) -> str:
        if not s:
            return ""
        ns = s.lower()
        if "delivery" in ns:
            return "Delivery"
        if "futures mon" in ns or "futures mon." in ns or "futures month" in ns:
            return "Futures Month"
        # futures price (avoid matching futures mon)
        if "futures" in ns and "mon" not in ns and "month" not in ns:
            return "Futures Price"
        if "chg" in ns or "change" in ns:
            return "Change"
        if "basis" in ns:
            return "Basis"
        if "cash price" in ns or ("cash" in ns and "price" in ns):
            return "Bushel Cash Price"
        # website convtd / price-per-tonne column -> internal MT Cash Price
        if "convtd" in ns or "tonne" in ns or "tonnes" in ns or "price / (tonnes)" in ns:
            return "MT Cash Price"
        return ""

    # helper: row looks like a bid row if it contains numeric in one of expected price columns
    def looks_like_bid_row(cells: List[str], mapped: List[str]) -> bool:
        if not cells:
            return False
        joined = " ".join(cells).lower()
        for p in (
            "username",
            "click here",
            "powered by",
            "request a username",
            "forgot your username",
            "online offer center",
            "for specific bids",
        ):
            if p in joined:
                return False
        # check for numeric content in any price-like mapped column
        for idx, m in enumerate(mapped):
            if m in ("Bushel Cash Price", "MT Cash Price", "Futures Price"):
                if idx < len(cells) and re.search(r"\d", str(cells[idx])):
                    return True
        # fallback: delivery cell contains month name or month-like content
        if "Delivery" in mapped:
            try:
                didx = mapped.index("Delivery")
                if didx < len(cells) and re.search(
                    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
                    cells[didx],
                    flags=re.IGNORECASE,
                ):
                    return True
            except ValueError:
                pass
        return False

    tables = soup.find_all("table")
    for tidx, table in enumerate(tables):
        # build header rows (thead preferred, else first 2 tr)
        header_rows = []
        thead = table.find("thead")
        if thead:
            for tr in thead.find_all("tr"):
                header_rows.append(
                    [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
                )
        else:
            trs = table.find_all("tr")
            if not trs:
                continue
            for tr in trs[:2]:
                header_rows.append(
                    [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
                )

        if not header_rows:
            continue

        # combine multi-row headers safely
        combined = []
        for parts in zip_longest(*header_rows, fillvalue=""):
            combined_name = " ".join([p for p in parts if p and p.strip()]).strip()
            combined.append(combined_name)

        if not combined:
            continue

        # map headers to tokens
        mapped = [header_token(c) for c in combined]
        has_delivery = any(m == "Delivery" for m in mapped)
        has_price = any(m in ("Bushel Cash Price", "MT Cash Price", "Futures Price") for m in mapped)
        if not (has_delivery and has_price):
            # skip non-bid tables
            try:
                (DEBUG_DIR / f"loc{loc_id}_skipped_table_{tidx}.html").write_text(
                    str(table)[:4096], encoding="utf-8"
                )
            except Exception:
                pass
            continue

        # get commodity name: caption or nearest heading before table
        commodity = None
        if table.caption and table.caption.get_text(strip=True):
            commodity = table.caption.get_text(strip=True)
        if not commodity:
            prev = table.find_previous(
                lambda tag: tag.name in ["h1", "h2", "h3", "h4", "strong", "b"]
                and tag.get_text(strip=True)
            )
            if prev:
                commodity = prev.get_text(strip=True)
        if not commodity:
            commodity = "GLG Cash"

        # collect body rows
        tbody = table.find("tbody")
        if tbody:
            data_trs = tbody.find_all("tr")
        else:
            all_trs = table.find_all("tr")
            data_trs = all_trs[len(header_rows) :] if len(all_trs) > len(header_rows) else []

        ncols = len(combined)
        for tr in data_trs:
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["td", "th"])]
            if len(cells) < ncols:
                cells += [""] * (ncols - len(cells))
            elif len(cells) > ncols:
                cells = cells[:ncols]
            if not cells or all(not c.strip() for c in cells):
                continue
            if not looks_like_bid_row(cells, mapped):
                continue

            # canonical record
            rec = {
                "Location":          location_name,
                "Name":              commodity,
                "Delivery":          "",
                "Futures Month":     "",
                "Futures Price":     "",
                "Change":            "",
                "Basis":             "",
                "Bushel Cash Price": "",
                "MT Cash Price":     "",
            }
            for i, val in enumerate(cells):
                if i >= len(mapped):
                    continue
                tok = mapped[i]
                if tok == "Delivery":
                    rec["Delivery"] = val
                elif tok == "Futures Month":
                    rec["Futures Month"] = val
                elif tok == "Futures Price":
                    rec["Futures Price"] = val
                elif tok == "Change":
                    rec["Change"] = val
                elif tok == "Basis":
                    rec["Basis"] = val
                elif tok == "Bushel Cash Price":
                    rec["Bushel Cash Price"] = val
                elif tok == "MT Cash Price":
                    rec["MT Cash Price"] = val
                
            # === Commodity Detection Based on Futures Code ===
            fm = rec.get("Futures Month", "").strip()

            if fm.startswith("@S") or fm.startswith("S"):
                rec["Name"] = "Soybeans"
            elif fm.startswith("@C") or fm.startswith("C"):
                rec["Name"] = "Corn"
            elif fm.startswith("@W") or fm.startswith("W"):
                rec["Name"] = "Wheat"
            else:
                rec["Name"] = commodity  # fallback


            if not any(
                re.search(r"\d", str(rec.get(k, "")))
                for k in ("Bushel Cash Price", "Futures Price", "MT Cash Price")
            ):
                continue

            def norm(x: str) -> str:
                return str(x).strip().lower()

            key = "|".join(
                [
                    norm(rec.get("Location", "")),
                    norm(rec.get("Delivery", "")),
                    norm(rec.get("Futures Month", "")),
                    norm(rec.get("Futures Price", "") or rec.get("Bushel Cash Price", "")),
                    norm(rec.get("MT Cash Price", "")),
                ]
            )
            if key in seen:
                continue
            seen.add(key)
            out_rows.append(rec)

    if not out_rows:
        return pd.DataFrame()

    df_out = pd.DataFrame(out_rows)

    expected_internal = [
        "Location",
        "Name",
        "Delivery",
        "Futures Month",
        "Futures Price",
        "Change",
        "Basis",
        "Bushel Cash Price",
        "MT Cash Price",
    ]
    for c in expected_internal:
        if c not in df_out.columns:
            df_out[c] = ""

    # IMPORTANT: do NOT call add_mt_cash_price here; we trust the site MT price
    df_out = df_out[expected_internal]

    df_out.attrs["web_headers"] = {
        "Location":          "Location",
        "Name":              "Commodity",
        "Delivery":          "Delivery",
        "Futures Month":     "Futures Mon.",
        "Futures Price":     "Futures",
        "Change":            "Chg",
        "Basis":             "Basis",
        "Bushel Cash Price": "Cash Price",
        "MT Cash Price":     "Convtd. Price (Tonnes)",
    }

    return df_out



def fetch_glg_all(playwright) -> pd.DataFrame:
    all_rows = []
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        for loc_id in GLG_LOCATION_IDS:
            loc_name = GLG_LOCATION_NAMES.get(loc_id, f"GLG theLocation={loc_id}")
            debug_label = f"GLG_loc{loc_id}"
            try:
                url = (
                    f"{GLG_BASE}?show={GLG_PARAMS['show']}&mid={GLG_PARAMS['mid']}"
                    f"&theLocation={loc_id}&cmid=all&layout={GLG_PARAMS['layout']}"
                )
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_selector("table", timeout=10_000)
                html = page.content()

                try:
                    (DEBUG_DIR / f"{debug_label}_response.html").write_text(html, encoding="utf-8")
                except Exception:
                    pass

                df_loc = parse_glg_html(html, loc_id)
                if df_loc is not None and not df_loc.empty:
                    all_rows.append(df_loc)
                    print(f"[GLG OK] {loc_name}: {len(df_loc)} rows")
                else:
                    print(f"[GLG WARN] {loc_name}: no rows parsed")
            except Exception as e:
                print(f"[GLG ERR] {loc_name}: {e}")
    finally:
        context.close()
        browser.close()

    if not all_rows:
        return pd.DataFrame()
    return pd.concat(all_rows, ignore_index=True)
