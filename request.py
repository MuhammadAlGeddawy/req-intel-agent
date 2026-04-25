import requests
from pathlib import Path

path = Path(r"E:\Muhammad\Projects\Valeo\req_intel_agent\sample_requirements.txt")

payload = {
    "document": path.read_text(encoding="utf-8"),
    "document_name": path.name,
}

print("Sending request to Docker agent... (this might take a minute)")
response = requests.post("http://127.0.0.1:8000/analyze", json=payload, timeout=300)

# NEW: Check if the request was successful
if response.status_code == 200:
    print("Success!")
    print(response.json())
else:
    print(f"❌ Error! Status Code: {response.status_code}")
    print("Response Content (The real error):")
    print(response.text) # This will show us the HTML error page or raw error message