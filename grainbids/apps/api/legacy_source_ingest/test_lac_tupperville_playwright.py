from lac_source import _parse_lac_dom, LAC_BASE_URL, DEFAULT_PARAMS
from playwright.sync_api import sync_playwright
from urllib.parse import urlencode

def main():
    params = DEFAULT_PARAMS | {"theLocation": "14"}  # 14 = Tupperville in your earlier tests
    url = f"{LAC_BASE_URL}?{urlencode(params)}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        html = page.content()
        browser.close()

    df = _parse_lac_dom(html, "LAC - Tupperville")
    print(df)

    df.to_excel("lac_tupperville_clean.xlsx", index=False)
    print("Wrote lac_tupperville_clean.xlsx")


if __name__ == "__main__":
    main()
