import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("HORDE_API_KEY")

MODEL = "aphrodite/TheDrummer/Skyfall-31B-v4.2"

headers = {
    "apikey": API_KEY,
    "Client-Agent": "SeventhGateRP:0.1",
    "Content-Type": "application/json"
}

payload = {
    "prompt": (
        "You are a test character in a roleplaying system. "
        "Say one short sentence proving you can respond."
    ),
    "models": [MODEL],
    "params": {
        "max_length": 80,
        "temperature": 0.8
    },
    "trusted_workers": False,
    "slow_workers": True
}

print(f"Sending request to:\n{MODEL}\n")

response = requests.post(
    "https://aihorde.net/api/v2/generate/text/async",
    headers=headers,
    json=payload,
    timeout=30
)

response.raise_for_status()
request_id = response.json()["id"]

print(f"Request accepted: {request_id}")
print("Waiting for generation...")

while True:
    check = requests.get(
        f"https://aihorde.net/api/v2/generate/text/status/{request_id}",
        headers=headers,
        timeout=30
    )

    check.raise_for_status()
    data = check.json()

    if data.get("done"):
        generations = data.get("generations", [])

        if generations:
            print("\n--- RESPONSE ---")
            print(generations[0]["text"])
            print("----------------")
        else:
            print("\nGeneration finished, but no text was returned.")

        break

    print(".", end="", flush=True)
    time.sleep(2)