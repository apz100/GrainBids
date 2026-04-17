# test_lac_single.py
from lac_source import _fetch_location_options, parse_lac_html, LAC_BASE_URL, DEFAULT_PARAMS
import requests

if __name__ == "__main__":
    locations = _fetch_location_options()
    # pick one location you care about (e.g. "LAC - Tupperville")
    for value, label in locations.items():
        if "Tupperville" in label:
            loc_id = value
            break

    params = DEFAULT_PARAMS | {"theLocation": loc_id}
    resp = requests.get(LAC_BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    df = parse_lac_html(resp.text, f"LAC - Tupperville")

    print(df.to_string(index=False))
