from __future__ import annotations

from typing import Dict, List
import re
import pandas as pd

from app.excel_to_db import STANDARD_COLUMNS, parse_number, symbol_to_month

# month code map for more robust futures symbol parsing
_MONTH_CODE_MAP = {
    "F": "January",
    "G": "February",
    "H": "March",
    "J": "April",
    "K": "May",
    "M": "June",
    "N": "July",
    "Q": "August",
    "U": "September",
    "V": "October",
    "X": "November",
    "Z": "December",
}


def _symbol_to_month_extended(sym: str) -> str:
    """Try several heuristics to convert a futures symbol into a human month like 'May 2026'.

    Uses existing `symbol_to_month` first (covers many DTN/@C6K style symbols),
    then handles ZC/ZS prefixed symbols like 'ZCK26' or 'ZCZ24'.
    """
    if not sym:
        return ""
    s = str(sym).strip()
    # try existing function first
    try:
        v = symbol_to_month(s)
        if v:
            return v
    except Exception:
        pass

    # sanitize: remove non-alphanum and leading @
    s2 = re.sub(r"[^A-Za-z0-9]", "", s)
    s2 = s2.lstrip("@")

    # look for ZC/Z S prefix followed by month-letter then year
    m = re.search(r"^(ZC|ZS)([FGHJKMNQUVXZ])(\d{2,4})$", s2, re.IGNORECASE)
    if m:
        mon = m.group(2).upper()
        yr = m.group(3)
        year = int(yr) if len(yr) == 4 else 2000 + int(yr)
        month_name = _MONTH_CODE_MAP.get(mon, "")
        return f"{month_name} {year}" if month_name else ""

    # general heuristic: find a month code letter and nearby 2-4 digit year
    for i, ch in enumerate(s2):
        uc = ch.upper()
        if uc in _MONTH_CODE_MAP:
            # try digits immediately after
            m2 = re.match(rf"{re.escape(s2[i])}(\d{{2,4}})", s2[i:])
            if m2:
                yr = m2.group(1)
                year = int(yr) if len(yr) == 4 else 2000 + int(yr)
                month_name = _MONTH_CODE_MAP.get(uc, "")
                return f"{month_name} {year}" if month_name else ""
            # try digits immediately before
            m3 = re.search(r"(\d{1,4})$", s2[:i])
            if m3:
                yr = m3.group(1)
                year = int(yr) if len(yr) == 4 else 2000 + int(yr)
                month_name = _MONTH_CODE_MAP.get(uc, "")
                return f"{month_name} {year}" if month_name else ""

    return ""


_CANDIDATE_MAP: Dict[str, List[str]] = {
    "location": ["Location", "location", "Location Name", "Site"],
    "commodity": ["Commodity", "commodity", "Name", "name"],
    "delivery_end": ["Delivery End", "delivery end", "Delivery", "Delivery Label", "delivery_end"],
    "futures_month": ["Futures Month", "Futures Mon.", "Futures", "futures_month", "Futures Symbol"],
    "futures_price": ["Futures Price", "Futures", "futures_price"],
    "futures_change": ["Change", "Chg", "Futures Change", "futures_change"],
    "basis": ["Basis", "basis"],
    "cash_price_bu": ["Bushel Cash Price", "Cash Price", "Cash Price", "cash_price_bu"],
    "cash_price_mt": ["MT Cash Price", "MT Cash Price", "Convtd. Price (Tonnes)", "cash_price_mt"],
}


def _find_col(df: pd.DataFrame, candidates: List[str]):
    low_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in df.columns:
            return cand
        lc = cand.lower()
        if lc in low_map:
            return low_map[lc]
    return None


def normalize_for_db(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map a combined DataFrame (from `GrainBidder`) into the canonical
    lowercase columns used by the web app (`STANDARD_COLUMNS`).

    Rules:
    - Non-destructive: missing values become empty strings.
    - Preserve a `source_sheet` column derived from `Source`/`source` if present.
    - If `futures_month` is empty but `futures_symbol` exists, derive it.
    """
    out = pd.DataFrame()
    if df is None or df.empty:
        # return empty frame with standard columns
        for c in STANDARD_COLUMNS:
            out[c] = []
        out["source_sheet"] = []
        return out

    for target in STANDARD_COLUMNS:
        cand_names = _CANDIDATE_MAP.get(target, [])
        col = _find_col(df, cand_names)
        if col is not None:
            out[target] = df[col].astype(str).fillna("")
        else:
            # default empty
            out[target] = ""

    # Add source_sheet if available
    src_col = _find_col(df, ["Source", "source", "source_sheet"])
    if src_col:
        out["source_sheet"] = df[src_col].astype(str).fillna("")
    else:
        # attempt to use a 'Source' attr on the DataFrame
        src_attr = getattr(df, "attrs", {}).get("web_headers")
        out["source_sheet"] = df.apply(lambda _: "", axis=1) if not df.empty else []

    # (No separate futures_symbol column in canonical output; futures_month will be normalized below)

    # Normalize any futures_month values that are actually symbols into human months
    if "futures_month" in out.columns:
        out["futures_month"] = out["futures_month"].astype(str).apply(lambda s: _symbol_to_month_extended(s) or s)

    # Ensure all columns are present and ordered
    for c in STANDARD_COLUMNS:
        if c not in out.columns:
            out[c] = ""

    # final columns: STANDARD_COLUMNS + source_sheet
    cols = STANDARD_COLUMNS + ["source_sheet"]
    return out[cols]


__all__ = ["normalize_for_db"]
