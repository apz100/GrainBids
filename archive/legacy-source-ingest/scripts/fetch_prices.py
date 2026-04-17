import requests, json
r = requests.get('http://127.0.0.1:5000/api/prices?refresh=1', timeout=10)
print('status', r.status_code)
try:
    j = r.json()
    print('columns:', j.get('columns'))
    print('sample row keys:', list(j.get('rows')[0].keys()) if j.get('rows') else 'no rows')
except Exception as e:
    print('error', e)
    print(r.text[:200])
