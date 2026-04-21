import sqlite3

def init_db():
    conn = sqlite3.connect('../grain_bids.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS grain_bids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT,
            name TEXT,
            delivery TEXT,
            basis TEXT,
            bushel_cash_price TEXT,
            mt_cash_price TEXT,
            other1 TEXT,
            other2 TEXT,
            other3 TEXT
        )
    ''')
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
