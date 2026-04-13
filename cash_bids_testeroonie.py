# cash_bids_via_playwright.py
# Renders each AgriCharts page in headless Chromium and exports:
# Name | Delivery | Delivery End | Futures Month | Futures Price | Change | Basis | (Bushel Cash Price | MT Cash Price)
# + Location
# Writes daily CSV to the first available of:
#   P:\Adam\Code\CashGrainBids\output
#   \\DERKS-SERVER\Current\Adam\Code\CashGrainBids\output
#   <folder next to this script>\output

from pathlib import Path
from datetime import datetime
import re, csv, io, time, os
from typing import List, Dict, Optional

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import requests  # NEW

import math
import datetime as _dt
import re as _re

# --- bushel → metric tonne conversion factors
SOY_BU_PER_MT  = 36.7437   # 1 metric tonne soybeans ≈ 36.7437 bu
CORN_BU_PER_MT = 39.3683   # 1 metric tonne corn     ≈ 39.3683 bu

def add_mt_cash_price(df: pd.DataFrame) -> pd.DataFrame:
    """Rename Cash Price → Bushel Cash Price, then insert MT Cash Price right after."""
    out = df.copy()

    # ensure the bushel column name
    if "Bushel Cash Price" not in out.columns and "Cash Price" in out.columns:
        out = out.rename(columns={"Cash Price": "Bushel Cash Price"})

    # robust numeric parse from strings like "$13.24"
    raw = (
        out["Bushel Cash Price"]
        .astype(str)
        .str.replace(r"[^\d.]", "", regex=True)   # keep only digits and dot
    )
    price_bu = pd.to_numeric(raw, errors="coerce")  # -> float with NaN instead of pd.NA

    # detect commodity from Name or Location
    is_soy  = out.get("Name", "").astype(str).str.contains("soy",  case=False, na=False) \
            | out.get("Location", "").astype(str).str.contains("soy",  case=False, na=False)
    is_corn = out.get("Name", "").astype(str).str.contains("corn", case=False, na=False) \
            | out.get("Location", "").astype(str).str.contains("corn", case=False, na=False)

    # compute MT price (float column default NaN)
    mt_price = pd.Series(index=out.index, dtype="float64")
    mt_price.loc[is_soy]  = price_bu.loc[is_soy]  * SOY_BU_PER_MT
    mt_price.loc[is_corn] = price_bu.loc[is_corn] * CORN_BU_PER_MT

    # insert right after Bushel Cash Price
    insert_at = list(out.columns).index("Bushel Cash Price") + 1
    out.insert(insert_at, "MT Cash Price", mt_price.round(2))

    return out


# ---------- DYNAMIC LOCATION DISCOVERY ----------
AGRICHARTS_BASE_URL = "https://fmn1.agricharts.com/markets/cash.php"

def fetch_all_locations() -> List[Dict]:
    """
    Pull every CORN and SOYBEAN location from the Agricharts master cash.php page.
    Returns a list of {"name": ..., "url": ...}.
    """
    resp = requests.get(AGRICHARTS_BASE_URL, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    select = soup.find("select", id="locationFilter")
    if not select:
        raise RuntimeError("Could not find <select id='locationFilter'> on cash.php")

    targets: List[Dict] = []
    for opt in select.find_all("option"):
        loc_id = (opt.get("value") or "").strip()
        name   = opt.get_text(strip=True)

        if not loc_id or not name:
            continue

        lname = name.lower()
        # only corn & soybeans; skip wheat/canola/etc for now
        if "corn" not in lname and "soybean" not in lname:
            continue

        url = f"{AGRICHARTS_BASE_URL}?location_filter={loc_id}"
        targets.append({"name": name, "url": url})

    if not targets:
        raise RuntimeError("No corn/soybean locations parsed from cash.php")

    return targets

TARGETS: List[Dict] = fetch_all_locations()

# ---------- ROBUST OUTPUT DIR ----------
CANDIDATES = [
    Path(r"P:\Adam\Code\CashGrainBids\OntarioBids"),
    Path(r"\\DERKS-SERVER\Current\Adam\Code\CashGrainBids\OntarioBids"),
    Path(__file__).resolve().parent / "OntarioBids",
]

OUTPUT_DIR = None
last_err = None
for d in CANDIDATES:
    try:
        d.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR = d
        break
    except Exception as e:
        last_err = e
if OUTPUT_DIR is None:
    raise RuntimeError(f"Could not create any output directory from {CANDIDATES}: {last_err}")

# ---------- NORMALIZATION ----------
MONTH_MAP = {
    "Jan":"January", "Feb":"February", "Mar":"March", "Apr":"April", "May":"May", "Jun":"June",
    "Jul":"July", "Aug":"August", "Sep":"September", "Sept":"September", "Oct":"October",
    "Nov":"November", "Dec":"December"
}
SHORT_MONTH_RX = re.compile(r"^\s*([A-Za-z]{3,4})[-\s](\d{2}|\d{4})\s*$")

def norm_short_month(s: str) -> str:
    m = SHORT_MONTH_RX.match(str(s))
    if not m: return str(s)
    mon, yy = m.groups()
    mon3 = mon[:3].title()
    yyyy = int(yy) + 2000 if int(yy) < 100 else int(yy)
    return f"{mon3} {yyyy}"

def norm_full_month(s: str) -> str:
    m = SHORT_MONTH_RX.match(str(s))
    if not m: return str(s)
    mon, yy = m.groups()
    mon3 = mon[:3].title()
    full = MONTH_MAP.get(mon3, mon3)
    yyyy = int(yy) + 2000 if int(yy) < 100 else int(yy)
    return f"{full} {yyyy}"

# ---------- TABLE PICKING ----------
WANTED_HEADERS = [
    "Name", "Delivery", "Delivery End", "Futures Month",
    "Futures Price", "Change", "Basis", "Cash Price"
]

def tidy_df(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join([str(x) for x in t if str(x) != "nan"]).strip() for t in df.columns]
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

# ---------- NEW: DROP SPACER/BLANK ROWS ----------
def drop_spacer_rows(out: pd.DataFrame) -> pd.DataFrame:
    """
    Remove spacer/header-echo rows. Keep rows that have a Name and at least one price.
    """
    out = out.copy().fillna("")
    # Ensure all target cols exist
    for c in WANTED_HEADERS:
        if c not in out.columns:
            out[c] = ""
    # Whitespace normalize
    for c in WANTED_HEADERS:
        out[c] = out[c].astype(str).str.strip()
    # Drop header echoes (e.g., Name == 'Name')
    out = out[out["Name"].str.lower() != "name"]
    # “Has price” signals
    rx_cash = re.compile(r"^\$?\s*\d")            # "$13.24" or "13.24"
    rx_frac = re.compile(r"^[+-]?\d{1,4}-[0-7]$") # "1025-0", "-6-2", etc.
    cash_ok = out["Cash Price"].str.match(rx_cash, na=False)
    fut_ok  = out["Futures Price"].str.match(rx_frac, na=False)
    # Keep: Name present AND (some price present)
    name_ok = out["Name"].str.len() > 0
    keep = name_ok & (cash_ok | fut_ok)
    out = out[keep].copy()
    # Final guard: drop rows where all 9 fields are empty
    all_blank = (out[[c for c in WANTED_HEADERS if c in out.columns]] == "").all(axis=1)
    out = out[~all_blank]
    return out.reset_index(drop=True)

def extract_table_to_df(table_html: str) -> pd.DataFrame:
    dfs = pd.read_html(io.StringIO(table_html))
    df = tidy_df(dfs[0])
    if "Name" in df.columns:
        df = df[df["Name"].astype(str).str.lower() != "name"]  # small safety
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
    # NEW: remove spacer/blank rows
    out = drop_spacer_rows(out)
    return out

# ---------- BROWSER SCRAPE ----------
def scrape_one(page, url: str) -> Optional[pd.DataFrame]:
    page.goto(url, wait_until="domcontentloaded", timeout=45000)

    def try_extract_from_html(html: str) -> Optional[pd.DataFrame]:
        tbl_html = pick_cash_table_html(html)
        if not tbl_html:
            return None
        return extract_table_to_df(tbl_html)

    # Try main page
    try:
        page.wait_for_selector("table", timeout=15000)
        html = page.content()
        df = try_extract_from_html(html)
        if df is not None and len(df):
            return df
    except PWTimeout:
        pass

    # Try iframes
    for fr in page.frames:
        try:
            fr.wait_for_selector("table", timeout=8000)
            html = fr.content()
            df = try_extract_from_html(html)
            if df is not None and len(df):
                return df
        except PWTimeout:
            continue

    return None

def excel_protect(s: str) -> str:
    if isinstance(s, str) and s and s[0] in ("=", "+", "-", "@"):
        return "'" + s  # Excel treats this as literal text, not a formula
    return s

# ---------- BASIS CHANGE HELPERS ----------
# Month maps to build a robust YYYY-MM key from various formats
_MON_TO_NUM = {
    "jan":1,"january":1, "feb":2,"february":2, "mar":3,"march":3, "apr":4,"april":4,
    "may":5, "jun":6,"june":6, "jul":7,"july":7, "aug":8,"august":8,
    "sep":9,"sept":9,"september":9, "oct":10,"october":10, "nov":11,"november":11, "dec":12,"december":12
}
_RX_MON_ANY = _re.compile(r"^\s*([A-Za-z]+)[\s\-]+(\d{2,4})\s*$")

def _month_to_key(s: str) -> str:
    """
    Normalize 'Sep-25', 'Sep 2025', or 'September 2025' -> '2025-09'.
    If not parseable, returns stripped lowercased string.
    """
    s = str(s).strip()
    m = _RX_MON_ANY.match(s)
    if not m:
        parts = s.replace(",", " ").replace("  ", " ").split()
        if len(parts) == 2 and parts[0].isalpha() and parts[1].isdigit():
            mon = parts[0].lower()
            yr  = int(parts[1])
            yr  = 2000 + yr if yr < 100 else yr
            mm  = _MON_TO_NUM.get(mon, None)
            if mm:
                return f"{yr:04d}-{mm:02d}"
        return s.lower()
    mon, yy = m.groups()
    yr = int(yy)
    yr = 2000 + yr if yr < 100 else yr
    mm = _MON_TO_NUM.get(mon.lower(), _MON_TO_NUM.get(mon[:3].lower(), None))
    return f"{yr:04d}-{mm:02d}" if mm else s.lower()

def _build_key(df: pd.DataFrame) -> pd.Series:
    """Key = Location|Name|DeliveryKey|DeliveryEndKey|FutMonKey"""
    loc = df.get("Location", "").astype(str).str.strip().str.lower()
    nam = df.get("Name", "").astype(str).str.strip().str.lower()
    d1  = df.get("Delivery", "").apply(_month_to_key)
    d2  = df.get("Delivery End", "").apply(_month_to_key)
    fm  = df.get("Futures Month", "").apply(_month_to_key)
    return loc + "|" + nam + "|" + d1 + "|" + d2 + "|" + fm

def _find_prev_output_file(fetch_date: str) -> Optional[Path]:
    """
    Return the most recent prior *_YYYY-MM-DD.csv in OUTPUT_DIR with a date < fetch_date.
    Accepts either 'cash_bids_raw_*.csv' or 'Ontario_CashBids_.csv'.
    """
    current = _dt.date.fromisoformat(fetch_date)
    best = None
    for p in OUTPUT_DIR.glob("*.csv"):
        m = _re.search(r"(?:cash_bids_raw|Ontario_CashBids)_(\d{4}-\d{2}-\d{2})\.csv$", p.name)
        if not m:
            continue
        d = _dt.date.fromisoformat(m.group(1))
        if d < current and (best is None or d > best[0]):
            best = (d, p)
    return best[1] if best else None

def add_basis_change_column(today_df: pd.DataFrame, prev_csv_path: Path) -> pd.DataFrame:
    """
    Compute 'Basis Change' = today's Basis - previous day's Basis (aligned by key)
    and insert it immediately after the Basis column.

    This version makes the previous-day key index UNIQUE before mapping,
    so .map() won't raise InvalidIndexError when there are duplicate keys.
    """
    out = today_df.copy()

    # Today's numeric basis
    basis_today = pd.to_numeric(out.get("Basis", pd.Series(dtype="object")), errors="coerce")

    # Load previous CSV (as strings), ensure columns exist
    prev = pd.read_csv(prev_csv_path, dtype=str)
    for c in ["Location", "Name", "Delivery", "Delivery End", "Futures Month", "Basis"]:
        if c not in prev.columns:
            prev[c] = ""

    # Numeric previous basis
    prev["Basis_num"] = pd.to_numeric(prev["Basis"], errors="coerce")

    # Build comparable keys for today and previous
    key_today = _build_key(out)
    key_prev  = _build_key(prev)

    # --- Make previous keys UNIQUE before mapping ---
    # Policy: if duplicates exist, keep the LAST occurrence (most recent row in file).
    prev_unique = (
        pd.DataFrame({"key": key_prev, "basis": prev["Basis_num"]})
        .groupby("key", sort=False, as_index=True)["basis"]
        .last()               # collapse duplicates
    )

    # Align previous basis to today's rows
    aligned_prev = key_today.map(prev_unique.to_dict())

    # Compute change
    basis_change = basis_today - aligned_prev  # NaN where no match

    # Insert column right after 'Basis'
    insert_at = out.columns.get_loc("Basis") + 1 if "Basis" in out.columns else len(out.columns)
    out.insert(insert_at, "Basis Change", basis_change)

    return out

# ---------- GREAT LAKES GRAIN (GLG) SCRAPER ----------

GLG_BASE = "https://cashbids.greatlakesgrain.com/index.cfm"

# List of GLG theLocation IDs you want to pull.
# Start with ones you know; you can add more IDs as you discover them.
GLG_LOCATION_IDS = [
    40,   # e.g. one elevator
    408,  # e.g. another elevator
    # add more IDs here
]

def parse_glg_html(html: str, location_label: str) -> pd.DataFrame:
    """
    Parse one GLG cash-bids HTML page (for a single theLocation)
    into rows that mostly match your OCR schema.
    """
    try:
        dfs = pd.read_html(html)
    except Exception:
        return pd.DataFrame()

    out_rows = []

    for df in dfs:
        if df.shape[1] < 3 or df.shape[0] == 0:
            continue

        df = tidy_df(df)

        def col_like(patterns):
            for p in patterns:
                for c in df.columns:
                    if p in c.lower():
                        return c
            return None

        col_delivery = col_like(["delivery", "month", "period"])
        col_fut      = col_like(["futures"])
        col_change   = col_like(["change"])
        col_basis    = col_like(["basis"])
        col_cash     = col_like(["cash"])

        # Need at least a delivery and a cash price column
        if not col_delivery or not col_cash:
            continue

        # Try a commodity/grade column if it exists
        col_name = col_like(["commodity", "product", "grade"])

        for _, row in df.iterrows():
            name_val = ""
            if col_name:
                name_val = row.get(col_name, "")
            if not name_val:
                name_val = "GLG Cash Bid"

            rec = {
                "Location":          location_label,
                "Name":              name_val,
                "Delivery":          row.get(col_delivery, ""),
                "Delivery End":      "",
                "Futures Month":     "",
                "Futures Price":     row.get(col_fut, ""),
                "Change":            row.get(col_change, ""),
                "Basis":             row.get(col_basis, ""),
                "Bushel Cash Price": row.get(col_cash, ""),
            }
            out_rows.append(rec)

    if not out_rows:
        return pd.DataFrame()

    df_out = pd.DataFrame(out_rows)
    df_out = add_mt_cash_price(df_out)
    return df_out

def fetch_glg_all() -> pd.DataFrame:
    """
    Fetch cash bids for all GLG locations listed in GLG_LOCATION_IDS.
    Uses ?show=11&mid=25&theLocation=ID&layout=19.
    """
    all_rows = []

    for loc_id in GLG_LOCATION_IDS:
        params = {
            "show": "11",
            "mid": "25",
            "theLocation": str(loc_id),
            "layout": "19",
        }
        label = f"GLG theLocation={loc_id}"
        try:
            resp = requests.get(GLG_BASE, params=params, timeout=30)
            resp.raise_for_status()
            df_loc = parse_glg_html(resp.text, label)
            if df_loc is not None and not df_loc.empty:
                all_rows.append(df_loc)
                print(f"[GLG OK] {label}: {len(df_loc)} rows")
            else:
                print(f"[GLG WARN] {label}: no rows parsed")
        except Exception as e:
            print(f"[GLG ERR] {label}: {e}")

    if not all_rows:
        return pd.DataFrame()

    return pd.concat(all_rows, ignore_index=True)


def main():
    now = datetime.now()
    fetch_date = now.strftime("%Y-%m-%d")
    fetch_ts = now.isoformat(timespec="seconds")
    out_path = OUTPUT_DIR / f"Ontario_CashBids_{fetch_date}.csv"

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"
        )
        page = context.new_page()

        for t in TARGETS:
            name, url = t["name"], t["url"]
            try:
                df = scrape_one(page, url)
                if df is None or df.empty:
                    print(f"[WARN] {name}: no rendered bids table found")
                    continue

                df.insert(0, "Location", name)
                df = add_mt_cash_price(df)

                rows.append(df)
                print(f"[OK] {name}: {len(df)} rows")
            except Exception as e:
                print(f"[ERR] {name}: {e}")
            time.sleep(0.5)

        context.close()
        browser.close()

    # ---------- GLG FETCH (no Playwright needed) ----------
    glg_df = fetch_glg_all()
    if glg_df is not None and not glg_df.empty:
        rows.append(glg_df)

    if not rows:
        print("No data collected.")
        return

    # IMPORTANT: don't fillna("") yet; we need numeric Basis for diff calc
    out = pd.concat(rows, ignore_index=True)

    # Compare to the most recent prior CSV (if any) and add 'Basis Change'
    prev_path = _find_prev_output_file(fetch_date)
    if prev_path is not None:
        out = add_basis_change_column(out, prev_path)
    else:
        # no prior file: still add the column so the CSV schema is stable
        if "Basis" in out.columns:
            out.insert(out.columns.get_loc("Basis") + 1, "Basis Change", pd.NA)
        else:
            out["Basis Change"] = pd.NA

    # Final column order (no Settlement; include Basis Change and Bushel/MT)
    base_cols = [
        "Location", "Name", "Delivery", "Delivery End", "Futures Month",
        "Futures Price", "Change", "Basis", "Basis Change", "Bushel Cash Price", "MT Cash Price"
    ]
    out = out[[c for c in base_cols if c in out.columns]]

    # Now it's safe to stringify empties for the CSV
    out = out.fillna("")

    # Prevent Excel from evaluating the Change strings like "+9-6" or "-0-2"
    if "Change" in out.columns:
        out["Change"] = out["Change"].astype(str).map(excel_protect)

    out.to_csv(out_path, index=False, header=True, quoting=csv.QUOTE_MINIMAL, encoding="utf-8")
    print(f"Wrote {len(out)} rows to {out_path}")
    try:
        print(out.head(12).to_string(index=False))
    except Exception:
        pass

if __name__ == "__main__":
    main()
