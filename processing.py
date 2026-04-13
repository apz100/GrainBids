"""
Shared helpers for parsing and normalizing cash bid tables.
"""

from __future__ import annotations

import io
import re
from typing import List, Optional

import pandas as pd
from bs4 import BeautifulSoup

# --- bushel -> metric tonne conversion factors
SOY_BU_PER_MT = 36.7437
CORN_BU_PER_MT = 39.3683

# ---------- NORMALIZATION ----------
MONTH_MAP = {
    "Jan": "January",
    "Feb": "February",
    "Mar": "March",
    "Apr": "April",
    "May": "May",
    "Jun": "June",
    "Jul": "July",
    "Aug": "August",
    "Sep": "September",
    "Sept": "September",
    "Oct": "October",
    "Nov": "November",
    "Dec": "December",
}
SHORT_MONTH_RX = re.compile(r"^\s*([A-Za-z]{3,4})[-\s](\d{2}|\d{4})\s*$")


def norm_short_month(s: str) -> str:
    m = SHORT_MONTH_RX.match(str(s))
    if not m:
        return str(s)
    mon, yy = m.groups()
    mon3 = mon[:3].title()
    yyyy = int(yy) + 2000 if int(yy) < 100 else int(yy)
    return f"{mon3} {yyyy}"


def norm_full_month(s: str) -> str:
    m = SHORT_MONTH_RX.match(str(s))
    if not m:
        return str(s)
    mon, yy = m.groups()
    mon3 = mon[:3].title()
    full = MONTH_MAP.get(mon3, mon3)
    yyyy = int(yy) + 2000 if int(yy) < 100 else int(yy)
    return f"{full} {yyyy}"


# ---------- TABLE PICKING ----------
WANTED_HEADERS = [
    "Name",
    "Delivery",
    "Delivery End",
    "Futures Month",
    "Futures Price",
    "Change",
    "Basis",
    "Cash Price",
]


def tidy_df(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join([str(x) for x in t if str(x) != "nan"]).strip() for t in df.columns
        ]
    else:
        df.columns = [str(c).strip() for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    return df


def score_headers(cols: List[str]) -> int:
    low = [c.lower() for c in cols]
    need = [h.lower() for h in WANTED_HEADERS]
    return sum(1 for h in need if any(h == c or h in c for c in low))


def pick_cash_table_html(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    best_tbl = None
    best_score = -1
    for tbl in soup.find_all("table"):
        hdr_cells = tbl.find_all("th")
        if not hdr_cells:
            first_tr = tbl.find("tr")
            hdr_cells = first_tr.find_all("td") if first_tr else []
        hdrs = [c.get_text(" ", strip=True) for c in hdr_cells]
        sc = score_headers(hdrs)
        if sc > best_score:
            best_tbl, best_score = tbl, sc
    return str(best_tbl) if best_tbl else None


def drop_spacer_rows(out: pd.DataFrame) -> pd.DataFrame:
    """
    Remove spacer/header-echo rows. Keep rows that have a Name and at least one price.
    """
    out = out.copy().fillna("")
    for c in WANTED_HEADERS:
        if c not in out.columns:
            out[c] = ""
    for c in WANTED_HEADERS:
        out[c] = out[c].astype(str).str.strip()
    out = out[out["Name"].str.lower() != "name"]
    rx_cash = re.compile(r"^\$?\s*\d")
    rx_frac = re.compile(r"^[+-]?\d{1,4}-[0-7]$")
    cash_ok = out["Cash Price"].str.match(rx_cash, na=False)
    fut_ok = out["Futures Price"].str.match(rx_frac, na=False)
    name_ok = out["Name"].str.len() > 0
    keep = name_ok & (cash_ok | fut_ok)
    out = out[keep].copy()
    all_blank = (out[[c for c in WANTED_HEADERS if c in out.columns]] == "").all(axis=1)
    out = out[~all_blank]
    return out.reset_index(drop=True)


def extract_table_to_df(table_html: str) -> pd.DataFrame:
    dfs = pd.read_html(io.StringIO(table_html))
    df = tidy_df(dfs[0])
    if "Name" in df.columns:
        df = df[df["Name"].astype(str).str.lower() != "name"]
    cols = {}
    for want in WANTED_HEADERS:
        match = None
        for c in df.columns:
            if want.lower() == c.lower() or want.lower() in c.lower():
                match = c
                break
        cols[want] = df[match] if match else [""] * len(df)
    out = pd.DataFrame(cols)
    if "Delivery" in out.columns:
        out["Delivery"] = out["Delivery"].apply(norm_short_month)
    if "Delivery End" in out.columns:
        out["Delivery End"] = out["Delivery End"].apply(norm_short_month)
    if "Futures Month" in out.columns:
        out["Futures Month"] = out["Futures Month"].apply(norm_full_month)
    out = drop_spacer_rows(out)
    return out


def add_mt_cash_price(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "Bushel Cash Price" not in out.columns and "Cash Price" in out.columns:
        out = out.rename(columns={"Cash Price": "Bushel Cash Price"})
    raw = (
        out["Bushel Cash Price"]
        .astype(str)
        .str.replace(r"[^\d.]", "", regex=True)
    )
    price_bu = pd.to_numeric(raw, errors="coerce")
    is_soy = out.get("Name", "").astype(str).str.contains("soy", case=False, na=False) | out.get(
        "Location", ""
    ).astype(str).str.contains("soy", case=False, na=False)
    is_corn = out.get("Name", "").astype(str).str.contains(
        "corn", case=False, na=False
    ) | out.get("Location", "").astype(str).str.contains("corn", case=False, na=False)
    mt_price = pd.Series(index=out.index, dtype="float64")
    mt_price.loc[is_soy] = price_bu.loc[is_soy] * SOY_BU_PER_MT
    mt_price.loc[is_corn] = price_bu.loc[is_corn] * CORN_BU_PER_MT
    insert_at = list(out.columns).index("Bushel Cash Price") + 1
    out.insert(insert_at, "MT Cash Price", mt_price.round(2))
    return out


def excel_protect(s: str) -> str:
    if isinstance(s, str) and s and s[0] in ("=", "+", "-", "@"):
        return "'" + s
    return s
