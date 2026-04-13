from app import excel_to_db
import sqlite3, json

excel_to_db.excel_to_db()
conn = sqlite3.connect(excel_to_db.DB_PATH)
rows = None
try:
    cur = conn.cursor()
    cur.execute("SELECT * FROM grain_bids WHERE source_sheet='Snobelen' LIMIT 20")
    cols = [d[0] for d in cur.description]
    data = cur.fetchall()
    rows = [dict(zip(cols, r)) for r in data]
finally:
    conn.close()
print(json.dumps(rows, indent=2))
