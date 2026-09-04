import os
import time
import requests

from dotenv import load_dotenv

load_dotenv()

HORDE_API_KEY = os.getenv("HORDE_API_KEY")

HORDE_HEADERS = {
    "apikey": HORDE_API_KEY,
    "Client-Agent": "SeventhGateRP:1.0",
    "Content-Type": "application/json",
}

GENERATE_URL = "https://aihorde.net/api/v2/generate/text/async"
STATUS_URL = "https://aihorde.net/api/v2/generate/text/status"


def generate(
    prompt,
    model,
    max_length=300,
    temperature=0.8,
    stop_sequences=None,
):
    if not HORDE_API_KEY:
        raise RuntimeError("HORDE_API_KEY is missing from .env")

    if stop_sequences is None:
        stop_sequences = []

    payload = {
        "prompt": prompt,
        "models": [model],
        "params": {
            "max_length": max_length,
            "temperature": temperature,
            "stop_sequence": stop_sequences,
        },
        "trusted_workers": False,
        "slow_workers": True,
    }

    response = requests.post(
        GENERATE_URL,
        headers=HORDE_HEADERS,
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    if "id" not in data:
        raise RuntimeError(
            f"Horde did not return a generation ID: {data}"
        )

    request_id = data["id"]

    while True:
        response = requests.get(
            f"{STATUS_URL}/{request_id}",
            headers=HORDE_HEADERS,
            timeout=30,
        )

        response.raise_for_status()
        data = response.json()

        if data.get("faulted"):
            raise RuntimeError(
                f"Horde generation faulted: {data}"
            )

        if data.get("done"):
            generations = data.get("generations", [])

            if not generations:
                raise RuntimeError(
                    "Horde finished but returned no generation."
                )

            text = generations[0].get("text", "").strip()

            if not text:
                raise RuntimeError(
                    "Horde returned an empty generation."
                )

            return text

        time.sleep(2)