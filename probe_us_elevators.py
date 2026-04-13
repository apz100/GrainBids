"""
probe_us_elevators.py

Probes each US elevator's official website to find their cash bid page URL
and detect whether it uses Agricharts (writeBidRow/jsquote) or DTN (CashBidTable).

Outputs a ready-to-paste config.toml [[us.elevators]] block.
"""

import re
import time
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
}
TIMEOUT = 15

# All 81 companies: (display_name, official_base_url)
ELEVATORS = [
    ("Ace Ethanol",                   "https://www.aceethanol.com"),
    ("ADM",                           "https://www.adm.com"),
    ("AGP",                           "https://www.agp.com"),
    ("Ag Partners",                   "https://agpartners.net"),
    ("Ag Plus",                       "https://www.agplusinc.com"),
    ("Ag State",                      "https://www.agstate.org"),
    ("Agtegra",                       "https://www.agtegra.com"),
    ("Ag Valley",                     "https://www.agvalley.com"),
    ("ALCIVIA",                       "https://www.alcivia.com"),
    ("Al-Corn",                       "https://www.al-corn.com"),
    ("Alliance Grain",                "https://www.alliance-grain.com"),
    ("Allied Cooperative",            "https://www.allied.coop"),
    ("Aurora Coop",                   "https://auroracoop.com"),
    ("Brubaker",                      "https://www.brubakergrain.com"),
    ("Bunge",                         "https://www.bungeag.com"),
    ("Cardinal Ethanol",              "https://www.cardinalethanol.com"),
    ("CFS",                           "https://www.cfscoop.com"),
    ("CRC",                           "https://www.centralregioncoop.com"),
    ("CVA",                           "https://www.cvacoop.com"),
    ("CGB",                           "https://www.cgb.com"),
    ("CFE",                           "https://www.cfe.coop"),
    ("Country Visions",               "https://www.countryvisions.coop"),
    ("Elite Octane",                  "https://www.eliteoctane.net"),
    ("Evergreen FS",                  "https://www.evergreenfsinc.com"),
    ("Farmers Cooperative Dorchester","https://www.farmerscooperativedorchester.com"),
    ("FCS",                           "https://www.fcs-grain.com"),
    ("Farmers Win Coop",              "https://www.farmerswin.com"),
    ("Farmward",                      "https://www.farmward.coop"),
    ("Five Star Coop",                "https://www.fivestarcoop.com"),
    ("FVC",                           "https://www.fvc.coop"),
    ("Frontier Ag",                   "https://www.frontierag.com"),
    ("Frontier Coop",                 "https://www.frontiercooperative.com"),
    ("Garden City Coop",              "https://www.gardencitycoop.com"),
    ("Gateway FS",                    "https://www.gatewayfs.com"),
    ("Gold Eagle Coop",               "https://goldeaglecoop.com"),
    ("Green Plains",                  "https://www.gpreinc.com"),
    ("Heartland Coop",                "https://www.heartlandcoop.com"),
    ("Hensall Co-op",                 "https://www.hensalldistrict.com"),
    ("Heritage Cooperative",          "https://www.heritagecooperative.com"),
    ("Heritage Grain Cooperative",    "https://www.heritagegrain.com"),
    ("Hull Coop",                     "https://www.hullcoop.com"),
    ("IAS",                           "https://www.iowaagsystems.com"),
    ("Jennie-O",                      "https://www.jennieo.com"),
    ("Kanza Coop",                    "https://www.kanzacoop.com"),
    ("Keller",                        "https://www.kellergrain.com"),
    ("Key Coop",                      "https://www.key.coop"),
    ("Kokomo Grain",                  "https://www.kokomograin.com"),
    ("Landus",                        "https://www.landus.ag"),
    ("Legacy Farmers",                "https://www.legacyfarmers.com"),
    ("Linn Coop",                     "https://www.linncoop.com"),
    ("Luckey Farmers",                "https://www.luckeyfarmers.com"),
    ("Mercer Landmark",               "https://www.mercerlandmark.com"),
    ("Michael Foods",                 "https://www.michaelfoods.com"),
    ("Mid Iowa Coop",                 "https://www.midiowacoop.com"),
    ("Midland Marketing",             "https://www.midlandmarketing.com"),
    ("Midway Coop",                   "https://www.midwaycoop.com"),
    ("NEW Coop",                      "https://www.newcoop.com"),
    ("New Vision Coop",               "https://www.newvisioncoop.com"),
    ("Nexus",                         "https://www.nexusag.com"),
    ("Pilgrims Gold'n Plum",          "https://www.pilgrims.com"),
    ("POET",                          "https://www.poet.com"),
    ("Pro Ag",                        "https://www.proag.com"),
    ("PRO Coop",                      "https://www.procoop.com"),
    ("Ray Carroll",                   "https://www.raycarrollcountygraingrowersassociation.com"),
    ("Skyland Grain",                 "https://www.skylandgrain.com"),
    ("Smithfield",                    "https://www.smithfieldfoods.com"),
    ("Star of the West",              "https://www.starofthewest.com"),
    ("StateLine Coop",                "https://www.statelinecoop.com"),
    ("Sunrise",                       "https://www.sunrise.coop"),
    ("Superior Ag",                   "https://www.superiorag.com"),
    ("Synergy",                       "https://www.synergycoop.com"),
    ("The Andersons",                 "https://www.andersons.com"),
    ("TGM",                           "https://www.tgmgrain.com"),
    ("United Coop",                   "https://www.unitedcoop.com"),
    ("UFC",                           "https://www.ufc.coop"),
    ("Ursa Farmers Coop",             "https://www.ursafarmers.com"),
    ("Valero",                        "https://www.valero.com"),
    ("West-Con",                      "https://www.west-con.com"),
    ("Wheaton Dumont",                "https://www.wheatondumont.com"),
    ("Wheaton Grain",                 "https://www.wheaton-grain.com"),
    ("Winchester Ag",                 "https://www.winchesterag.com"),
]

# Common cash bid path suffixes to try
BID_PATHS = [
    "/markets/cash.php",
    "/markets/cash.php?location_filter=",
    "/cash-bids",
    "/grain/cash-bids",
    "/grain-bids",
    "/businesses/grain/grain-bids",
    "/grain/bids",
    "/markets/bids",
    "/bids.htm",
    "/grain/prices",
    "/grain-prices",
    "/cash_bids",
    "/markets",
    "/grain",
]

# Patterns that identify the widget type
AGRICHARTS_RX = re.compile(
    r"writeBidRow\s*\(|jsquote\.php\?varname|agricharts\.com/marketdata/jsquote",
    re.IGNORECASE,
)
DTN_RX = re.compile(
    r"CashBidTable\s*\(|companyID\s*:\s*\d+|stonexCashBid|/dtncashbidwidget/|dtn\.com",
    re.IGNORECASE,
)
BID_CONTENT_RX = re.compile(
    r"cash.bid|grain.bid|grain.price|basis|futures.price|delivery",
    re.IGNORECASE,
)


def detect_type(html: str) -> str:
    if AGRICHARTS_RX.search(html):
        return "agricharts"
    if DTN_RX.search(html):
        return "dtn"
    return "unknown"


def fetch(url: str) -> tuple[int, str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


def find_bid_links_in_page(html: str, base: str) -> list[str]:
    """Scan homepage for links that look like cash bid pages."""
    candidates = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', html):
        if re.search(r'cash.bid|grain.bid|grain.price|bid|market|grain', href, re.IGNORECASE):
            if href.startswith("http"):
                candidates.append(href)
            elif href.startswith("/"):
                candidates.append(base.rstrip("/") + href)
    return list(dict.fromkeys(candidates))  # deduplicate, preserve order


def probe_elevator(name: str, base: str) -> tuple[str | None, str]:
    """
    Returns (bid_url, type) or (None, "") if not found.
    """
    base = base.rstrip("/")

    # 1. Try known paths directly
    for path in BID_PATHS:
        url = base + path
        status, html = fetch(url)
        if status == 200 and BID_CONTENT_RX.search(html):
            typ = detect_type(html)
            return url, typ
        time.sleep(0.2)

    # 2. Scrape homepage for bid links
    status, homepage = fetch(base)
    if status == 200:
        links = find_bid_links_in_page(homepage, base)
        for link in links[:8]:  # try top 8 candidates
            status2, html2 = fetch(link)
            if status2 == 200 and BID_CONTENT_RX.search(html2):
                typ = detect_type(html2)
                return link, typ
            time.sleep(0.2)

    return None, ""


def main():
    results = []
    not_found = []

    for name, base in ELEVATORS:
        print(f"Probing: {name} ({base}) ...", end=" ", flush=True)
        bid_url, typ = probe_elevator(name, base)
        if bid_url:
            print(f"FOUND [{typ}] -> {bid_url}")
            results.append((name, bid_url, typ))
        else:
            print("not found")
            not_found.append((name, base))
        time.sleep(0.3)

    print("\n\n" + "=" * 70)
    print("# PASTE THIS INTO config.toml under [us]")
    print("=" * 70 + "\n")

    for name, url, typ in results:
        print(f"[[us.elevators]]")
        print(f'enabled = true')
        print(f'type    = "{typ}"')
        print(f'name    = "{name}"')
        print(f'url     = "{url}"')
        print()

    if not_found:
        print("# ── NOT FOUND ──────────────────────────────────────────────────────")
        for name, base in not_found:
            print(f"# NOT FOUND: {name} — official site: {base}")

    print(f"\n# Summary: {len(results)} found, {len(not_found)} not found out of {len(ELEVATORS)} total")


if __name__ == "__main__":
    main()
