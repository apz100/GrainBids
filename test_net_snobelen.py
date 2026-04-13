import requests

urls = [
    "https://snobelenfarms.com",
    "https://snobelenfarms.com/wp-content/plugins/mv_blocks/blocks/dtn/feed.php?commodity=all&location=Brantford",
    "https://snobelenfarms.com/wp-content/plugins/mv_blocks/blocks/dtn/feed.php?commodity=all&location=R,%20L,%20D,%20B,%20T,%20L(B)",
]

for url in urls:
    print("Testing:", url)
    try:
        r = requests.get(url, timeout=15)
        print("  -> OK, status", r.status_code)
    except Exception as e:
        print("  -> ERROR:", repr(e))
