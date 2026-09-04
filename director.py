from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from campaign import get_campaign_setting
from development import get_director_perception_constraints
from horde import generate as horde_generate


DEFAULT_MAX_LENGTH = 520
DEFAULT_TEMPERATURE = 0.65

ALLOWED_PERCEPTION_KEYS = {
    "current",
    "environment",
    "people",
    "objects",
    "recent",
    "private",
}

DIRECTOR_OUTPUT_INSTRUCTION = """
OUTPUT FORMAT

Return exactly one JSON object with these keys:

{
  "current": null,
  "environment": null,
  "people": [],
  "objects": [],
  "recent": [],
  "private": []
}

Rules:
- Reveal only information supported by the supplied OBJECTIVE SCENE PACKET.
- Do not invent hidden facts, motives, thoughts, feelings, intentions,
  relationships, outcomes, or off-screen events.
- `current` is the immediate thing this character perceives happening now.
- `environment` is perceivable scene/weather/sound/smell/lighting/etc.
- `people` contains only people this character can presently perceive, using
  observable details only.
- `objects` contains only objects/details this character can presently perceive.
- `recent` contains only recent things this character plausibly perceived.
- `private` contains only private bodily/sensory notices addressed to THIS
  character, never a hidden diagnosis or engine-only conclusion.
- Preserve uncertainty. If the scene packet does not support a detail, omit it.
- Do not add narration outside the JSON object.
""".strip()


@dataclass(frozen=True)
class DirectorPerceptionResult:
    character_id: int
    model: str
    perception: dict
    raw_text: str


def _clean_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _model_candidates():
    preferred = _clean_text(
        get_campaign_setting("director_model")
    )
    fallback_raw = _clean_text(
        get_campaign_setting("director_fallback_models")
    )

    candidates = []

    if preferred:
        candidates.append(preferred)

    if fallback_raw:
        for model in fallback_raw.split(","):
            model = model.strip()
            if model and model not in candidates:
                candidates.append(model)

    if not candidates:
        raise RuntimeError(
            "No Director model is configured. "
            "Set campaign setting 'director_model'."
        )

    return candidates


def _normalize_objective_scene(objective_scene):
    if not isinstance(objective_scene, dict):
        raise TypeError(
            "objective_scene must be a dict."
        )
    return objective_scene


def build_director_prompt(
    character_id,
    objective_scene,
):
    objective_scene = _normalize_objective_scene(
        objective_scene
    )

    constraints = get_director_perception_constraints(
        character_id
    )

    developmental = (
        "No specific developmental perception constraint is established."
        if constraints is None
        else constraints["directive"]
    )

    scene_json = json.dumps(
        objective_scene,
        ensure_ascii=False,
        indent=2,
        default=str,
    )

    return (
        "DIRECTOR / PERCEPTION TASK\n\n"
        "You are the Director. The Engine has already determined what is true.\n"
        "Your job here is ONLY to decide how much of the supplied scene truth "
        "this specific character can actually perceive and how it appears to "
        "them.\n\n"
        "Do not decide the character's thoughts, feelings, morality, dialogue, "
        "intentions, or actions.\n"
        "Do not convert hidden engine truth into character knowledge.\n\n"
        "DEVELOPMENTAL / INTERPRETIVE CONSTRAINT\n"
        f"{developmental}\n\n"
        "OBJECTIVE SCENE PACKET\n"
        f"{scene_json}\n\n"
        f"{DIRECTOR_OUTPUT_INSTRUCTION}"
    )


def _extract_json_object(raw_text):
    text = str(raw_text or "").strip()

    if not text:
        raise ValueError(
            "Director returned empty output."
        )

    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(
                "Director did not return a JSON object."
            )
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Director returned malformed JSON."
            ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "Director output must be one JSON object."
        )

    return data


def _clean_list(value, field_name):
    if value is None:
        return []

    if not isinstance(value, list):
        raise ValueError(
            f"Director field '{field_name}' must be a list."
        )

    return value


def parse_director_perception(
    character_id,
    model,
    raw_text,
):
    data = _extract_json_object(raw_text)

    unexpected = set(data) - ALLOWED_PERCEPTION_KEYS

    if unexpected:
        raise ValueError(
            "Director returned unsupported fields: "
            + ", ".join(sorted(unexpected))
        )

    perception = {
        "current": _clean_text(data.get("current")),
        "environment": _clean_text(data.get("environment")),
        "people": _clean_list(data.get("people"), "people"),
        "objects": _clean_list(data.get("objects"), "objects"),
        "recent": _clean_list(data.get("recent"), "recent"),
        "private": _clean_list(data.get("private"), "private"),
    }

    return DirectorPerceptionResult(
        character_id=int(character_id),
        model=str(model),
        perception=perception,
        raw_text=str(raw_text),
    )


def run_director_perception(
    character_id,
    objective_scene,
    *,
    generator: Callable = horde_generate,
    max_length=DEFAULT_MAX_LENGTH,
    temperature=DEFAULT_TEMPERATURE,
):
    prompt = build_director_prompt(
        character_id,
        objective_scene,
    )

    errors = []

    for model in _model_candidates():
        try:
            raw_text = generator(
                prompt=prompt,
                model=model,
                max_length=max_length,
                temperature=temperature,
                stop_sequences=[],
            )

            return parse_director_perception(
                character_id,
                model,
                raw_text,
            )

        except Exception as exc:
            errors.append(
                f"{model}: {type(exc).__name__}: {exc}"
            )

    raise RuntimeError(
        "All configured Director models failed. "
        + " | ".join(errors)
    )
