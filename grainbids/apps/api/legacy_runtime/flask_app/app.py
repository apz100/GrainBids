
from flask import Flask, jsonify, render_template, request
import pandas as pd
import sqlite3
import time
import sys
import os
from playwright.sync_api import sync_playwright

# Add parent directory to sys.path to import source modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Note: scraper modules are not imported at app startup to avoid
# heavy import-time dependencies (Playwright, network). Import them
# lazily where needed. Keep DB utils import minimal.
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


@app.route('/api/companies')
def get_companies():
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query('SELECT DISTINCT source_sheet FROM grain_bids WHERE source_sheet IS NOT NULL', conn)
        conn.close()
        companies = sorted([str(x) for x in df['source_sheet'].fillna("").unique() if str(x).strip()])
        return jsonify({'companies': companies})
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

        # If delivery_label exists (e.g. Wanstead), parse and move into delivery_end where appropriate
        if 'delivery_label' in df.columns:
            import re
            def _parse_delivery_label(lbl):
                if lbl is None:
                    return ''
                s = str(lbl).strip()
                if not s:
                    return ''
                # Remove common trailing words like 'Elev', 'Branch', 'Locations', etc.
                s = re.sub(r"\b(Elev|Elevator|Elevators|Branch|Branches|Locations|Loc|Location|Elev\.)\b", "", s, flags=re.I).strip()
                # Look for short month + year like 'Apr-26', 'Apr 26' or 'Apr 2026'
                # capture optional separator to distinguish day vs year shorthand
                m = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?([\s\-\.\xa0]*)(\d{2,4})\b", s, flags=re.I)
                if m:
                    mon = m.group(1).title()[:3]
                    sep = m.group(2) or ''
                    yr = m.group(3)
                    # If a full 4-digit year appears elsewhere, prefer it
                    y4 = re.search(r"(\d{4})", s)
                    if y4:
                        yr = y4.group(1)
                    # If two-digit and separator is hyphen/dot or non-breaking-space, treat as year shorthand
                    if len(yr) == 2:
                        if sep.strip() in ('-', '.') or '\xa0' in sep:
                            yr = '20' + yr
                        else:
                            # ambiguous whitespace; if the two-digit looks like a day (1-31) and there's no 4-digit year, skip
                            if 1 <= int(yr) <= 31 and not y4:
                                return ''
                            yr = '20' + yr
                    return f"{mon} {yr}"
                # Look for full month name + year
                m2 = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b\s*(\d{2,4})", s, flags=re.I)
                if m2:
                    mon = m2.group(1).title()[:3]
                    yr = m2.group(2)
                    if len(yr) == 2 and 1 <= int(yr) <= 31:
                        return ''
                    if len(yr) == 2:
                        yr = '20' + yr
                    return f"{mon} {yr}"
                # If nothing parsed, return original trimmed string (UI will hide legacy values)
                return s

            if 'delivery_end' not in df.columns:
                df['delivery_end'] = df['delivery_label'].apply(_parse_delivery_label)
            else:
                mask = df['delivery_end'].astype(str).str.strip() == ''
                df.loc[mask, 'delivery_end'] = df.loc[mask, 'delivery_label'].apply(_parse_delivery_label)
            # We'll keep delivery_label in DB briefly but drop legacy from the UI view later

        # Also normalize existing delivery_end values (some sources wrote short labels there)
        try:
            import re
            def _parse_delivery_label_local(lbl):
                if lbl is None:
                    return ''
                s = str(lbl).strip()
                if not s:
                    return ''
                s = re.sub(r"\b(Elev|Elevator|Elevators|Branch|Branches|Locations|Loc|Location|Elev\.)\b", "", s, flags=re.I).strip()
                m = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?([\s\-\.\xa0]*)(\d{2,4})\b", s, flags=re.I)
                if m:
                    mon = m.group(1).title()[:3]
                    sep = m.group(2) or ''
                    yr = m.group(3)
                    y4 = re.search(r"(\d{4})", s)
                    if y4:
                        yr = y4.group(1)
                    if len(yr) == 2:
                        if sep.strip() in ('-', '.') or '\xa0' in sep:
                            yr = '20' + yr
                        else:
                            if 1 <= int(yr) <= 31 and not y4:
                                return ''
                            yr = '20' + yr
                    return f"{mon} {yr}"
                m2 = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b\s*(\d{2,4})", s, flags=re.I)
                if m2:
                    mon = m2.group(1).title()[:3]
                    yr = m2.group(2)
                    if len(yr) == 2 and 1 <= int(yr) <= 31:
                        return ''
                    if len(yr) == 2:
                        yr = '20' + yr
                    return f"{mon} {yr}"
                return s
            if 'delivery_end' in df.columns:
                parsed = df['delivery_end'].astype(str).apply(_parse_delivery_label_local)
                # Replace only when parsed looks like 'Mon YYYY' and original does not
                mask_replace = parsed.str.match(r'^[A-Z][a-z]{2} \d{4}$') & ~df['delivery_end'].astype(str).str.match(r'^[A-Z][a-z]{2} \d{4}$')
                if mask_replace.any():
                    df.loc[mask_replace, 'delivery_end'] = parsed[mask_replace]
        except Exception:
            pass

        # Normalize futures_month entries (convert symbol-like values into month names)
        try:
            from app.normalize import _symbol_to_month_extended
            # Normalize existing futures_month values (if they contain symbols)
            if 'futures_month' in df.columns:
                df['futures_month'] = df['futures_month'].astype(str).apply(lambda s: _symbol_to_month_extended(s) or s)
            # If a raw futures_symbol column exists, use it to fill empty futures_month
            if 'futures_symbol' in df.columns:
                mask = ~df['futures_symbol'].isnull() & (df.get('futures_month', '').astype(str).str.strip() == '')
                if mask.any():
                    df.loc[mask, 'futures_month'] = df.loc[mask, 'futures_symbol'].astype(str).apply(lambda s: _symbol_to_month_extended(s) or s)
            # If futures_month still empty, try to derive from delivery_end (next calendar month)
            if 'futures_month' in df.columns and 'delivery_end' in df.columns:
                import calendar
                import re
                def _next_month_from_delivery(s):
                    if not s:
                        return ''
                    s = str(s).strip()
                    # match 'Mon YYYY' or 'Month YYYY' or formats like 'Apr-26' or 'Apr 26'
                    m = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\b[\s\-\.]*(\d{2,4})\b", s, flags=re.I)
                    if not m:
                        return ''
                    mon = m.group(1)[:3].title()
                    yr = m.group(2)
                    # If two-digit number looks like a day (1-31), don't treat as year
                    if len(yr) == 2 and 1 <= int(yr) <= 31:
                        return ''
                    if len(yr) == 2:
                        yr = '20' + yr
                    try:
                        month_num = list(calendar.month_abbr).index(mon)
                    except Exception:
                        return ''
                    # compute next month
                    next_month = month_num + 1
                    next_year = int(yr)
                    if next_month == 13:
                        next_month = 1
                        next_year += 1
                    next_mon_name = calendar.month_name[next_month][:3]
                    return f"{next_mon_name} {next_year}"

                mask_empty = df['futures_month'].astype(str).str.strip() == ''
                if mask_empty.any():
                    df.loc[mask_empty, 'futures_month'] = df.loc[mask_empty, 'delivery_end'].astype(str).apply(lambda s: _next_month_from_delivery(s) or '')
                # Multi-source inference: fill missing futures_month/futures_price using other sources
                try:
                    from app.excel_to_db import parse_number
                    import datetime
                    # helper: parse 'Mon YYYY' or 'Month YYYY' into (year,month)
                    def _parse_month_str(s):
                        if not s:
                            return None
                        s = str(s).strip()
                        m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\b\s*(\d{4})", s, flags=re.I)
                        if not m:
                            return None
                        mon = m.group(1)[:3].title()
                        yr = int(m.group(2))
                        try:
                            month_num = list(calendar.month_abbr).index(mon)
                        except Exception:
                            return None
                        return (yr, month_num)

                    # build commodity -> available months mapping
                    now = datetime.date.today()
                    comm_months = {}
                    for _, row in df.iterrows():
                        comm = str(row.get('commodity','')).strip()
                        fm = str(row.get('futures_month','')).strip()
                        fp = row.get('futures_price','')
                        parsed = _parse_month_str(fm)
                        if parsed:
                            comm_months.setdefault(comm, []).append((parsed, fp))

                    # for each commodity, determine front month and new-crop month
                    preferred_new = {'corn': 'Dec', 'soybeans': 'Nov'}
                    comm_targets = {}
                    for comm, items in comm_months.items():
                        # items: list of ((year,month), price)
                        months = sorted([ym for ym, _ in items])
                        # find front month as first >= now
                        front = None
                        for (y,m) in months:
                            if datetime.date(y, m, 1) >= datetime.date(now.year, now.month, 1):
                                front = (y,m)
                                break
                        if front is None and months:
                            front = months[0]
                        # find new-crop month (Dec for corn, Nov for soybeans)
                        lc = comm.lower()
                        new_month_name = None
                        for key in preferred_new:
                            if key in lc:
                                new_month_name = preferred_new[key]
                                break
                        new_target = None
                        if new_month_name:
                            # choose earliest year for that month >= now.year
                            candidates = [ym for ym, _ in items if list(calendar.month_abbr)[ym[1]] == new_month_name[:3]]
                            if candidates:
                                # pick candidate with year >= now.year else earliest
                                cands = sorted(candidates)
                                sel = None
                                for (y,m) in cands:
                                    if y >= now.year:
                                        sel = (y,m); break
                                if sel is None:
                                    sel = cands[0]
                                new_target = sel
                        comm_targets[comm] = {'front': front, 'new': new_target, 'items': items}

                    # Fill missing futures_month based on delivery_end crop heuristics
                    def _is_new_crop(delivery):
                        if not delivery:
                            return False
                        m = re.search(r"(\d{4})\s*Crop", str(delivery), flags=re.I)
                        if m:
                            try:
                                year = int(m.group(1))
                                return year >= now.year
                            except Exception:
                                return False
                        return False

                    for idx, row in df.iterrows():
                        if str(row.get('futures_month','')).strip() == '':
                            comm = str(row.get('commodity','')).strip()
                            targets = comm_targets.get(comm)
                            chosen = None
                            if targets:
                                if _is_new_crop(row.get('delivery_end','')) and targets.get('new'):
                                    chosen = targets['new']
                                else:
                                    chosen = targets['front']
                            if chosen:
                                fm_str = f"{calendar.month_name[chosen[1]][:3]} {chosen[0]}"
                                df.at[idx, 'futures_month'] = fm_str
                                # fill futures_price by taking median of available prices for this commodity+month
                                prices = []
                                for (ym, price) in targets.get('items', []) if targets else []:
                                    if ym == chosen and price:
                                        p = parse_number(price)
                                        if p is not None:
                                            prices.append(p)
                                if prices:
                                    # median
                                    prices.sort()
                                    mid = prices[len(prices)//2]
                                    df.at[idx, 'futures_price'] = str(mid)
                except Exception:
                    pass
        except Exception:
            pass

        # Remove legacy columns permanently from the view
        legacy = {'delivery_start', 'futures_symbol', 'basis_mt', 'delivery_label'}
        drop_legacy = [c for c in df.columns if c in legacy]
        if drop_legacy:
            df = df.drop(columns=drop_legacy)

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
    # Allow forcing a cache refresh via ?refresh=1
    force = request.args.get('refresh', '') in ('1', 'true', 'yes')
    if force or _cached_db is None or (now - _cache_db_timestamp) > _cache_db_ttl:
        _cached_db = _refresh_db()
        _cache_db_timestamp = now
    data = _cached_db
    # Filtering
    location = request.args.get('location', '').strip().lower()
    crop = request.args.get('crop', '').strip().lower()
    company = request.args.get('company', '').strip().lower()
    rows = data['rows']
    if location:
        rows = [row for row in rows if location in str(row.get('location', '')).lower()]
    if crop:
        rows = [row for row in rows if crop in str(row.get('commodity', '')).lower()]
    if company:
        rows = [row for row in rows if company in str(row.get('source_sheet', '')).lower()]
    return jsonify({'columns': data['columns'], 'rows': rows})

if __name__ == '__main__':
    app.run(debug=True)
