import requests
print(requests.get("https://www.agricharts.com", timeout=10).status_code)