"""
docker compose up -d --force-recreate --build agent-service
"""

import time
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8081"
path = Path(__file__).resolve().parent / "sample_requirements.txt"

payload = {
    "document": path.read_text(encoding="utf-8"),
    "document_name": path.name,
}

print("Sending analysis request to the agent service...")
response = requests.post(f"{BASE_URL}/analyze", json=payload, timeout=300)

if response.status_code not in {200, 202}:
    print(f"❌ Error! Status Code: {response.status_code}")
    print("Response Content (The real error):")
    print(response.text)
    raise SystemExit(1)

result = response.json()
analysis_id = result["analysis_id"]
print(f"Accepted analysis request with id {analysis_id}.")
print(f"Initial status: {result.get('status')}")

for attempt in range(1, 31):
    status_response = requests.get(f"{BASE_URL}/analyses/{analysis_id}/status", timeout=60)
    status_payload = status_response.json()
    print(f"Status check {attempt}: {status_payload.get('status')}")

    if status_payload.get("status") == "COMPLETED":
        result_response = requests.get(f"{BASE_URL}/analyses/{analysis_id}", timeout=60)
        print("Success!")
        print(result_response.json())
        break

    if status_payload.get("status") == "FAILED":
        print("❌ Analysis failed.")
        if status_payload.get("error_message"):
            print(status_payload["error_message"])
        raise SystemExit(1)

    time.sleep(5)
else:
    print("❌ Analysis did not finish in time.")
    raise SystemExit(1)