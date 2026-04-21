#!/usr/bin/env python3
"""
Prune legacy columns from the grain_bids SQLite table by creating a
new table with the same data except without the specified legacy columns.

Usage:
    python scripts/prune_legacy_columns.py

This script is idempotent: if the legacy columns are not present it exits.
"""
import sqlite3
import os

DB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'grain_bids.db'))
LEGACY = {'delivery_start', 'futures_symbol', 'basis_mt', 'delivery_label'}

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    # Get existing columns
    cur.execute("PRAGMA table_info('grain_bids')")
    cols = [row[1] for row in cur.fetchall()]
    to_remove = [c for c in cols if c in LEGACY]
    if not to_remove:
        print('No legacy columns found; nothing to do.')
        conn.close()
        return
    keep = [c for c in cols if c not in LEGACY]
    cols_sql = ', '.join([f'"{c}"' for c in keep])
    cur.execute('BEGIN')
    try:
        cur.execute(f'CREATE TABLE IF NOT EXISTS grain_bids_new AS SELECT {cols_sql} FROM grain_bids')
        cur.execute('DROP TABLE grain_bids')
        # Rename new table to old name
        cur.execute('ALTER TABLE grain_bids_new RENAME TO grain_bids')
        conn.commit()
        print('Removed legacy columns:', to_remove)
    except Exception as e:
        conn.rollback()
        print('Error pruning legacy columns:', e)
    finally:
        conn.close()

if __name__ == '__main__':
    main()
