from playwright.sync_api import sync_playwright
from wanstead_source import fetch_wanstead_all


def main():
    with sync_playwright() as p:
        df = fetch_wanstead_all(p)

    if df is None or df.empty:
        print("Wanstead: no rows returned (DataFrame is empty).")
        return

    # Drop cosmetic columns here instead of in the scraper
    df_display = df.drop(columns=["Name", "Delivery End"], errors="ignore")

    print("Wanstead DataFrame preview (first 20 rows):")
    print(df_display.head(20))
    print("\nColumns:", list(df_display.columns))
    print("Total rows:", len(df_display))

    # Optional: write a cleaned Excel just for Wanstead
    out_path = r"\\DERKS-SERVER\Current\Adam\Code\TestingGrainBidder - Copy\Wanstead_CashBids_Test.xlsx"
    df_display.to_excel(out_path, index=False)
    print(f"Wrote Wanstead test Excel to:\n{out_path}")


if __name__ == "__main__":
    main()
