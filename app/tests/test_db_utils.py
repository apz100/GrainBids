import sqlite3
import os
import pandas as pd

from app.db_utils import save_df_to_db
from app.excel_to_db import DB_PATH


def test_save_df_to_db_creates_table(tmp_path):
    # Use temporary DB path to avoid clobbering user's DB
    test_db = str(tmp_path / "test_grain_bids.db")
    data = {
        'Location': ['Loc A'],
        'Name': ['Corn'],
        'Delivery': ['Jan 2027'],
        'Futures Month': ['May 2026'],
        'Futures Price': ['450'],
        'Basis': ['+5'],
        'Bushel Cash Price': ['$4.50'],
        'MT Cash Price': ['165.00'],
        'Source': ['TestSource'],
    }
    df = pd.DataFrame(data)
    save_df_to_db(df, db_path=test_db)

    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='grain_bids'")
    row = cur.fetchone()
    conn.close()
    assert row is not None
