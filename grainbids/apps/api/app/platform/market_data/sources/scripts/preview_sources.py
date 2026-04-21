import sqlite3, os
DB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT DISTINCT source_sheet FROM grain_bids")
sources = [r[0] for r in cur.fetchall()]
for s in sources:
    cur.execute("SELECT * FROM grain_bids WHERE source_sheet=? LIMIT 1", (s,))
    row = cur.fetchone()
    cols = [r[1] for r in cur.execute("PRAGMA table_info('grain_bids')")]
    print('---', s)
    if row:
        for c,v in zip(cols,row):
            print(c, ':', v)
    else:
        print('no rows')

conn.close()
