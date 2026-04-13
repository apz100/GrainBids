import requests
from bs4 import BeautifulSoup
import re

LAC_BASE_URL = "https://dtn.londonag.com/index.cfm"
PARAMS = {"show": "11", "mid": "3", "layout": "19", "cmid": "all", "theLocation": "14"}  # Tupperville


def main():
    print("Fetching page...")
    html = requests.get(LAC_BASE_URL, params=PARAMS).text
    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table", attrs={"name": "cashbids-data-table"})
    rows = table.find_all("tr")

    print("\n=== Inspecting first 3 data rows (after header) ===\n")

    # Skip header row, inspect rows 1–3
    for i, tr in enumerate(rows[1:4], start=1):
        tds = tr.find_all("td")
        print(f"\nROW {i} — {len(tds)} TDs")

        for col_index, td in enumerate(tds):
            print(f"\n  --- td[{col_index}] RAW HTML ---")
            print(str(td))

            print("\n  text ->", td.get_text(" ", strip=True))

            # Extract displayNumber() occurrences
            scripts = td.find_all("script")
            nums = []
            for s in scripts:
                txt = s.get_text(" ", strip=True)
                found = re.findall(r"displayNumber\(\s*([-+]?[0-9]*\.?[0-9]+)", txt)
                nums.extend(found)
                print("    script:", txt)
                print("    displayNumber matches:", found)

        print("\n============================\n")


if __name__ == "__main__":
    main()
