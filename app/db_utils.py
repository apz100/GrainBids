import sqlite3
import pandas as pd
import os
from typing import Dict, Any

from app.normalize import normalize_for_db
from app.excel_to_db import DB_PATH as EXCEL_DB_PATH


def save_df_to_db(df: pd.DataFrame, db_path: str | None = None):
    """Normalize and save a combined DataFrame to the `grain_bids` table.

    This function uses `app.normalize.normalize_for_db` to map incoming
    columns into the canonical schema used by the web app/tests.
    """
    if db_path is None:
        db_path = EXCEL_DB_PATH

    norm = normalize_for_db(df)

    conn = sqlite3.connect(db_path)
    try:
        norm.to_sql('grain_bids', conn, if_exists='replace', index=False)
    finally:
        conn.close()


def save_posted_bid(posted_bid: Dict[str, Any], db_path: str | None = None):
    """Insert a posted bid into a `posted_bids` table. Creates the table if needed.

    Expected keys in `posted_bid`: location, commodity, posted_price_mt, user, notes
    """
    if db_path is None:
        db_path = EXCEL_DB_PATH

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS posted_bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            location TEXT,
            commodity TEXT,
            posted_price_mt REAL,
            user TEXT,
            notes TEXT
        )
        """
    )
    conn.commit()

    c.execute(
        "INSERT INTO posted_bids (location, commodity, posted_price_mt, user, notes) VALUES (?,?,?,?,?)",
        (
            posted_bid.get('location', ''),
            posted_bid.get('commodity', ''),
            posted_bid.get('posted_price_mt', None),
            posted_bid.get('user', ''),
            posted_bid.get('notes', ''),
        ),
    )
    conn.commit()
    conn.close()
