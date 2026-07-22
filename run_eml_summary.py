import base64
import json
import urllib.request
import sys

eml_path = r"C:\fcn\PRE ALERT MAWB 105-57500063 MAD-KIX R BOSCH _AE 079200_.eml"

try:
    with open(eml_path, 'rb') as f:
        eml_bytes = f.read()
except Exception as e:
    print('ERROR: could not read file:', e)
    sys.exit(1)

b64 = base64.b64encode(eml_bytes).decode('utf-8')
payload = json.dumps({"eml_payload": b64}).encode('utf-8')

url = 'http://127.0.0.1:8000/parse-eml'
headers = {'Content-Type': 'application/json'}

try:
    req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode('utf-8')
except Exception as e:
    print('ERROR: request failed:', e)
    sys.exit(2)

try:
    result = json.loads(text)
except Exception as e:
    print('ERROR: response is not valid JSON:', e)
    print(text[:1000])
    sys.exit(3)

if result.get('status') != 'success':
    print('Parser returned error:', result.get('message'))
    sys.exit(4)

data = result.get('data', {})
print('Subject:', data.get('subject'))
print('From:', ', '.join([f"{a.get('name') or ''} <{a.get('email')}>" for a in data.get('from', [])]))
print('To:', ', '.join([f"{a.get('name') or ''} <{a.get('email')}>" for a in data.get('to', [])]))
print('Date:', data.get('date'))
body_text = data.get('body_text') or ''
body_html = data.get('body_html') or ''
print('Body text length:', len(body_text))
print('Body html length:', len(body_html))
attachments = data.get('attachments', [])
print('Attachments count:', len(attachments))
for i, a in enumerate(attachments, 1):
    print(f"  {i}. filename={a.get('filename')}, content_type={a.get('content_type')}, size={a.get('size')}")
