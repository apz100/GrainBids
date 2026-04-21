# test_ganaraska_jsquote_dump.py
import requests

url = "https://www.agricharts.com/marketdata/jsquote.php?varname=quotevar91161&symbols=ZCH26,ZCZ26,ZCZ27,ZSF26,ZSX26,ZSX27,ZWN26,ZWN27&fields=name,month,last&user=&pass=&settle=0&exchsyms=&display_ice=&ice_exchanges=&currencyconv=&displayType=bids"

r = requests.get(url, timeout=30)
r.raise_for_status()

text = r.text
print("Length:", len(text))
print("First 40 lines:")
for i, line in enumerate(text.splitlines()[:40], start=1):
    print(f"{i:02d}: {line}")


import requests
print(requests.get("https://www.agricharts.com", timeout=10).status_code)
