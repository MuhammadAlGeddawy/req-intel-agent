import requests
from pathlib import Path

path = Path(r"E:\Muhammad\Projects\Valeo\req_intel_agent\sample_requirements.txt")

payload = {
    "document": path.read_text(encoding="utf-8"),
    "document_name": path.name,
}

response = requests.post("http://127.0.0.1:8000/analyze", json=payload, timeout=300)
print(response.json())
