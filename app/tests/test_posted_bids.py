import sqlite3
import os

from app.db_utils import save_posted_bid


def test_save_posted_bid(tmp_path):
    db_file = tmp_path / "posted_bids.db"
    db_path = str(db_file)
    posted = {
        'location': 'UnitTest Loc',
        'commodity': 'Corn',
        'posted_price_mt': 123.45,
        'user': 'tester',
        'notes': 'unittest'
    }
    save_posted_bid(posted, db_path=db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT location, commodity, posted_price_mt, user, notes FROM posted_bids LIMIT 1")
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 'UnitTest Loc'
    assert float(row[2]) == 123.45
