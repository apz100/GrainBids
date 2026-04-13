# compute_posted_bid.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import re
import pandas as pd


BU_PER_MT = {
    "corn": 39.368,      # bu per metric tonne
    "soybeans": 36.744,  # bu per metric tonne
    "wheat": 36.743,     # if you add wheat later
}


@dataclass
class BidParams:
    # Positioning vs market
    target_discount_cad_mt: float = 7.5   # aim: avg - 7.5
    discount_min_cad_mt: float = 5.0
    discount_max_cad_mt: float = 10.0

    # Anchor construction
    trim_percent: float = 0.20            # trimmed mean (drop top/bottom 20%)

    # Risk/margin clamps (optional but recommended)
        # Optional absolute floor/ceiling clamps in CAD/MT (independent of FX)
    min_posted_bid_cad_mt: Optional[float] = None  # e.g. don't go below 250
    max_posted_bid_cad_mt: Optional[float] = None  # e.g. don't go above 400


    # Rate limiting (optional)
    max_move_up_cad_mt: float = 3.0
    max_move_down_cad_mt: float = 5.0

    # Data filters
    max_bid_age_minutes: Optional[int] = None  # not used unless your CSV has timestamps


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _parse_cbot_price(price_str: str) -> float:
    """
    Parses CBOT-style strings like '425-4' into cents/bu as a float.
    Convention: the suffix is eighths of a cent.
      425-4 -> 425 + 4/8 = 425.5 cents/bu
      1061-2 -> 1061.25 cents/bu
    """
    if price_str is None or str(price_str).strip() == "":
        raise ValueError("Empty Futures Price")
    s = str(price_str).strip()
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", s)
    if not m:
        raise ValueError(f"Unrecognized Futures Price format: {price_str!r}")
    whole = float(m.group(1))
    frac = float(m.group(2)) if m.group(2) is not None else 0.0
    return whole + frac / 8.0  # cents/bu


def _trimmed_mean(values: pd.Series, trim: float) -> float:
    vals = values.dropna().astype(float).sort_values().to_list()
    n = len(vals)
    if n == 0:
        raise ValueError("No competitor MT Cash Price values after filtering.")
    if n < 5 or trim <= 0:
        return sum(vals) / n

    k = int(n * trim)
    # ensure we don't trim everything
    if 2 * k >= n:
        k = max(0, (n - 1) // 2)

    trimmed = vals[k:n - k]
    return sum(trimmed) / len(trimmed)


def compute_posted_bid_from_cashbids_csv(
    csv_path: str | Path,
    *,
    commodity: str,
    delivery: Optional[str] = None,      # matches 'Delivery' column (exact string)
    futures_month: Optional[str] = None, # matches 'Futures Month' column (exact string)
    notes: Optional[str] = None,         # for Wix output (e.g., "Old Crop" / "New Crop")
    params: BidParams = BidParams(),
    last_bid_cad_mt: Optional[float] = None,
    output_csv: Optional[str | Path] = None,
    exclude_locations: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """
    FX-free posted bid:
      anchor = trimmed_mean(competitors MT Cash Price in CAD/MT)
      posted = anchor - clamp(discount, min, max)
      optional rate limiting vs last_bid

    Uses ONLY 'MT Cash Price' from your existing CSV.
    """

    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)

    commodity_norm = commodity.strip().lower()
    if commodity_norm not in BU_PER_MT:
        raise ValueError(f"Unsupported commodity {commodity!r}. Supported: {list(BU_PER_MT.keys())}")

    # Filter by commodity
    df_f = df[df["Name"].astype(str).str.strip().str.lower() == commodity_norm].copy()

    # Filter by delivery bucket if provided
    if delivery is not None:
        df_f = df_f[df_f["Delivery"].astype(str).str.strip() == delivery]

    # Filter by futures month label if provided
    if futures_month is not None:
        df_f = df_f[df_f["Futures Month"].astype(str).str.strip() == futures_month]

    # Exclude certain locations from competitor set (case-insensitive exact match)
    if exclude_locations:
        excl = {str(x).strip().lower() for x in exclude_locations}
        df_f = df_f[~df_f["Location"].astype(str).str.strip().str.lower().isin(excl)].copy()

    if df_f.empty:
        raise ValueError(
            "No rows after filtering. Check commodity/delivery/futures_month values "
            f"against the CSV. Got commodity={commodity!r}, delivery={delivery!r}, futures_month={futures_month!r}"
        )

    # Market anchor based on competitor MT cash prices (CAD/MT)
    comp_prices = pd.to_numeric(df_f["MT Cash Price"], errors="coerce")
    anchor_cad_mt = _trimmed_mean(comp_prices, params.trim_percent)


    # Apply desired discount band (5–10 under avg)
    discount = _clamp(params.target_discount_cad_mt, params.discount_min_cad_mt, params.discount_max_cad_mt)
    bid_raw_cad_mt = anchor_cad_mt - discount

    bid_clamped_cad_mt = float(bid_raw_cad_mt)

    # Rate limit vs last bid (optional)
    if last_bid_cad_mt is not None:
        lo = last_bid_cad_mt - params.max_move_down_cad_mt
        hi = last_bid_cad_mt + params.max_move_up_cad_mt
        bid_clamped_cad_mt = _clamp(bid_clamped_cad_mt, lo, hi)

    # Optional absolute clamps (independent of FX)
    if params.min_posted_bid_cad_mt is not None:
        bid_clamped_cad_mt = max(bid_clamped_cad_mt, float(params.min_posted_bid_cad_mt))
    if params.max_posted_bid_cad_mt is not None:
        bid_clamped_cad_mt = min(bid_clamped_cad_mt, float(params.max_posted_bid_cad_mt))

    bu_per_mt = BU_PER_MT[commodity_norm]
    posted_bid_cad_bu = bid_clamped_cad_mt / bu_per_mt

    # --- Final pricing outputs ---
    result = {
        "Name": commodity_norm.upper(),
        "Notes": notes or "",
        "Basis Month": futures_month or "",

        "Futures Price": "",
        "Fut. Chg.": "",
        "Basis": "",

        "Cash Price": round(float(posted_bid_cad_bu), 2),
        "Cash Price (tonne)": round(float(bid_clamped_cad_mt), 2),
    }

    if output_csv is not None:
        out_path = Path(output_csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        wix_cols = [
            "Name",
            "Notes",
            "Basis Month",
            "Futures Price",
            "Fut. Chg.",
            "Basis",
            "Cash Price",
            "Cash Price (tonne)",
        ]

        pd.DataFrame([result])[wix_cols].to_csv(out_path, index=False)



    return result

# -----------------------
# Example usage
# -----------------------
if __name__ == "__main__":
    src = r"\\DERKS-SERVER\Current\Adam\Code\CashGrainBids\EasternOntarioBids\EasternOntario_CashBids_2026-01-30.csv"
    out_dir = Path(r"\\DERKS-SERVER\Current\Adam\Code\CashGrainBids\PostedBids")
    out_dir.mkdir(parents=True, exist_ok=True)

    params = BidParams(
        target_discount_cad_mt=7.5,
        discount_min_cad_mt=5.0,
        discount_max_cad_mt=10.0,
        trim_percent=0.20,
        min_posted_bid_cad_mt=None,
        max_posted_bid_cad_mt=None,
        max_move_up_cad_mt=3.0,
        max_move_down_cad_mt=5.0,
    )

    r_corn = compute_posted_bid_from_cashbids_csv(
        src,
        commodity="Corn",
        delivery="Jan 2026",
        futures_month="March 2026",
        params=params,
        exclude_locations=["Cardinal Corn", "Johnstown Corn", "Prescott Corn"],
        output_csv=out_dir / "YOUR_POSTED_BID_corn_latest.csv",
    )

    r_soy = compute_posted_bid_from_cashbids_csv(
        src,
        commodity="Soybeans",
        delivery="Jan 2026",
        futures_month="March 2026",
        params=params,
        exclude_locations=["Prescott Soybeans"],
        output_csv=out_dir / "YOUR_POSTED_BID_soy_latest.csv",
    )

    print("CORN:", r_corn)
    print("SOY:", r_soy)