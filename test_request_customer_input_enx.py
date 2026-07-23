import json
import time
import urllib.request

payload = json.dumps(
    {
        "customerName": "enx-demo",
        "containerNo": ["ENX-0001", "ENX-0002"],
        "resumeUrl": "https://example.com/resume/enx-task-001",
    }
).encode("utf-8")

url = "http://127.0.0.1:8000/api/customer-input"
headers = {"Content-Type": "application/json"}

for _ in range(20):
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(resp.read().decode("utf-8"))
            break
    except Exception:
        time.sleep(0.5)
else:
    print("Failed to reach server")
