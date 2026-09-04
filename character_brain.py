from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional

from character_context import (
    build_character_context,
    render_character_context,
)
from character_profiles import get_character_profile
from horde import generate as horde_generate


# ============================================================
# CHARACTER BRAIN
#
# This layer is intentionally thin.
#
# It does NOT:
#   - decide objective truth
#   - decide what the character perceived
#   - resolve whether an attempted action succeeds
#   - mutate world state
#   - write another person's mind
#
# It DOES:
#   - receive one character's filtered context
#   - let that character model think/respond
#   - return the character's own speech, private thought, and
#     intended action for later Director/Engine handling
#
# Flow:
#
#   Director/perception
#       -> Character Context
#       -> Character Brain
#       -> proposed character response
#       -> Director / action interpretation
#       -> Engine resolution
# ============================================================


DEFAULT_MAX_LENGTH = 420
DEFAULT_TEMPERATURE = 0.8

BRAIN_OUTPUT_INSTRUCTION = """
OUTPUT FORMAT

Return exactly one JSON object with these keys:

{
  "speech": null,
  "thought": null,
  "action": null
}

Rules:
- speech: only words this character chooses to say aloud.
- thought: only this character's private thought/feeling/interpretation.
- action: only what this character intends or attempts to do.
- Use null when a field does not apply.
- Never state that an attempted action succeeded unless the supplied context
  already establishes that result.
- Never decide another person's thoughts, feelings, beliefs, consent,
  intentions, dialogue, or voluntary actions.
- Do not add narration outside the JSON object.
""".strip()


@dataclass(frozen=True)
class CharacterBrainResponse:
    character_id: int
    model: str
    speech: Optional[str]
    thought: Optional[str]
    action: Optional[str]
    raw_text: str

    @property
    def has_public_output(self):
        return bool(self.speech or self.action)

    @property
    def has_any_output(self):
        return bool(
            self.speech
            or self.thought
            or self.action
        )


def _clean_optional_text(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def _model_candidates(runtime):
    preferred = _clean_optional_text(
        runtime.get("preferred_model")
    )

    fallback_raw = _clean_optional_text(
        runtime.get("fallback_models")
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
            "This character has no preferred_model or fallback model configured."
        )

    return candidates


def build_character_brain_prompt(
    rendered_context,
    profile_text=None,
):
    parts = []

    if profile_text:
        parts.extend([
            "AUTHORED CHARACTER PROFILE",
            str(profile_text).strip(),
            "",
            (
                "The authored profile defines this character's enduring identity, "
                "values, behavioural tendencies, voice, and starting relationships. "
                "Apply it through the character's own knowledge and current filtered "
                "context. It does not override Engine truth, grant hidden knowledge, "
                "decide outcomes, or control another person's internal state."
            ),
            "",
        ])

    parts.append(rendered_context.rstrip())
    parts.append("")
    parts.append(BRAIN_OUTPUT_INSTRUCTION)

    return "\n".join(parts)


def _extract_json_object(raw_text):
    """
    Horde models may occasionally wrap otherwise-valid JSON in prose or a
    Markdown code fence. Accept the first complete JSON object, but reject
    output that cannot be interpreted as one object.
    """
    text = str(raw_text or "").strip()

    if not text:
        raise ValueError(
            "Character brain returned empty output."
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

        if (
            start == -1
            or end == -1
            or end <= start
        ):
            raise ValueError(
                "Character brain did not return a JSON object."
            )

        candidate = text[start:end + 1]

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Character brain returned malformed JSON."
            ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "Character brain output must be one JSON object."
        )

    return data


def parse_character_brain_output(
    character_id,
    model,
    raw_text,
):
    data = _extract_json_object(raw_text)

    allowed = {
        "speech",
        "thought",
        "action",
    }

    unexpected = set(data) - allowed

    if unexpected:
        raise ValueError(
            "Character brain returned unsupported fields: "
            + ", ".join(sorted(unexpected))
        )

    return CharacterBrainResponse(
        character_id=int(character_id),
        model=str(model),
        speech=_clean_optional_text(
            data.get("speech")
        ),
        thought=_clean_optional_text(
            data.get("thought")
        ),
        action=_clean_optional_text(
            data.get("action")
        ),
        raw_text=str(raw_text),
    )


def run_character_brain(
    character_id,
    perception,
    *,
    query=None,
    memory_limit=6,
    knowledge_limit=8,
    generator: Callable = horde_generate,
    max_length=DEFAULT_MAX_LENGTH,
    temperature=DEFAULT_TEMPERATURE,
):
    """
    Ask one character brain for its own response.

    `perception` must already be filtered for this character.

    Returns CharacterBrainResponse only. This function deliberately performs
    no world mutation and does not send speech to Discord. The caller/Director
    decides what to do with the proposed speech/action next.
    """
    context = build_character_context(
        character_id,
        perception,
        query=query,
        memory_limit=memory_limit,
        knowledge_limit=knowledge_limit,
    )

    runtime = context["runtime"]

    if not runtime["may_invoke_ai_brain"]:
        raise RuntimeError(
            "This character is not currently eligible for AI brain invocation."
        )

    rendered_context = render_character_context(
        context
    )

    rich_profile = get_character_profile(
        character_id
    )

    prompt = build_character_brain_prompt(
        rendered_context,
        profile_text=(
            None
            if rich_profile is None
            else rich_profile.profile_text
        ),
    )

    errors = []

    for model in _model_candidates(runtime):
        try:
            raw_text = generator(
                prompt=prompt,
                model=model,
                max_length=max_length,
                temperature=temperature,
                stop_sequences=[],
            )

            return parse_character_brain_output(
                character_id,
                model,
                raw_text,
            )

        except Exception as exc:
            errors.append(
                f"{model}: {type(exc).__name__}: {exc}"
            )

    raise RuntimeError(
        "All configured character brain models failed. "
        + " | ".join(errors)
    )
