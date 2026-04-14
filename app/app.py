
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
from app.db_utils import save_posted_bid

app = Flask(__name__)
# Disable posting by default; set True to enable POSTing of posted bids
ALLOW_POSTED_BIDS_EDIT = False

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


@app.route('/api/posted_bids', methods=['GET'])
def get_posted_bids():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query('SELECT id, ts, location, commodity, posted_price_mt, user, notes FROM posted_bids ORDER BY ts DESC LIMIT 200', conn)
        conn.close()
        return jsonify({'rows': df.fillna("").to_dict(orient='records')})
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/posted_bids', methods=['POST'])
def create_posted_bid():
    # Posting disabled unless explicitly enabled by config
    if not ALLOW_POSTED_BIDS_EDIT:
        return jsonify({'error': 'posting posted bids is disabled'}), 403

    try:
        data = request.get_json() or {}
        # basic validation
        if not data.get('location') or not data.get('commodity') or not data.get('posted_price_mt'):
            return jsonify({'error': 'location, commodity, and posted_price_mt are required'}), 400
        save_posted_bid({
            'location': data.get('location',''),
            'commodity': data.get('commodity',''),
            'posted_price_mt': float(data.get('posted_price_mt')) if data.get('posted_price_mt') is not None else None,
            'user': data.get('user',''),
            'notes': data.get('notes',''),
        })
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
    "delivery_end",
    "futures_month",
    "futures_price",
    "futures_change",
    "basis",
    "cash_price_bu",
    "cash_price_mt",
    "source_sheet",
]

def _refresh_db():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query('SELECT * FROM grain_bids', conn)
        conn.close()
        # Cleanup: drop numeric helper columns (ending with 'num' or containing '_num')
        drop_cols = [c for c in df.columns if c.lower().endswith('num') or c.lower().endswith('_num') or c.lower().endswith(' num')]
        if drop_cols:
            df = df.drop(columns=drop_cols)

        # If delivery_label exists (e.g. Wanstead), move into delivery_end where appropriate
        if 'delivery_label' in df.columns:
            if 'delivery_end' not in df.columns:
                df['delivery_end'] = df['delivery_label']
            else:
                mask = df['delivery_end'].astype(str).str.strip() == ''
                df.loc[mask, 'delivery_end'] = df.loc[mask, 'delivery_label']
            df = df.drop(columns=['delivery_label'])

        # Normalize futures_month entries (convert symbol-like values into month names)
        try:
            from app.normalize import _symbol_to_month_extended
            if 'futures_month' in df.columns:
                df['futures_month'] = df['futures_month'].astype(str).apply(lambda s: _symbol_to_month_extended(s) or s)
        except Exception:
            pass

        # Ensure columns are present and in desired order (only keep canonical columns)
        cols = [c for c in STANDARD_COLUMNS if c in df.columns]
        result = {
            'columns': cols,
            'rows': df[cols].fillna("").to_dict(orient="records")
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
