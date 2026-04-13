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

EXCEL_PATH = 'P:/Adam/Code/GrainBidsFrankenstine/Ontario_CashBids_2026-04-10.xlsx'
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))

STANDARD_COLUMNS = [
    "location",
    "commodity",
    "delivery_label",
    "delivery_start",
    "delivery_end",
    "futures_month",
    "futures_symbol",
    "futures_price",
    "futures_change",
    "basis",
    "cash_price_bu",
    "cash_price_mt",
    "basis_mt",
]

SHEET_MAPPINGS = {
    "Agricharts": {
        "Location": "location",
        "Name": "commodity",
        "Delivery": "delivery_start",
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
        "Delivery": "delivery_start",
        "Futures Mon.": "futures_symbol",
        "Futures": "futures_price",
        "Chg": "futures_change",
        "Basis": "basis",
        "Cash Price": "cash_price_bu",
        "Convtd. Price (Tonnes)": "cash_price_mt",
    },
    "LAC": {
        "Location": "location",
        "Commodity": "commodity",
        "Delivery": "delivery_start",
        "Month": "futures_symbol",
        "Futures": "futures_price",
        "Change": "futures_change",
        "Basis": "basis",
        "Cash Price": "cash_price_bu",
        "Price / (Tonnes)": "cash_price_mt",
    },
    "Andersons": {
        "Location": "location",
        "Commodity": "commodity",
        "Delivery": "delivery_start",
        "Futures Month": "futures_symbol",
        "Futures Price": "futures_price",
        "Futures Change": "futures_change",
        "Basis": "basis",
        "The Andersons Cash Price": "cash_price_bu",
        "Converted Price": "cash_price_mt",
    },
    "Snobelen": {
        "Location": "location",
        "Name": "commodity",
        "Delivery": "delivery_start",
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
        "Delivery": "delivery_start",
        "Delivery End": "delivery_end",
        "Futures Month": "futures_symbol",
        "Futures Price": "futures_price",
        "Change": "futures_change",
        "Basis": "basis",
        "Bushel Cash Price": "cash_price_bu",
        "MT Cash Price": "cash_price_mt",
    },
    "DG Global": {
        "Location": "location",
        "Name": "commodity",
        "Delivery": "delivery_start",
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
        "Delivery Label": "delivery_label",
        "Symbol": "futures_symbol",
        "Futures Price": "futures_price",
        "Futures Change": "futures_change",
        "Basis": "basis",
        "Cash Price": "cash_price_bu",
        "Cash Price (tonne)": "cash_price_mt",
    },
    "Ganaraska": {
        "Location": "location",
        "Name": "commodity",
        "Delivery": "delivery_start",
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
        # rename only columns present
        df = df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})
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
        if sheet == 'Wanstead':
            # sometimes Delivery Label is descriptive; also populate delivery_start with same text
            if 'delivery_label' in df.columns and 'delivery_start' not in df.columns:
                df['delivery_start'] = df['delivery_label']
        # ensure all standard columns exist
        for col in STANDARD_COLUMNS:
            if col not in df.columns:
                df[col] = ''
        # ensure all standard columns exist and reorder
        for col in STANDARD_COLUMNS:
            if col not in df.columns:
                df[col] = ''
        df = df[STANDARD_COLUMNS]
        df['source_sheet'] = sheet
        normalized_frames.append(df)
    if not normalized_frames:
        print('No sheets found')
        return
    combined = pd.concat(normalized_frames, ignore_index=True, sort=False)
    combined = combined.fillna('')

    # (numeric parsing available via module-level parse_number)

    # Best-effort: fill futures_month from futures_symbol when missing
    if 'futures_month' in combined.columns and 'futures_symbol' in combined.columns:
        mask = (combined['futures_month'].astype(str).str.strip() == '') & (combined['futures_symbol'].astype(str).str.strip() != '')
        if mask.any():
            combined.loc[mask, 'futures_month'] = combined.loc[mask, 'futures_symbol'].apply(symbol_to_month)

    # We compute numeric values temporarily for validation, but do not persist them to DB to avoid duplicate columns in the UI.
    # Compute but drop numeric helper columns before saving.
    tmp_numeric_cols = []
    for col in ['basis', 'cash_price_bu', 'cash_price_mt', 'futures_price']:
        if col in combined.columns:
            num_col = f"{col}_num"
            combined[num_col] = combined[col].apply(parse_number)
            tmp_numeric_cols.append(num_col)

    # Remove temporary numeric helper columns before writing to DB
    for c in tmp_numeric_cols:
        if c in combined.columns:
            combined.drop(columns=[c], inplace=True)
    # drop delivery_label as requested
    if 'delivery_label' in combined.columns:
        combined.drop(columns=['delivery_label'], inplace=True)

    # write to DB
    conn = sqlite3.connect(DB_PATH)
    combined.to_sql('grain_bids', conn, if_exists='replace', index=False)
    conn.close()

if __name__ == '__main__':
    excel_to_db()
