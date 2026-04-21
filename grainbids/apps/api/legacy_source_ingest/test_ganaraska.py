# test_ganaraska.py
from playwright.sync_api import sync_playwright
from ganaraska_source import fetch_ganaraska


def main():
    with sync_playwright() as p:
        df = fetch_ganaraska(p)

    if df is None or df.empty:
        print("Ganaraska: no rows returned (DataFrame is empty).")
        return

    print("Ganaraska DataFrame preview (first 20 rows):")
    print(df.head(20))
    print("\nColumns:", list(df.columns))
    print("Total rows:", len(df))


if __name__ == "__main__":
    main()
