import sqlite3
import pandas as pd
import os

def save_df_to_db(df: pd.DataFrame, db_path=None):
    if db_path is None:
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))
    # Ensure all required columns exist
    required_cols = ['location','name','delivery','basis','bushel_cash_price','mt_cash_price','other1','other2','other3']
    for col in required_cols:
        if col not in df.columns:
            df[col] = ''
    df = df[required_cols]
    conn = sqlite3.connect(db_path)
    df.to_sql('grain_bids', conn, if_exists='replace', index=False)
    conn.close()
