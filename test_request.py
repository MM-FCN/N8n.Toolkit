import base64
import json
import urllib.request
import time

eml = """From: Alice <alice@example.com>
To: Bob <bob@example.com>
Subject: Test email
Date: Wed, 21 Jul 2021 10:00:00 +0000
MIME-Version: 1.0
Content-Type: text/plain; charset="utf-8"

Hello Bob,
This is a test.
"""

b64 = base64.b64encode(eml.encode('utf-8')).decode('utf-8')
payload = json.dumps({"eml_payload": b64}).encode('utf-8')

url = 'http://szh2vm0372.apac.bosch.com:8000/parse-eml'
headers = {'Content-Type': 'application/json'}

for i in range(20):
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(resp.read().decode('utf-8'))
            break
    except Exception as e:
        time.sleep(0.5)
else:
    print('Failed to reach server')
