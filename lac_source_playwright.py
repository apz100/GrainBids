# lac_source_playwright.py

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd

LAC_BASE_URL = "https://dtn.londonag.com/index.cfm"
DEFAULT_PARAMS = {"show": "11", "mid": "3", "layout": "19", "cmid": "all"}

def parse_lac_dom(html: str, location_name: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table", attrs={"name": "cashbids-data-table"})
    records = []

    for tbl in tables:
        # Commodity label just above the table
        label_node = tbl.find_previous(
            lambda tag: tag.name in ["h1", "h2", "h3", "h4", "b", "strong", "font", "span"]
            and tag.get_text(strip=True)
        )
        commodity = label_node.get_text(" ", strip=True).strip() if label_node else "LAC Cash Bid"

        rows = tbl.find_all("tr")
        if not rows:
            continue

        # skip header row
        for tr in rows[1:]:
            tds = tr.find_all("td")
            if len(tds) < 8:
                continue

            delivery = tds[0].get_text(" ", strip=True)
            month    = tds[1].get_text(" ", strip=True)
            futures  = tds[2].get_text(" ", strip=True)
            change   = tds[3].get_text(" ", strip=True)
            basis    = tds[4].get_text(" ", strip=True)
            cash     = tds[5].get_text(" ", strip=True)
            price_t  = tds[6].get_text(" ", strip=True)
            basis_t  = tds[7].get_text(" ", strip=True)

            # skip empty / non-bid rows
            if not cash and not price_t and not futures:
                continue

            records.append(
                {
                    "Location":          location_name,
                    "Name":              commodity,
                    "Delivery":          delivery,
                    "Delivery End":      "",
                    "Futures Month":     month,
                    "Futures Price":     futures,
                    "Change":            change,
                    "Basis":             basis,
                    "Bushel Cash Price": cash,
                    "MT Cash Price":     price_t,
                    "Basis / (Tonnes)":  basis_t,
                }
            )

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    expected_cols = [
        "Location", "Name", "Delivery", "Delivery End",
        "Futures Month", "Futures Price", "Change",
        "Basis", "Bushel Cash Price", "MT Cash Price", "Basis / (Tonnes)",
    ]
    for c in expected_cols:
        if c not in df.columns:
            df[c] = ""
    df = df[expected_cols]

    df.attrs["web_headers"] = {
        "Location":          "Location",
        "Name":              "Commodity",
        "Delivery":          "Delivery",
        "Futures Month":     "Month",
        "Futures Price":     "Futures",
        "Change":            "Change",
        "Basis":             "Basis",
        "Bushel Cash Price": "Cash Price",
        "MT Cash Price":     "Price / (Tonnes)",
        "Basis / (Tonnes)":  "Basis / (Tonnes)",
    }

    return df


def fetch_lac_all_via_playwright() -> pd.DataFrame:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1) get locations using normal requests OR hard-code ids if you prefer
        #    simplest for now: hit Tupperville only to validate
        locations = {"14": "Tupperville"}  # once tested, plug in _fetch_location_options() output

        all_rows = []
        for loc_id, loc_name in locations.items():
            url = f"{LAC_BASE_URL}?show=11&mid=3&layout=19&cmid=all&theLocation={loc_id}"
            page.goto(url, wait_until="networkidle")
            html = page.content()
            df_loc = parse_lac_dom(html, f"LAC - {loc_name}")
            if not df_loc.empty:
                print(f"[LAC OK] {loc_name}: {len(df_loc)} rows")
                all_rows.append(df_loc)
            else:
                print(f"[LAC WARN] {loc_name}: no rows parsed")

        browser.close()

    if not all_rows:
        return pd.DataFrame()
    return pd.concat(all_rows, ignore_index=True)
