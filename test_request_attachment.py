import base64
import json
import urllib.request
import time

eml = """From: Erin <erin@example.com>
To: Frank <frank@example.com>
Subject: Attachment Test
Date: Thu, 22 Jul 2021 13:00:00 +0000
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="BOUNDARY"

--BOUNDARY
Content-Type: text/plain; charset="utf-8"

Hi Frank,
See attached.

--BOUNDARY
Content-Type: text/plain; name="hello.txt"
Content-Disposition: attachment; filename="hello.txt"
Content-Transfer-Encoding: base64

aGVsbG8K

--BOUNDARY--
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
