import sqlite3, os
DB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT DISTINCT source_sheet FROM grain_bids")
sources = [r[0] for r in cur.fetchall()]
print('Source, total, missing_delivery_end, missing_futures_month')
for s in sources:
    cur.execute("SELECT COUNT(*) FROM grain_bids WHERE source_sheet=?", (s,))
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM grain_bids WHERE source_sheet=? AND (IFNULL(delivery_end,'')='')", (s,))
    miss_del = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM grain_bids WHERE source_sheet=? AND (IFNULL(futures_month,'')='')", (s,))
    miss_fut = cur.fetchone()[0]
    print(f"{s},{total},{miss_del},{miss_fut}")
conn.close()
