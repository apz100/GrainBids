# test_snobelen_playwright.py
from playwright.sync_api import sync_playwright
from snobelen_source import fetch_snobelen_all

with sync_playwright() as p:
    df = fetch_snobelen_all(p)
    print(df.head(20))
    print(df.columns.tolist(), len(df))
