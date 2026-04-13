# ganaraska_source.py
"""
Ganaraska Grain cash bid scraper.

The Ganaraska site uses Agricharts' jsquote.php widget — all data is rendered
client-side via JavaScript, so headless browsers see 0 tables. Instead we:

  1. Fetch the HTML page with requests to extract varname + symbols
  2. Call Agricharts jsquote.php API directly for futures prices
  3. Parse the inline JS in the HTML to extract basis values + delivery labels
  4. Compute cash prices and return a normalized DataFrame

No Playwright needed. The `playwright` arg is accepted for orchestrator compatibility.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd
import requests

GANARASKA_URL  = "https://www.ganaraskagrain.com/cashbidsindex"
GANARASKA_LABEL = "Ganaraska Grain"
JSQUOTE_BASE   = "https://www.agricharts.com/marketdata/jsquote.php"

# bu → MT conversion factors (same as processing.py)
_BU_PER_MT = {"corn": 39.3683, "soybeans": 36.7437, "wheat": 36.7437}

# CME single-letter month code → (short name, month number)
_MONTH_LETTER = {
    "F": ("Jan",  1), "G": ("Feb",  2), "H": ("Mar",  3), "J": ("Apr",  4),
    "K": ("May",  5), "M": ("Jun",  6), "N": ("Jul",  7), "Q": ("Aug",  8),
    "U": ("Sep",  9), "V": ("Oct", 10), "X": ("Nov", 11), "Z": ("Dec", 12),
}

# Agricharts commodity ID → name
_COMMODITY_IDS = {"4978": "Corn", "4980": "Soybeans", "4984": "Wheat"}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
}


def _decode_delivery(d_code: str) -> str:
    """'J26' → 'Apr 2026'"""
    if not d_code or len(d_code) < 3:
        return d_code
    letter = d_code[0].upper()
    try:
        year = 2000 + int(d_code[1:])
    except ValueError:
        return d_code
    mon = _MONTH_LETTER.get(letter, ("???", 0))[0]
    return f"{mon} {year}"


def _parse_jsquote_month(raw: str) -> str:
    """'May 26' or 'May 2026' → 'May 2026'"""
    raw = raw.strip()
    # Already full year: "May 2026"
    if re.match(r"[A-Za-z]+\s+\d{4}$", raw):
        parts = raw.split()
        return f"{parts[0].title()} {parts[1]}"
    # Short year: "May 26"
    m = re.match(r"([A-Za-z]+)\s+(\d{2})$", raw)
    if m:
        return f"{m.group(1).title()} {2000 + int(m.group(2))}"
    return raw


def _js_obj_to_dict(js_text: str) -> dict:
    """
    Parse an Agricharts JS object literal (unquoted keys, single-quoted strings)
    into a Python dict of dicts. Only extracts name, month, last per symbol.
    """
    result = {}
    # Split on top-level symbol entries: 'ZCK26': {
    sym_rx = re.compile(r"['\"]([A-Z0-9]+)['\"]\s*:\s*\{([^}]+)\}", re.DOTALL)
    field_rx = re.compile(r"(\w+)\s*:\s*'([^']*)'")
    for sm in sym_rx.finditer(js_text):
        symbol = sm.group(1)
        block  = sm.group(2)
        fields = {m.group(1): m.group(2) for m in field_rx.finditer(block)}
        result[symbol] = fields
    return result


def _fetch_jsquote(varname: str, symbols: list) -> dict:
    """
    Call Agricharts jsquote.php API.
    Returns dict: { "ZCK26": {"last": "439", "month": "May 2026", "name": "Corn"}, ... }
    """
    params = {
        "varname": varname,
        "symbols": ",".join(symbols),
        "fields": "name,month,last",
        "settle": "0",
        "displayType": "bids",
    }
    r = requests.get(JSQUOTE_BASE, params=params, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    data = _js_obj_to_dict(r.text)
    if not data:
        print(f"[GANARASKA] jsquote parse failed. Preview: {r.text[:300]}")
    return data


def _extract_basis(block: str) -> Optional[float]:
    """
    Extract the basis value ($/bu) from one symbol's JS block.

    Agricharts embeds basis as integer cents in the cash-price expression:
        var rounded = price + 195;       → basis = 195 cents = $1.95/bu
        var rounded = price + (195/100)  → same value, MW/ZR path

    Falls back to addBasis variable patterns used by other Agricharts widgets.
    NOTE: Does NOT truncate at document.write — basis is inside those calls.
    """
    # Primary: Agricharts cash-price expression, basis in cents
    m = re.search(r"rounded\s*=\s*price\s*\+\s*\(?([+-]?\d+(?:\.\d+)?)\b", block)
    if m:
        return float(m.group(1)) / 100.0   # cents → $/bu

    # Fallback: addBasis / basis variable patterns (other Agricharts widgets)
    for pat in [
        r"var\s+\w*[Bb]asis\w*\s*=\s*([+-]?\d+\.?\d*)",
        r"addBasis\s*=\s*([+-]?\d+\.?\d*)",
        r"basis\s*[=:]\s*([+-]?\d+\.?\d*)",
        r"basisadj\s*=\s*([+-]?\d+\.?\d*)",
    ]:
        bm = re.search(pat, block, re.IGNORECASE)
        if bm:
            return float(bm.group(1))
    return None


def _extract_rows(html: str, quotes: dict) -> list:
    """
    Walk the HTML looking for JS blocks of the form:
        quote = quotevarXXXXX['SYMBOL'];
        ...
    One block per delivery row. Extract delivery, commodity, basis from each block.
    """
    rows = []
    # All quote assignment positions
    block_rx = re.compile(r"quote\s*=\s*quotevar\w+\[(['\"])([A-Z0-9]+)\1\]")
    matches = list(block_rx.finditer(html))

    for i, match in enumerate(matches):
        symbol = match.group(2)
        if symbol not in quotes:
            continue

        block_start = match.start()
        block_end   = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        block       = html[block_start:block_end]

        q = quotes[symbol]

        # --- Delivery label from cashchart URL ---
        delivery = ""
        commodity = q.get("name", "").title()
        d_match = re.search(r"cashchart\.php\?c=(\d+)&l=\d+&d=([A-Z]\d{2})", block)
        if d_match:
            delivery = _decode_delivery(d_match.group(2))
            commodity = _COMMODITY_IDS.get(d_match.group(1), commodity)

        # --- Futures month from jsquote ---
        futures_month = _parse_jsquote_month(str(q.get("month", "")))

        # --- Futures price (raw CBOT string) ---
        futures_price = str(q.get("last", ""))

        # --- Basis ---
        basis = _extract_basis(block)

        # --- Cash prices ---
        bushel_cash = mt_cash = ""
        if basis is not None and futures_price:
            try:
                # "443-0" = 443 + 0/8 cents/bu; "449.5" = 449.5 cents/bu → dollars/bu
                m2 = re.fullmatch(r"(\d+(?:\.\d+)?)(?:-(\d+))?", futures_price.strip())
                if m2:
                    if m2.group(2) is not None:
                        cents = float(m2.group(1)) + float(m2.group(2)) / 8
                    else:
                        cents = float(m2.group(1))
                    fut_dol = cents / 100.0
                    cash_bu = fut_dol + basis
                    bushel_cash = f"${cash_bu:.2f}"
                    bpu = _BU_PER_MT.get(commodity.lower(), 39.3683)
                    mt_cash = str(round(cash_bu * bpu, 2))
            except Exception:
                pass

        row = {
            "Location":          GANARASKA_LABEL,
            "Name":              commodity,
            "Delivery":          delivery,
            "Delivery End":      "",
            "Futures Month":     futures_month,
            "Futures Price":     futures_price,
            "Change":            "",
            "Basis":             str(round(basis, 2)) if basis is not None else "",
            "Bushel Cash Price": bushel_cash,
            "MT Cash Price":     mt_cash,
        }

        if row["Delivery"] and (row["Futures Price"] or row["Basis"]):
            rows.append(row)

    return rows


def fetch_ganaraska(playwright=None) -> pd.DataFrame:
    """
    Fetch Ganaraska Grain cash bids directly from the Agricharts jsquote API.
    No browser required. `playwright` is accepted but unused.
    """
    try:
        # 1. Fetch HTML to find varname + symbols dynamically
        r = requests.get(GANARASKA_URL, headers=_HEADERS, timeout=30)
        r.raise_for_status()
        html = r.text

        src_m = re.search(
            r"jsquote\.php\?varname=(\w+)&(?:amp;)?symbols=([A-Z0-9,]+)",
            html,
        )
        if not src_m:
            print("[GANARASKA ERR] jsquote varname/symbols not found in page")
            return pd.DataFrame()

        varname = src_m.group(1)
        symbols = src_m.group(2).split(",")
        print(f"[GANARASKA] varname={varname}, {len(symbols)} symbols")

        # 2. Fetch futures prices from jsquote API
        quotes = _fetch_jsquote(varname, symbols)
        if not quotes:
            print("[GANARASKA ERR] jsquote API returned no data")
            return pd.DataFrame()

        # 3. Extract rows from HTML (delivery labels, commodity, basis)
        rows = _extract_rows(html, quotes)

        if not rows:
            print("[GANARASKA WARN] 0 rows extracted — basis regex may need adjustment")
            # Fallback: emit rows with futures data only (no basis/cash)
            rows = []
            for sym, q in quotes.items():
                rows.append({
                    "Location":          GANARASKA_LABEL,
                    "Name":              q.get("name", "").title(),
                    "Delivery":          _parse_jsquote_month(str(q.get("month", ""))),
                    "Delivery End":      "",
                    "Futures Month":     _parse_jsquote_month(str(q.get("month", ""))),
                    "Futures Price":     str(q.get("last", "")),
                    "Change":            "",
                    "Basis":             "",
                    "Bushel Cash Price": "",
                    "MT Cash Price":     "",
                })
            if not rows:
                return pd.DataFrame()

        df = pd.DataFrame(rows)
        print(f"[GANARASKA OK] {len(df)} rows")
        return df

    except Exception as e:
        print(f"[GANARASKA ERR] {e}")
        return pd.DataFrame()
