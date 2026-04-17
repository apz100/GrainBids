# debug_ganarska_find_api.py
# Fetches the Ganaraska page source with requests (no JS) and looks for:
#   - Agricharts varname / widget parameters
#   - Any API endpoints referenced in script tags
#   - jsquote.php URLs
import re
import requests

URL = "https://www.ganaraskagrain.com/cashbidsindex"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}

r = requests.get(URL, headers=headers, timeout=30)
print("Status:", r.status_code)
print("Content-Type:", r.headers.get("content-type", ""))
print("Body length:", len(r.text))
print()

# Look for agricharts references
for i, line in enumerate(r.text.splitlines(), 1):
    line_low = line.lower()
    if any(kw in line_low for kw in [
        "agricharts", "jsquote", "varname", "quotevar",
        "dpTable", "dtn", "cash", "bid", "script src"
    ]):
        print(f"Line {i:4d}: {line.strip()[:200]}")

print()
print("--- All <script src> tags ---")
for m in re.finditer(r'<script[^>]+src=["\']([^"\']+)["\']', r.text, re.IGNORECASE):
    print(" ", m.group(1))

print()
print("--- iframe src ---")
for m in re.finditer(r'<iframe[^>]+src=["\']([^"\']+)["\']', r.text, re.IGNORECASE):
    print(" ", m.group(1))
