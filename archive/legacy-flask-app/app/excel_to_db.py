import pandas as pd
import sqlite3
import os
import re
import numpy as np

# Numeric parsing helpers (module-level so tests can import)
def parse_number(val):
    if val is None:
        return None
    s = str(val).strip()
    if s == '' or s.lower() in ('nan', 'none'):
        return None
    # Replace common separators like "'" or "-" used in futures prices with a dot
    s = s.replace("'", ".").replace('-', '.')
    # Remove dollar signs, commas, spaces and any non-numeric except dot and minus
    s = re.sub(r"[^0-9.\-]", "", s)
    # If empty after cleanup, return None
    if s == '' or s == '.' or s == '-':
        return None
    try:
        return float(s)
    except Exception:
        return None


# Convert a futures symbol like '@C6K' or '@S6K' to a human-readable month like 'May 2026'
MONTH_CODE = {
    'F': 'Jan', 'G': 'Feb', 'H': 'Mar', 'J': 'Apr', 'K': 'May', 'M': 'Jun',
    'N': 'Jul', 'Q': 'Aug', 'U': 'Sep', 'V': 'Oct', 'X': 'Nov', 'Z': 'Dec'
}

def symbol_to_month(sym):
    if not sym:
        return ''
    s = str(sym)
    # strip non-alphanum
    s = re.sub(r"[^A-Za-z0-9]", '', s)
    # look for pattern: ...<year_digit><month_code>
    m = re.search(r"(\d{1,2})([FGHJKMNQUVXZ])", s, re.IGNORECASE)
    if not m:
        # try last char as month code and preceding single digit as year
        if len(s) >= 2 and s[-1].upper() in MONTH_CODE and s[-2].isdigit():
            year_digit = s[-2]
            month_code = s[-1].upper()
        else:
            return ''
    else:
        year_digit, month_code = m.group(1), m.group(2).upper()
    try:
        if len(year_digit) == 1:
            year = 2020 + int(year_digit)
        else:
            year = 2000 + int(year_digit)
    except Exception:
        year = 0
    month_name = MONTH_CODE.get(month_code, '')
    if month_name and year:
        return f"{month_name} {year}"
    return ''

EXCEL_PATH = 'P:/Adam/Code/GrainBids/Ontario_CashBids_2026-04-10.xlsx'
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))

STANDARD_COLUMNS = [
    "location",
    "commodity",
    "delivery_end",
    "futures_month",
    "futures_price",
    "futures_change",
    "basis",
    "cash_price_bu",
    "cash_price_mt",
]

SHEET_MAPPINGS = {
    "Agricharts": {
        "Location": "location",
        "Name": "commodity",
        "Delivery": "delivery_end",
        "Delivery End": "delivery_end",
        "Futures Month": "futures_month",
        "Futures Price": "futures_price",
        "Change": "futures_change",
        "Basis": "basis",
        "Bushel Cash Price": "cash_price_bu",
        "MT Cash Price": "cash_price_mt",
    },
    "GLG": {
        "Location": "location",
        "Commodity": "commodity",
        "Futures": "futures_price",
        "Chg": "futures_change",
        "Basis": "basis",
        "Cash Price": "cash_price_bu",
        "Convtd. Price (Tonnes)": "cash_price_mt",
    },
    "LAC": {
        "Location": "location",
        "Commodity": "commodity",
        "Delivery": "delivery_end",
        "Month": "futures_month",
        "Futures": "futures_price",
        "Change": "futures_change",
        "Basis": "basis",
        "Cash Price": "cash_price_bu",
        "Price / (Tonnes)": "cash_price_mt",
    },
    "Andersons": {
        "Location": "location",
        "Commodity": "commodity",
        "Delivery": "delivery_end",
        "Futures Month": "futures_month",
        "Futures Price": "futures_price",
        "Futures Change": "futures_change",
        "Basis": "basis",
        "The Andersons Cash Price": "cash_price_bu",
        "Converted Price": "cash_price_mt",
    },
    "Snobelen": {
        "Location": "location",
        "Name": "commodity",
        "Delivery": "delivery_end",
        "Delivery End": "delivery_end",
        "Futures Month": "futures_month",
        "Futures Price": "futures_change",   # this sheet is misaligned
        "Basis": "basis",
        "Bushel Cash Price": "cash_price_bu",
        "Change": "futures_price",           # this sheet is misaligned
        "MT Cash Price": "cash_price_mt",
    },
    "Hensall": {
        "Location": "location",
        "Name": "commodity",
        "Delivery": "delivery_end",
        "Delivery End": "delivery_end",
        "Futures Month": "futures_month",
        "Futures Price": "futures_price",
        "Change": "futures_change",
        "Basis": "basis",
        "Bushel Cash Price": "cash_price_bu",
        "MT Cash Price": "cash_price_mt",
    },
    "DG Global": {
        "Location": "location",
        "Name": "commodity",
        "Delivery End": "delivery_end",
        "Futures Month": "futures_month",
        "Futures Price": "futures_price",
        "Change": "futures_change",
        "Basis": "basis",
        "Bushel Cash Price": "cash_price_bu",
        "MT Cash Price": "cash_price_mt",
    },
    "Wanstead": {
        "Location": "location",
        "Commodity": "commodity",
        "Futures Price": "futures_price",
        "Futures Change": "futures_change",
        "Basis": "basis",
        "Cash Price": "cash_price_bu",
        "Cash Price (tonne)": "cash_price_mt",
    },
    "Ganaraska": {
        "Location": "location",
        "Name": "commodity",
        "Delivery End": "delivery_end",
        "Futures Month": "futures_month",
        "Futures Price": "futures_price",
        "Change": "futures_change",
        "Basis": "basis",
        "Bushel Cash Price": "cash_price_bu",
        "MT Cash Price": "cash_price_mt",
    },
}

def excel_to_db():
    xls = pd.ExcelFile(EXCEL_PATH)
    normalized_frames = []
    combined = pd.DataFrame()  # Initialize combined DataFrame
    for sheet in xls.sheet_names:
        df = pd.read_excel(EXCEL_PATH, sheet_name=sheet)
        mapping = SHEET_MAPPINGS.get(sheet, {})
        # Keep a copy of original columns so we can preserve raw fields like
        # 'Delivery Label' or 'Futures Symbol' even if not in the per-sheet mapping.
        df_raw = df.copy()
        # rename only columns present
        df = df.rename(columns={k: v for k, v in mapping.items() if k in df_raw.columns})

        # Preserve raw 'Delivery Label' and 'Futures Symbol' into normalized
        # internal columns so they are available in the DB even if not shown.
        for orig_col in df_raw.columns:
            lc = str(orig_col).strip().lower()
            if lc in ('delivery label', 'delivery_label', 'delivery') and 'delivery_label' not in df.columns:
                # prefer explicit delivery_label but fall back to generic 'Delivery' when present
                df['delivery_label'] = df_raw[orig_col]
            if lc in ('futures symbol', 'futures_symbol', 'futures symbol code', 'futures_symbol_code') and 'futures_symbol' not in df.columns:
                df['futures_symbol'] = df_raw[orig_col]
        # If the rename produced duplicate column names (e.g. both "Delivery" and
        # "Delivery End" mapped to "delivery_end"), coalesce them into a single
        # column by taking the first non-empty value per row.
        cols_list = list(df.columns)
        dup_names = [c for c in set(cols_list) if cols_list.count(c) > 1]
        for dup in dup_names:
            # collect all columns with this name
            dup_cols = [i for i, c in enumerate(cols_list) if c == dup]
            if len(dup_cols) <= 1:
                continue
            # Build a single consolidated Series by taking the first non-empty value
            def first_non_empty(row):
                for v in row:
                    try:
                        if str(v).strip() != '':
                            return v
                    except Exception:
                        if v is not None:
                            return v
                return ''

            df_merged = df.loc[:, [c for c in df.columns if c == dup]].apply(first_non_empty, axis=1)
            # Drop all duplicate-named columns
            df = df.loc[:, [c for c in df.columns if c != dup]]
            # Reinsert the merged column
            df[dup] = df_merged
        # Special handling per-sheet
        if sheet == 'Snobelen':
            # Snobelen has shifted columns in some rows: swap futures_price and futures_change when detected
            # If futures_price is empty but futures_change contains price-like value, move it
            if 'futures_price' in df.columns and 'futures_change' in df.columns:
                # ensure object dtype to avoid pandas downcasting warnings when assigning mixed types
                df['futures_price'] = df['futures_price'].astype(object)
                df['futures_change'] = df['futures_change'].astype(object)
                mask_move = (df['futures_price'].astype(str).str.strip() == '') & (df['futures_change'].astype(str).str.strip() != '')
                # use where to avoid direct mixed-type loc assignment issues
                df.loc[mask_move, 'futures_price'] = df.loc[mask_move, 'futures_change']
                # clear moved values from futures_change for clarity
                df.loc[mask_move, 'futures_change'] = ''
            # Additional fallback: if futures_price still empty, try extracting from raw sheet columns
            if 'futures_price' in df.columns:
                mask_empty = df['futures_price'].astype(str).str.strip() == ''
                if mask_empty.any():
                    # for each row with empty futures_price, look through raw columns for a numeric-like candidate
                    def _fill_from_raw(row_idx):
                        if str(df.at[row_idx, 'futures_price']).strip() != '':
                            return df.at[row_idx, 'futures_price']
                        for cand in df_raw.columns:
                            try:
                                val = df_raw.at[row_idx, cand]
                            except Exception:
                                val = None
                            if val is None:
                                continue
                            if parse_number(val) is not None:
                                return val
                        return df.at[row_idx, 'futures_price']

                    empty_idxs = [i for i, v in enumerate(mask_empty) if v]
                    for i in empty_idxs:
                        df.at[i, 'futures_price'] = _fill_from_raw(i)
        if sheet == 'Wanstead':
            # sometimes Delivery Label is descriptive; populate delivery_end with same text
            if 'delivery_label' in df.columns:
                if 'delivery_end' not in df.columns:
                    df['delivery_end'] = df['delivery_label']
                else:
                    mask = df['delivery_end'].astype(str).str.strip() == ''
                    df.loc[mask, 'delivery_end'] = df.loc[mask, 'delivery_label']
        # ensure all standard columns exist
        for col in STANDARD_COLUMNS:
            if col not in df.columns:
                df[col] = ''
        # Build saved columns list: canonical columns plus any preserved raw fields
        saved_cols = list(STANDARD_COLUMNS)
        for raw_col in ('delivery_label', 'futures_symbol'):
            if raw_col in df.columns:
                saved_cols.append(raw_col)
        df = df[saved_cols]
        df['source_sheet'] = sheet
        normalized_frames.append(df)
    if not normalized_frames:
        print('No sheets found')
        return
    combined = pd.concat(normalized_frames, ignore_index=True, sort=False)
    combined = combined.fillna('')

    # (numeric parsing available via module-level parse_number)

    # No futures_symbol column in canonical output anymore; keep futures_month as-is

    # We compute numeric values temporarily for validation, but do not persist them to DB to avoid duplicate columns in the UI.
    # Compute numeric helper columns and persist them so numeric types are
    # available in the DB for downstream analysis.
    numeric_sources = ['basis', 'cash_price_bu', 'cash_price_mt', 'futures_price', 'futures_change']
    for col in numeric_sources:
        if col in combined.columns:
            num_col = f"{col}_num"
            combined[num_col] = combined[col].apply(parse_number)
    # Keep `delivery_label` in the DB so the app can map it into
    # `delivery_end` at runtime for display, but do not remove it here.

    # Ensure backward-compatible columns exist for downstream consumers/tests
    for legacy_col in ['delivery_start', 'futures_symbol', 'basis_mt']:
        if legacy_col not in combined.columns:
            combined[legacy_col] = ''

    # write to DB
    conn = sqlite3.connect(DB_PATH)
    combined.to_sql('grain_bids', conn, if_exists='replace', index=False)
    conn.close()

if __name__ == '__main__':
    excel_to_db()
