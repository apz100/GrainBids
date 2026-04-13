from playwright.sync_api import sync_playwright

URL = "https://www.ganaraskagrain.com/cashbidsindex"

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # log failed requests – this will tell us if agricharts.com is blocked
        def on_request_failed(req):
            print("[REQ FAILED]", req.url, "->", req.failure)

        page.on("request_failed", on_request_failed)

        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(8000)  # give JS some time regardless

        # how many tables does headless Chromium see?
        tables = page.query_selector_all("table")
        print("Playwright sees", len(tables), "<table> elements")

        # dump any that look like the bids grid
        for i, t in enumerate(tables):
            html = t.inner_html()[:500]
            print(f"\n--- TABLE {i} (first 500 chars) ---\n{html}")

        browser.close()

if __name__ == "__main__":
    main()
