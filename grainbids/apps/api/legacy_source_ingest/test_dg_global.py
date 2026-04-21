# test_dg_global.py
from playwright.sync_api import sync_playwright
from dg_global_source import fetch_dg_global


def main():
    with sync_playwright() as p:
        df = fetch_dg_global(p)

    if df is None or df.empty:
        print("DG Global: no rows returned (DataFrame is empty).")
        return

    print("DG Global DataFrame preview (first 20 rows):")
    print(df.head(20))
    print("\nColumns:", list(df.columns))
    print("Total rows:", len(df))


if __name__ == "__main__":
    main()
