
from flask import Flask, jsonify, render_template, request
import pandas as pd
import sqlite3
import time
import sys
import os
from playwright.sync_api import sync_playwright

# Add parent directory to sys.path to import source modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import all fetch functions
from bunge_source import fetch_bunge_all
from lac_source import fetch_lac_all
from hensall_source import fetch_hensall
from dg_global_source import fetch_dg_global
from glg_source import fetch_glg_all
from ganaraska_source import fetch_ganaraska
from snobelen_source import fetch_snobelen_all
from us_dtn_source import fetch_us_dtn
from us_agricharts_source import fetch_us_agricharts
from wanstead_source import fetch_wanstead_all
from agricharts_source import fetch_agricharts_bids
from andersons_source import fetch_andersons_all

app = Flask(__name__)

@app.route('/api/debug_db')
def debug_db():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query('SELECT * FROM grain_bids LIMIT 5', conn)
        conn.close()
        return jsonify({
            'columns': list(df.columns),
            'rows': df.fillna("").to_dict(orient="records")
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/')
def index():
    return render_template('index.html')





# In-memory cache for DB data
_cached_db = None
_cache_db_timestamp = 0
_cache_db_ttl = 24 * 60 * 60  # 1 day in seconds


# The Excel loader now writes normalized STANDARD_COLUMNS into the DB.
STANDARD_COLUMNS = [
    "location",
    "commodity",
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
    "source_sheet",
]

def _refresh_db():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query('SELECT * FROM grain_bids', conn)
        conn.close()
        # Ensure columns are present and in desired order where possible
        cols = [c for c in STANDARD_COLUMNS if c in df.columns] + [c for c in df.columns if c not in STANDARD_COLUMNS]
        result = {
            'columns': cols,
            'rows': df.fillna("").to_dict(orient="records")
        }
    except Exception as e:
        print(f"Error loading DB: {e}", file=sys.stderr)
        result = {'columns': [], 'rows': []}
    return result

@app.route('/api/prices')
def get_prices():
    global _cached_db, _cache_db_timestamp
    now = time.time()
    if _cached_db is None or (now - _cache_db_timestamp) > _cache_db_ttl:
        _cached_db = _refresh_db()
        _cache_db_timestamp = now
    data = _cached_db
    # Filtering
    location = request.args.get('location', '').strip().lower()
    crop = request.args.get('crop', '').strip().lower()
    rows = data['rows']
    if location:
        rows = [row for row in rows if location in str(row.get('location', '')).lower()]
    if crop:
        rows = [row for row in rows if crop in str(row.get('commodity', '')).lower()]
    return jsonify({'columns': data['columns'], 'rows': rows})

if __name__ == '__main__':
    app.run(debug=True)
