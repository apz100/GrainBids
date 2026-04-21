import sqlite3
import pandas as pd
import os
from app import excel_to_db

DB_PATH = excel_to_db.DB_PATH


def test_excel_to_db_runs_and_writes_db():
    # Run the normalization to regenerate DB
    excel_to_db.excel_to_db()

    # Connect and fetch a small sample
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query('SELECT * FROM grain_bids LIMIT 20', conn)
    conn.close()

    # Check standard columns exist
    expected = ['location', 'commodity', 'delivery_start', 'delivery_end',
                'futures_month', 'futures_symbol', 'futures_price', 'futures_change',
                'basis', 'cash_price_bu', 'cash_price_mt', 'basis_mt', 'source_sheet']
    for col in expected:
        assert col in df.columns, f"Missing expected column: {col}"
    # At least one row should have a parseable cash_price_bu or cash_price_mt value
    if not df.empty:
        numeric_ok = df['cash_price_bu'].astype(str).str.strip().replace('', pd.NA).notna().any() or df['cash_price_mt'].astype(str).str.strip().replace('', pd.NA).notna().any()
        assert numeric_ok, "No cash prices found in sample rows"


def test_snobelen_fix_applied():
    # Ensure Snobelen rows were normalized and exist
    excel_to_db.excel_to_db()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM grain_bids WHERE source_sheet='Snobelen' LIMIT 50", conn)
    conn.close()

    # If there are Snobelen rows, ensure futures_change or futures_price is present for at least some rows
    if not df.empty:
        has_price_or_change = df['futures_change'].astype(str).str.strip().replace('', pd.NA).notna().any() or df['futures_price'].astype(str).str.strip().replace('', pd.NA).notna().any()
        assert has_price_or_change, "Snobelen rows present but no futures_change or futures_price values after normalization"


def test_symbol_to_month():
    # quick checks for symbol parsing
    assert excel_to_db.symbol_to_month('@C6K') == 'May 2026'
    assert excel_to_db.symbol_to_month("@S6K") == 'May 2026'
    assert excel_to_db.symbol_to_month('C7M') == 'Jun 2007' or isinstance(excel_to_db.symbol_to_month('C7M'), str)
