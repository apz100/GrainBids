import sqlite3, os, json
DB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))
conn = sqlite3.connect(DB)
cur = conn.cursor()
cols = [r[1] for r in cur.execute("PRAGMA table_info('grain_bids')")]
print(json.dumps(cols, indent=2))
conn.close()
