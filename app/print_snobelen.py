import sqlite3, json, os
# assume db is in project root
db = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT * FROM grain_bids WHERE source_sheet='Snobelen' LIMIT 20")
cols = [d[0] for d in cur.description]
rows = [dict(zip(cols, r)) for r in cur.fetchall()]
conn.close()
print(json.dumps(rows, indent=2))
