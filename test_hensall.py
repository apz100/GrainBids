from playwright.sync_api import sync_playwright
from hensall_source import fetch_hensall


def main():
    with sync_playwright() as p:
        df = fetch_hensall(p)

    if df is None or df.empty:
        print("Hensall: no rows returned (DataFrame is empty).")
        return

    print("Hensall DataFrame preview (first 20 rows):")
    print(df.head(20))
    print("\nColumns:", list(df.columns))
    print("Total rows:", len(df))


if __name__ == "__main__":
    main()
