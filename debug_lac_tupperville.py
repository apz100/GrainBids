import re
import requests
from bs4 import BeautifulSoup

LAC_BASE_URL = "https://dtn.londonag.com/index.cfm"
DEFAULT_PARAMS = {"show": "11", "mid": "3", "layout": "19", "cmid": "all"}

def debug_one_location(location_value: str):
    params = DEFAULT_PARAMS | {"theLocation": location_value}
    resp = requests.get(LAC_BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    html = resp.text

    soup = BeautifulSoup(html, "lxml")
    tbl = soup.find("table", attrs={"name": "cashbids-data-table"})
    if not tbl:
        print("No cashbids-data-table found")
        return

    print("=== HEADER ROW ===")
    head_tr = tbl.find("tr")
    ths = head_tr.find_all("th")
    for i, th in enumerate(ths):
        print(f"  th[{i}]: {repr(th.get_text(' ', strip=True))}")

    print("\n=== DATA ROWS (first 5) ===")
    for row_idx, tr in enumerate(tbl.find_all("tr")):
        tds = tr.find_all("td")
        if not tds:
            continue
        print(f"\nROW {row_idx}, {len(tds)} tds")
        for i, td in enumerate(tds):
            txt = td.get_text(" ", strip=True)
            print(f"  td[{i}]: {repr(txt)}")
        if row_idx >= 10:
            break

if __name__ == "__main__":
    # replace this with the actual numeric value for "Tupperville"
    # you can see it in Network tab or from your existing _fetch_location_options()
    debug_one_location(location_value="13")
