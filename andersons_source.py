"""
The Andersons (DTN) cash bid scraper.

Pulls each location's DTN cash-bids page, pivots the tables into rows, and
returns a unified DataFrame matching the main output schema.
"""

from __future__ import annotations

from typing import Dict
import io

import pandas as pd
import requests

from processing import add_mt_cash_price

# Base endpoint and location slugs (extend if more are needed)
ANDERSONS_BASE = "https://dtn-api.andersonscanada.com/cash-bids"
ANDERSONS_LOCATIONS: Dict[str, str] = {
    "blacks-lane": "Blacks Lane",
    "blenheim": "Blenheim",
    "granton": "Granton",
    "hensall": "Hensall",
    "kent-bridge": "Kent Bridge",
    "mitchell": "Mitchell",
    "norwich": "Norwich",
    "pain-court": "Pain Court",
    "pontypool": "Pontypool",
    "port-albert": "Port Albert",
    "claybanks": "Claybanks",
    "igpc-ethanol": "IGPC Ethanol",
    "kintore": "Kintore",
    "rannoch": "Rannoch",
}


def _col_like(df: pd.DataFrame, patterns) -> str:
    low_cols = {c.lower(): c for c in df.columns}
    for p in patterns:
        for lc, orig in low_cols.items():
            if p in lc:
                return orig
    return ""


def parse_andersons_html(html: str, location_name: str) -> pd.DataFrame:
    """
    Parse one DTN 'cash-bids/<slug>' HTML page into rows that match the OCR schema.
    """
    try:
        dfs = pd.read_html(io.StringIO(html))
    except Exception:
        return pd.DataFrame()
    if not dfs:
        return pd.DataFrame()

    COMMODITIES = ["Corn", "Soybeans", "White Wheat", "Soft Red Wheat"]
    out_rows = []
    commodity_idx = 0

    for df in dfs:
        if df.shape[1] < 2:
            continue
        first_col = df.iloc[:, 0].astype(str).str.lower()
        if not first_col.str.contains("futures month").any():
            continue
        if commodity_idx >= len(COMMODITIES):
            break

        commodity_name = COMMODITIES[commodity_idx]
        commodity_idx += 1

        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]
        metric_col = df.columns[0]
        df = df.rename(columns={metric_col: "Metric"})

        # Wide -> long pivot
        wide = (
            df.set_index("Metric")
            .T.reset_index()
            .rename(columns={"index": "Delivery"})
        )
        wide.columns = [str(c).strip() for c in wide.columns]

        col_fut_month = _col_like(wide, ["futures month"])
        col_fut_price = _col_like(wide, ["futures price"])
        col_fut_change = _col_like(wide, ["futures change", "change"])
        col_basis = _col_like(wide, ["basis"])
        col_cash = _col_like(wide, ["the andersons cash price", "cash price"])
        col_converted = _col_like(wide, ["converted price"])


        for _, row in wide.iterrows():
            rec = {
                "Location": location_name,
                "Name": commodity_name,
                "Delivery": row.get("Delivery", ""),
                "Futures Month": row.get(col_fut_month, ""),
                "Futures Price": row.get(col_fut_price, ""),
                "Change": row.get(col_fut_change, ""),
                "Basis": row.get(col_basis, ""),
                "Bushel Cash Price": row.get(col_cash, ""),
                "MT Cash Price": row.get(col_converted, ""),
            }
            out_rows.append(rec)

    if not out_rows:
        return pd.DataFrame()

    df_out = pd.DataFrame(out_rows)
    if "MT Cash Price" not in df_out.columns:
        df_out["MT Cash Price"] = ""

    df_out.attrs["web_headers"] = {
        "Location":          "Location",
        "Name":              "Commodity",
        "Delivery":          "Delivery",  
        "Futures Month":     "Futures Month",
        "Futures Price":     "Futures Price",
        "Change":            "Futures Change",
        "Basis":             "Basis",
        "Bushel Cash Price": "The Andersons Cash Price",
        "MT Cash Price":     "Converted Price",
    }
    return df_out


def fetch_andersons_all() -> pd.DataFrame:
    """
    Fetch cash bids for all Andersons locations defined above.
    """
    all_rows = []
    for slug, long_name in ANDERSONS_LOCATIONS.items():
        url = f"{ANDERSONS_BASE}/{slug}"
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            df_loc = parse_andersons_html(resp.text, long_name)
            if df_loc is not None and not df_loc.empty:
                all_rows.append(df_loc)
                print(f"[ANDERSONS OK] {long_name}: {len(df_loc)} rows")
            else:
                print(f"[ANDERSONS WARN] {long_name}: no rows parsed")
        except Exception as e:
            print(f"[ANDERSONS ERR] {slug}: {e}")

    if not all_rows:
        return pd.DataFrame()

    out = pd.concat(all_rows, ignore_index=True)
    base_cols = [
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
    for c in base_cols:
        if c not in out.columns:
            out[c] = ""
    out = out[[c for c in base_cols if c in out.columns]]
    # preserve web_headers attrs (lost during concat — restore from first frame)
    if all_rows and all_rows[0].attrs:
        out.attrs = all_rows[0].attrs
    return out

