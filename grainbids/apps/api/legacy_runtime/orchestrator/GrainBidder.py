# GrainBidder.py
# Main entrypoint that orchestrates per-source fetchers and writes the consolidated CSV + Excel.

from pathlib import Path
from datetime import datetime
import csv
import datetime as _dt
import re as _re
from typing import Optional, List, Tuple

import pandas as pd
from app.db_utils import save_df_to_db
from playwright.sync_api import sync_playwright

from grain_bids.config import config
from processing import excel_protect
from agricharts_source import fetch_agricharts_bids
from glg_source import fetch_glg_all
from lac_source import fetch_lac_all
from andersons_source import fetch_andersons_all
from snobelen_source import fetch_snobelen_all
from hensall_source import fetch_hensall
from dg_global_source import fetch_dg_global
from bunge_source import fetch_bunge_all
from wanstead_source import fetch_wanstead_all
from ganaraska_source import fetch_ganaraska
from us_agricharts_source import fetch_us_agricharts
from us_dtn_source import fetch_us_dtn


# ---------- BASIS CHANGE HELPERS ----------
_MON_TO_NUM = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_RX_MON_ANY = _re.compile(r"^\s*([A-Za-z]+)[\s\-]+(\d{2,4})\s*$")


def _month_to_key(s: str) -> str:
    s = str(s).strip()
    m = _RX_MON_ANY.match(s)
    if not m:
        parts = s.replace(",", " ").replace("  ", " ").split()
        if len(parts) == 2 and parts[0].isalpha() and parts[1].isdigit():
            mon = parts[0].lower()
            yr = int(parts[1])
            yr = 2000 + yr if yr < 100 else yr
            mm = _MON_TO_NUM.get(mon, None)
            if mm:
                return f"{yr:04d}-{mm:02d}"
        return s.lower()
    mon, yy = m.groups()
    yr = int(yy)
    yr = 2000 + yr if yr < 100 else yr
    mm = _MON_TO_NUM.get(mon.lower(), _MON_TO_NUM.get(mon[:3].lower(), None))
    return f"{yr:04d}-{mm:02d}" if mm else s.lower()


def _normalize_text_series(series: pd.Series) -> pd.Series:
    out = series.fillna("").astype(str).str.strip()
    return out.mask(out.str.lower().isin({"nan", "none"}), "")


def _pick_series(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    fallback: pd.Series | None = None
    for column in candidates:
        if column not in df.columns:
            continue
        series = df[column]
        if fallback is None:
            fallback = series
        if _normalize_text_series(series).ne("").any():
            return series
    if fallback is not None:
        return fallback
    return pd.Series([""] * len(df), index=df.index, dtype="object")


def _build_key(df: pd.DataFrame) -> pd.Series:
    # Support both internal headers and renamed headers in historical CSVs.
    loc = _normalize_text_series(_pick_series(df, ["Location", "location"])).str.lower()
    nam = _normalize_text_series(
        _pick_series(
            df,
            ["Name", "Commodity.1", "Commodity", "commodity_name", "commodity"],
        )
    ).str.lower()
    d1 = _normalize_text_series(_pick_series(df, ["Delivery", "Delivery Label", "delivery_label"])).apply(_month_to_key)
    d2 = _normalize_text_series(_pick_series(df, ["Delivery End", "delivery_end"])).apply(_month_to_key)
    fm = _normalize_text_series(_pick_series(df, ["Futures Month", "Symbol", "futures_month"])).apply(_month_to_key)
    return loc + "|" + nam + "|" + d1 + "|" + d2 + "|" + fm


def _find_prev_output_file(output_dir: Path, fetch_date: str) -> Optional[Path]:
    current = _dt.date.fromisoformat(fetch_date)
    best = None
    for p in output_dir.glob("*.csv"):
        m = _re.search(r"(?:cash_bids_raw|Ontario_CashBids)_(\d{4}-\d{2}-\d{2})\.csv$", p.name)
        if not m:
            continue
        d = _dt.date.fromisoformat(m.group(1))
        if d < current and (best is None or d > best[0]):
            best = (d, p)
    return best[1] if best else None


def add_basis_change_column(today_df: pd.DataFrame, prev_csv_path: Path) -> pd.DataFrame:
    """Compute 'Basis Change' = today's Basis - previous day's Basis (aligned by key)."""
    out = today_df.copy()
    basis_today = pd.to_numeric(_pick_series(out, ["Basis", "basis"]), errors="coerce")
    prev = pd.read_csv(prev_csv_path, dtype=str)
    prev["Basis_num"] = pd.to_numeric(_pick_series(prev, ["Basis", "basis"]), errors="coerce")
    key_today  = _build_key(out)
    key_prev   = _build_key(prev)
    prev_unique = (
        pd.DataFrame({"key": key_prev, "basis": prev["Basis_num"]})
        .groupby("key", sort=False, as_index=True)["basis"]
        .last()
    )
    aligned_prev = key_today.map(prev_unique.to_dict())
    basis_change = basis_today - aligned_prev
    if "Basis Change" in out.columns:
        out["Basis Change"] = basis_change
    else:
        insert_at = out.columns.get_loc("Basis") + 1 if "Basis" in out.columns else len(out.columns)
        out.insert(insert_at, "Basis Change", basis_change)
    return out


def _gather_source_data(playwright) -> List[Tuple[str, pd.DataFrame]]:
    rows: List[Tuple[str, pd.DataFrame]] = []

    # Each entry: (config_key, display_name, fetch_lambda)
    source_fetchers = [
        ("agricharts", "Agricharts",  lambda p: fetch_agricharts_bids(p)),
        ("glg",        "GLG",         lambda p: fetch_glg_all(p)),
        ("lac",        "LAC",         lambda p: fetch_lac_all(p)),
        ("andersons",  "Andersons",   lambda _p: fetch_andersons_all()),
        ("snobelen",   "Snobelen",    lambda p: fetch_snobelen_all(p)),
        ("hensall",    "Hensall",     lambda p: fetch_hensall(p)),
        ("dg_global",  "DG Global",   lambda p: fetch_dg_global(p)),
        ("bunge",      "Bunge",       lambda p: fetch_bunge_all(p)),
        ("wanstead",   "Wanstead",    lambda p: fetch_wanstead_all(p)),
        ("ganaraska",  "Ganaraska",   lambda p: fetch_ganaraska(p)),
    ]

    for cfg_key, name, fn in source_fetchers:
        if not config.source_enabled(cfg_key):
            print(f"[SKIP] {name}: disabled in config.toml")
            continue
        try:
            df = fn(playwright)
            if df is None or df.empty:
                print(f"[WARN] {name}: no rows parsed")
                continue
            rows.append((name, df))
            print(f"[OK] {name}: {len(df)} rows")
        except Exception as e:
            print(f"[ERR] {name}: {e}")

    # ── US elevator sources (config-driven via [[us.elevators]] in config.toml) ──
    if config.us_enabled:
        for elev in config.us_elevators:
            if not elev.get("enabled", True):
                continue
            name = elev.get("name", "Unknown")
            url  = elev.get("url", "")
            typ  = elev.get("type", "agricharts")
            try:
                if typ == "agricharts":
                    df = fetch_us_agricharts(url, name)
                elif typ == "dtn":
                    df = fetch_us_dtn(url, name, playwright)
                else:
                    print(f"[SKIP] {name}: unknown type '{typ}'")
                    continue
                if df is None or df.empty:
                    print(f"[WARN] {name}: no rows parsed")
                    continue
                rows.append((name, df))
                print(f"[OK] {name}: {len(df)} rows")
            except Exception as e:
                print(f"[ERR] {name}: {e}")
    else:
        print("[SKIP] US sources: disabled in config.toml")

    return rows


def main():
    now        = datetime.now()
    fetch_date = now.strftime("%Y-%m-%d")

    output_dir = config.output_dir
    out_path   = output_dir / f"Ontario_CashBids_{fetch_date}.csv"

    with sync_playwright() as p:
        source_dfs = _gather_source_data(p)

    if not source_dfs:
        print("No data collected.")
        return

    # Combine all sources with a Source column
    combined_parts     = []
    merged_web_headers = {}
    for src_name, df in source_dfs:
        df_copy = df.copy()
        df_copy["Source"] = src_name
        combined_parts.append(df_copy)
        try:
            wh = getattr(df, "attrs", {}).get("web_headers", None)
            if isinstance(wh, dict):
                merged_web_headers.update(wh)
        except Exception:
            pass
    out = pd.concat(combined_parts, ignore_index=True)

    prev_path = _find_prev_output_file(output_dir, fetch_date)
    if prev_path is not None:
        out = add_basis_change_column(out, prev_path)
    else:
        if "Basis" in out.columns:
            out.insert(out.columns.get_loc("Basis") + 1, "Basis Change", pd.NA)
        else:
            out["Basis Change"] = pd.NA

    base_cols = [
        "Location", "Commodity", "Name",
        "Delivery", "Delivery End",
        "Futures Month", "Futures Price", "Change",
        "Basis", "Basis Change",
        "Bushel Cash Price", "MT Cash Price",
    ]
    out = out[[c for c in base_cols if c in out.columns] + (["Source"] if "Source" in out.columns else [])]
    out = out.fillna("")

    if "Change" in out.columns:
        out["Change"] = out["Change"].astype(str).map(excel_protect)

    if merged_web_headers:
        rename_map = {k: v for k, v in merged_web_headers.items() if k in out.columns and v}
        if rename_map:
            out = out.rename(columns=rename_map)


    # Save to CSV as before
    out.to_csv(out_path, index=False, header=True, quoting=csv.QUOTE_MINIMAL, encoding="utf-8")
    print(f"Wrote {len(out)} rows to {out_path}")

    # Save to SQLite database for the web app
    try:
        save_df_to_db(out)
        print(f"Saved {len(out)} rows to grain_bids.db for web app.")
    except Exception as e:
        print(f"[ERR] Failed to save to DB: {e}")

    # Excel workbook: one sheet per source + Combined
    excel_path = output_dir / f"Ontario_CashBids_{fetch_date}.xlsx"
    try:
        with pd.ExcelWriter(excel_path) as writer:
            for src_name, df_src in source_dfs:
                df_sheet = df_src.copy()
                wh = getattr(df_src, "attrs", {}).get("web_headers", None)
                if isinstance(wh, dict) and wh:
                    internal_cols = [c for c in df_sheet.columns if c in wh]
                    df_sheet = df_sheet[internal_cols].rename(columns=wh)
                for col in df_sheet.columns:
                    if df_sheet[col].dtype == "object":
                        df_sheet[col] = df_sheet[col].astype(str).map(excel_protect)
                safe_name = src_name.replace("/", "-")[:31] or "Sheet"
                df_sheet.to_excel(writer, sheet_name=safe_name, index=False)
        print(f"Wrote Excel workbook to {excel_path}")
    except ModuleNotFoundError:
        print("openpyxl not installed; skipped Excel output. Run: pip install openpyxl")


if __name__ == "__main__":
    main()
