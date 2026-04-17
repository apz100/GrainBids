# us_agricharts_source.py
"""
Generic scraper for US grain elevators using the Agricharts/Barchart writeBidRow() pattern.

Many US grain elevator sites (hosted by Agricharts, now part of Barchart) embed cash bid
data directly in HTML as writeBidRow() function calls:

    writeBidRow(name, basis_cents, manual, eod, incwt, rounding,
                start, end, location, group, notes, weight, rowclass,
                chartsym, quotes['SYMBOL'], settlement, displayOrigPrice,
                basisInActualCents, currConv, exchDisplayType);

Location names come from <h4> tags that precede each table/script block.
Futures prices are fetched from the Agricharts jsquote.php API (same as ganaraska_source).

Usage (called by GrainBidder.py via the [[us.elevators]] config):
    fetch_us_agricharts(url, company_name) -> pd.DataFrame

No Playwright needed — pure requests.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd
import requests

JSQUOTE_BASE = "https://www.agricharts.com/marketdata/jsquote.php"

_BU_PER_MT = {
    "corn":      39.3683,
    "soybeans":  36.7437,
    "soybean":   36.7437,
    "wheat":     36.7437,
    "hrw wheat": 36.7437,
    "srw wheat": 36.7437,
    "hard red winter": 36.7437,
    "soft red winter": 36.7437,
    "milo":      39.3683,
    "sorghum":   39.3683,
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
}

# Matches a writeBidRow() call and captures the parameters we care about.
# Signature (0-indexed):
#   0  name          commodity name
#   1  basis         cents/bu (signed integer)
#   2  manual        bool
#   3  eod           bool
#   4  incwt         bool
#   5  rounding      float
#   6  start         delivery start MM/DD/YYYY
#   7  end           delivery end   MM/DD/YYYY
#   8  location      often 'All' — we prefer the surrounding <h4> name
#   9  group         display group (often '&nbsp;')
#   10 notes         (often '&nbsp;')
#   11 weight        bu/unit (56 for corn, 60 for soy/wheat)
#   12 rowclass      'odd'/'even'
#   13 chartsym      'c=XXXX&l=YYYY&d=ZZZ'
#   14 quote         quotes['SYMBOL'] or quotevarXXXX['SYMBOL']
_WRITEBIDROW_RX = re.compile(
    r"writeBidRow\s*\("
    r"\s*'([^']+)'"                               # 0: name
    r"\s*,\s*([+-]?\d+(?:\.\d+)?)"               # 1: basis (cents/bu)
    r"\s*,\s*(?:true|false)"                      # 2: manual
    r"\s*,\s*(?:true|false)"                      # 3: eod
    r"\s*,\s*(?:true|false)"                      # 4: incwt
    r"\s*,\s*[+-]?[\d.]*"                         # 5: rounding
    r"\s*,\s*'(\d{2}/\d{2}/\d{4})'"              # 6: delivery start
    r"\s*,\s*'(\d{2}/\d{2}/\d{4})'"              # 7: delivery end
    r"\s*,\s*'([^']*)'"                           # 8: location param
    r"\s*,\s*'[^']*'"                             # 9: group
    r"\s*,\s*'[^']*'"                             # 10: notes
    r"\s*,\s*\d+"                                 # 11: weight
    r"\s*,\s*'[^']*'"                             # 12: rowclass
    r"\s*,\s*'([^']*)'"                           # 13: chartsym
    r"\s*,\s*(?:quotes|quotevar\w+)\['([A-Z0-9]+)'\]"  # 14: futures symbol
)

_H4_RX = re.compile(r"<h4[^>]*>\s*([^<]+?)\s*</h4>", re.IGNORECASE)

_JSQUOTE_SCRIPT_RX = re.compile(
    r"jsquote\.php\?varname=(\w+)&(?:amp;)?symbols=([A-Z0-9,]+)",
)


# ─── jsquote helpers (shared logic with ganaraska_source) ────────────────────

def _js_obj_to_dict(js_text: str) -> dict:
    """
    Parse an Agricharts JS object literal (unquoted keys, single-quoted strings)
    into a Python dict of dicts.  Extracts name, month, last per symbol.
    """
    result: dict = {}
    sym_rx   = re.compile(r"['\"]([A-Z0-9]+)['\"]\s*:\s*\{([^}]+)\}", re.DOTALL)
    field_rx = re.compile(r"(\w+)\s*:\s*'([^']*)'")
    for sm in sym_rx.finditer(js_text):
        symbol = sm.group(1)
        block  = sm.group(2)
        fields = {m.group(1): m.group(2) for m in field_rx.finditer(block)}
        result[symbol] = fields
    return result


def _fetch_jsquote(varname: str, symbols: list) -> dict:
    """Fetch current futures prices from Agricharts jsquote API."""
    params = {
        "varname":     varname,
        "symbols":     ",".join(symbols),
        "fields":      "name,month,last",
        "settle":      "0",
        "displayType": "bids",
    }
    r = requests.get(JSQUOTE_BASE, params=params, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    data = _js_obj_to_dict(r.text)
    if not data:
        print(f"[US-AG] jsquote parse failed. Preview: {r.text[:200]}")
    return data


# ─── Main scraper ─────────────────────────────────────────────────────────────

def fetch_us_agricharts(url: str, company_name: str, playwright=None) -> pd.DataFrame:
    """
    Scrape a US elevator page that uses the Agricharts writeBidRow() pattern.

    Args:
        url:          The cash bids page URL (e.g. https://site.com/markets/cash.php)
        company_name: Human-readable company/elevator name for the Location column
        playwright:   Unused; accepted for orchestrator compatibility

    Returns:
        Normalized DataFrame with columns matching the rest of GrainBidder.
    """
    try:
        r = requests.get(url, headers=_HEADERS, timeout=30)
        r.raise_for_status()
        html = r.text

        # 1. Find jsquote.php script tag → varname + symbols
        jm = _JSQUOTE_SCRIPT_RX.search(html)
        if not jm:
            print(f"[US-AG WARN] {company_name}: jsquote script tag not found in page")
            return pd.DataFrame()

        varname = jm.group(1)
        symbols = jm.group(2).split(",")

        # 2. Fetch futures prices from jsquote API
        quotes = _fetch_jsquote(varname, symbols)
        if not quotes:
            print(f"[US-AG ERR] {company_name}: jsquote returned no data")
            return pd.DataFrame()

        # 3. Walk HTML in document order, tracking current <h4> location name
        events: list = []
        for m in _H4_RX.finditer(html):
            events.append((m.start(), "h4", m.group(1).strip()))
        for m in _WRITEBIDROW_RX.finditer(html):
            events.append((m.start(), "row", m))
        events.sort(key=lambda e: e[0])

        rows: list = []
        current_loc = company_name   # fallback if no <h4> precedes first row

        for _pos, etype, data in events:
            if etype == "h4":
                current_loc = data
                continue

            m = data
            name        = m.group(1).strip()
            basis_cents = float(m.group(2))
            del_start   = m.group(3)          # MM/DD/YYYY
            del_end     = m.group(4)          # MM/DD/YYYY
            # group(5) = location param in writeBidRow — often 'All', use h4 instead
            # group(6) = chartsym
            symbol      = m.group(7)

            q             = quotes.get(symbol, {})
            futures_raw   = q.get("last", "")
            futures_month = q.get("month", "")

            bushel_cash = mt_cash = ""
            if futures_raw:
                try:
                    # futures_raw is decimal cents/bu (e.g. "439", "449.5")
                    cash_cents = float(futures_raw) + basis_cents
                    cash_bu    = cash_cents / 100.0
                    bushel_cash = f"${cash_bu:.2f}"
                    bpu = _BU_PER_MT.get(name.lower(), 39.3683)
                    mt_cash = str(round(cash_bu * bpu, 2))
                except Exception:
                    pass

            # Basis as ¢/bu for display  (e.g. 5 → "+5¢", -40 → "-40¢")
            basis_disp = (
                f"+{int(basis_cents)}" if basis_cents > 0
                else str(int(basis_cents)) if basis_cents == int(basis_cents)
                else str(basis_cents)
            )

            rows.append({
                "Location":          f"{company_name} - {current_loc}",
                "Name":              name,
                "Delivery":          del_start,
                "Delivery End":      del_end,
                "Futures Month":     futures_month,
                "Futures Price":     futures_raw,
                "Change":            "",
                "Basis":             basis_disp,
                "Bushel Cash Price": bushel_cash,
                "MT Cash Price":     mt_cash,
            })

        if not rows:
            print(f"[US-AG WARN] {company_name}: 0 rows parsed — page structure may differ")
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        print(f"[US-AG OK] {company_name}: {len(df)} rows from {len(set(r['Location'] for r in rows))} locations")
        return df

    except Exception as e:
        print(f"[US-AG ERR] {company_name}: {e}")
        return pd.DataFrame()
