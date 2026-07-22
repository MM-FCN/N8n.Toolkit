import base64
import json
import urllib.request
import time

eml = """From: Carol <carol@example.com>
To: Dave <dave@example.com>
Subject: HTML Test
Date: Thu, 22 Jul 2021 12:00:00 +0000
MIME-Version: 1.0
Content-Type: text/html; charset="utf-8"

<html><body><h1>Hello Dave</h1><p>This is <b>HTML</b> content.</p></body></html>
"""

b64 = base64.b64encode(eml.encode('utf-8')).decode('utf-8')
payload = json.dumps({"eml_payload": b64}).encode('utf-8')

url = 'http://127.0.0.1:8000/parse-eml'
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
