from __future__ import annotations

from typing import Dict, List

import pandas as pd

from app.modules.imports.legacy_helpers import STANDARD_COLUMNS, symbol_to_month_extended

_CANDIDATE_MAP: Dict[str, List[str]] = {
    "location": ["Location", "location", "Location Name", "Site"],
    "commodity": ["Commodity", "commodity", "Name", "name"],
    "delivery_end": ["Delivery End", "delivery end", "Delivery", "Delivery Label", "delivery_end"],
    "futures_month": ["Futures Month", "Futures Mon.", "Futures", "futures_month", "Futures Symbol", "Symbol", "Month"],
    "futures_price": ["Futures Price", "Futures", "futures_price"],
    "futures_change": ["Change", "Chg", "Futures Change", "futures_change"],
    "basis": ["Basis", "basis"],
    "cash_price_bu": ["Bushel Cash Price", "Cash Price", "The Andersons Cash Price", "cash_price_bu"],
    "cash_price_mt": ["MT Cash Price", "Convtd. Price (Tonnes)", "Price / (Tonnes)", "Cash Price (tonne)", "Converted Price", "cash_price_mt"],
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


def normalize_legacy_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    if df is None or df.empty:
        for c in STANDARD_COLUMNS:
            out[c] = []
        out["source_sheet"] = []
        return out

    for target in STANDARD_COLUMNS:
        col = _find_col(df, _CANDIDATE_MAP.get(target, []))
        out[target] = df[col].astype(str).fillna("") if col else ""

    src_col = _find_col(df, ["Source", "source", "source_sheet"])
    out["source_sheet"] = df[src_col].astype(str).fillna("") if src_col else ""

    out["futures_month"] = out["futures_month"].astype(str).apply(lambda s: symbol_to_month_extended(s) or s)

    cols = STANDARD_COLUMNS + ["source_sheet"]
    for c in cols:
        if c not in out.columns:
            out[c] = ""
    return out[cols]
