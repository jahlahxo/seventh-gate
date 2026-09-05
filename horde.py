from __future__ import annotations

import os
import time

import requests
from dotenv import load_dotenv


load_dotenv()

HORDE_API_KEY = os.getenv("HORDE_API_KEY")

CLIENT_AGENT = "SeventhGateRP:1.0"

HORDE_HEADERS = {
    "apikey": HORDE_API_KEY,
    "Client-Agent": CLIENT_AGENT,
    "Content-Type": "application/json",
}

PUBLIC_HORDE_HEADERS = {
    "Client-Agent": CLIENT_AGENT,
}

GENERATE_URL = "https://aihorde.net/api/v2/generate/text/async"
STATUS_URL = "https://aihorde.net/api/v2/generate/text/status"
MODELS_URL = "https://aihorde.net/api/v2/status/models"
TEXT_MODEL_METADATA_URL = (
    "https://raw.githubusercontent.com/"
    "db0/AI-Horde-text-model-reference/main/db.json"
)

MODEL_CACHE_SECONDS = 60.0

_model_cache = None
_model_cache_time = 0.0


def clear_text_model_cache():
    global _model_cache
    global _model_cache_time

    _model_cache = None
    _model_cache_time = 0.0


def _safe_performance(model):
    try:
        return float(
            model.get("performance", 0)
            or 0
        )
    except (TypeError, ValueError):
        return 0.0


def _is_popular(model):
    tags = model.get("tags") or []
    return "popular" in tags


def _merge_model_metadata(active_models, metadata):
    merged = []

    for active_model in active_models:
        model = dict(active_model)
        name = str(model.get("name") or "").strip()

        metadata_model = (
            metadata.get(name)
            if isinstance(metadata, dict)
            else None
        )

        if isinstance(metadata_model, dict):
            model.update(metadata_model)
            model["is_whitelisted"] = True
        else:
            model["is_whitelisted"] = False

        if name:
            model["name"] = name

        merged.append(model)

    return merged


def _rank_models(models):
    """
    Match SillyTavern's current Horde model dropdown ordering:

    1. whitelisted models first
    2. models tagged "popular" next
    3. higher live performance next

    Python's sort is stable, so ties preserve Horde's original order.
    """
    return sorted(
        models,
        key=lambda model: (
            not bool(model.get("is_whitelisted")),
            not _is_popular(model),
            -_safe_performance(model),
        ),
    )


def get_ranked_text_models(*, force=False, timeout=15):
    """
    Return currently active Horde text models in SillyTavern-style order.

    The active model list is authoritative. Metadata is advisory and is used
    only for whitelisted/popular ranking. If metadata cannot be fetched, live
    models are still returned and ranked by performance.

    Results are cached briefly so normal character turns do not hit Horde and
    the metadata repository on every message.
    """
    global _model_cache
    global _model_cache_time

    now = time.monotonic()

    if (
        not force
        and _model_cache is not None
        and now - _model_cache_time < MODEL_CACHE_SECONDS
    ):
        return [dict(model) for model in _model_cache]

    response = requests.get(
        MODELS_URL,
        headers=PUBLIC_HORDE_HEADERS,
        params={"type": "text"},
        timeout=timeout,
    )
    response.raise_for_status()

    active_models = response.json()

    if not isinstance(active_models, list):
        raise RuntimeError(
            "Horde model status endpoint did not return a list."
        )

    active_models = [
        dict(model)
        for model in active_models
        if (
            isinstance(model, dict)
            and str(model.get("name") or "").strip()
        )
    ]

    metadata = {}

    try:
        metadata_response = requests.get(
            TEXT_MODEL_METADATA_URL,
            headers=PUBLIC_HORDE_HEADERS,
            timeout=timeout,
        )
        metadata_response.raise_for_status()
        metadata_data = metadata_response.json()

        if isinstance(metadata_data, dict):
            metadata = metadata_data
    except (requests.RequestException, ValueError):
        metadata = {}

    ranked = _rank_models(
        _merge_model_metadata(
            active_models,
            metadata,
        )
    )

    _model_cache = [dict(model) for model in ranked]
    _model_cache_time = now

    return [dict(model) for model in ranked]


def get_ranked_text_model_names(*, force=False, timeout=15):
    return [
        str(model["name"])
        for model in get_ranked_text_models(
            force=force,
            timeout=timeout,
        )
    ]


def generate(
    prompt,
    model,
    max_length=300,
    temperature=0.8,
    stop_sequences=None,
):
    if not HORDE_API_KEY:
        raise RuntimeError(
            "HORDE_API_KEY is missing from .env"
        )

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
