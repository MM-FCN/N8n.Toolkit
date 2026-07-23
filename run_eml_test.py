import base64
import json
import urllib.request
import sys

# Path to the .eml file (from user)
eml_path = r"C:\fcn\PRE ALERT MAWB 105-57500063 MAD-KIX R BOSCH _AE 079200_.eml"

try:
    with open(eml_path, 'rb') as f:
        eml_bytes = f.read()
except Exception as e:
    print('ERROR: could not read file:', e)
    sys.exit(1)

b64 = base64.b64encode(eml_bytes).decode('utf-8')
payload = json.dumps({"eml_payload": b64}).encode('utf-8')

url = 'http://szh2vm0372.apac.bosch.com:8000/parse-eml'
headers = {'Content-Type': 'application/json'}

try:
    req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=20) as resp:
        print(resp.read().decode('utf-8'))
except Exception as e:
    print('ERROR: request failed:', e)
    sys.exit(2)
