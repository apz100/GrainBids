import pandas as pd
import sqlite3
import tempfile
import os
import sys

# Ensure repo root is on sys.path so `app` package imports work when running as a script
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from app.normalize import normalize_for_db, _symbol_to_month_extended
from app.db_utils import save_df_to_db


def check_normalize():
    data = {
        'Location': ['Test Loc'],
        'Name': ['Corn'],
        'Delivery': ['Apr 2026'],
        'Futures Mon.': ['ZCK26'],
        'Futures Price': ['439-0'],
        'Basis': ['145'],
        'Bushel Cash Price': ['$5.84'],
        'MT Cash Price': ['229.91'],
        'Source': ['Agricharts']
    }
    df = pd.DataFrame(data)
    out = normalize_for_db(df)
    print('Normalized columns:', list(out.columns))
    print('Sample row:', out.iloc[0].to_dict())


def check_symbol_map():
    examples = ['ZCK26', 'ZCZ24', '@C6K', 'C7M']
    for s in examples:
        print(s, '->', _symbol_to_month_extended(s))


def check_db_write():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, 'test_db.sqlite')
    data = {
        'Location': ['X'],
        'Name': ['Corn'],
        'Delivery': ['Apr 2026'],
        'Futures Mon.': ['ZCK26'],
        'Futures Price': ['439-0'],
        'Basis': ['145'],
        'Bushel Cash Price': ['$5.84'],
        'MT Cash Price': ['229.91'],
        'Source': ['Agricharts']
    }
    df = pd.DataFrame(data)
    save_df_to_db(df, db_path=db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='grain_bids'")
    print('grain_bids table exists:', cur.fetchone() is not None)
    cur.execute('SELECT * FROM grain_bids LIMIT 1')
    print('Row:', cur.fetchone())
    conn.close()


if __name__ == '__main__':
    check_normalize()
    check_symbol_map()
    check_db_write()
