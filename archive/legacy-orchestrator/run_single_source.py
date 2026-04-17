"""
Run a single grain bidder source standalone (without full GrainBidder pipeline).
Usage: python run_single_source.py <source_name>
  e.g. python run_single_source.py GLG
"""

import sys
from pathlib import Path
from datetime import datetime
import csv

import pandas as pd

# Import source fetchers
from glg_source import fetch_glg_all
from agricharts_source import fetch_agricharts_bids
from lac_source import fetch_lac_all
from andersons_source import fetch_andersons_all
from snobelen_source import fetch_snobelen_all
from hensall_source import fetch_hensall
from dg_global_source import fetch_dg_global
from bunge_source import fetch_bunge_all
from processing import excel_protect
from playwright.sync_api import sync_playwright


OUTPUT_DIR = Path(__file__).resolve().parent / "Output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Map source names to fetcher functions
SOURCE_FETCHERS = {
    "GLG": (lambda _p: fetch_glg_all(), False),  # (fetcher_fn, needs_playwright)
    "Agricharts": (lambda p: fetch_agricharts_bids(p), True),
    "LAC": (lambda _p: fetch_lac_all(), False),
    "Andersons": (lambda _p: fetch_andersons_all(), False),
    "Snobelen": (lambda _p: fetch_snobelen_all(), False),
    "Hensall": (lambda p: fetch_hensall(p), True),
    "DG Global": (lambda p: fetch_dg_global(p), True),
    "Bunge": (lambda p: fetch_bunge_all(p), True),
}


def apply_web_headers(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """
    Apply web-style header renames if the source advertised them via df.attrs["web_headers"].
    """
    try:
        wh = getattr(df, "attrs", {}).get("web_headers", None)
        if isinstance(wh, dict):
            rename_map = {k: v for k, v in wh.items() if k in df.columns and v}
            if rename_map:
                print(f"[{source_name}] Applying web-header renames: {rename_map}")
                df = df.rename(columns=rename_map)
    except Exception as e:
        print(f"[{source_name}] Warning: could not apply web headers: {e}")
    return df


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_single_source.py <source_name>")
        print(f"Available sources: {', '.join(SOURCE_FETCHERS.keys())}")
        sys.exit(1)

    source_name = sys.argv[1]
    if source_name not in SOURCE_FETCHERS:
        print(f"[ERROR] Unknown source: {source_name}")
        print(f"Available sources: {', '.join(SOURCE_FETCHERS.keys())}")
        sys.exit(1)

    fetcher_fn, needs_playwright = SOURCE_FETCHERS[source_name]

    print(f"[INFO] Running single-source test for: {source_name}")

    # Fetch data
    try:
        if needs_playwright:
            with sync_playwright() as p:
                df = fetcher_fn(p)
        else:
            df = fetcher_fn(None)
    except Exception as e:
        print(f"[ERROR] {source_name} fetch failed: {e}")
        sys.exit(1)

    if df is None or df.empty:
        print(f"[WARN] {source_name}: no rows parsed")
        sys.exit(0)

    print(f"[OK] {source_name}: {len(df)} rows")

    # Apply web-header mappings if advertised
    df = apply_web_headers(df, source_name)

    # Apply excel_protect to Change column if present
    if "Change" in df.columns or "Chg" in df.columns:
        chg_col = "Change" if "Change" in df.columns else "Chg"
        df[chg_col] = df[chg_col].astype(str).map(excel_protect)

    # Write CSV
    now = datetime.now()
    fetch_date = now.strftime("%Y-%m-%d")
    out_path = OUTPUT_DIR / f"{source_name}_{fetch_date}.csv"
    
    df.to_csv(out_path, index=False, header=True, quoting=csv.QUOTE_MINIMAL, encoding="utf-8")
    print(f"[OK] Wrote {len(df)} rows to {out_path}")

    # Print first few rows
    try:
        print("\n" + df.head(12).to_string(index=False))
    except Exception:
        pass


if __name__ == "__main__":
    main()
