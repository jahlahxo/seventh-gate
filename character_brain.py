from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional

from campaign import get_campaign_setting
from character_context import (
    build_character_context,
    render_character_context,
)
from character_profiles import get_character_profile
from horde import (
    generate as horde_generate,
    get_ranked_text_model_names,
)


DEFAULT_MAX_LENGTH = 420
DEFAULT_TEMPERATURE = 0.8
DEFAULT_CHARACTER_MODEL_SETTING = "default_character_model"

CHARACTER_WORLD_CONSISTENCY_INSTRUCTION = """
TIME / CULTURAL CONSISTENCY

Stay inside this character's established era, culture, education, experience
and personal knowledge.

Another person's modernity, foreignness, confidence, unfamiliar vocabulary,
strange object, unexplained claim or different social assumptions do NOT grant
this character knowledge they do not have.

If something is unfamiliar, interpret it through this character's existing
worldview and available evidence. Whether the character is curious, amused,
suspicious, dismissive, frightened, welcoming, hostile, fascinated, or
indifferent is a character decision shaped by their own personality and
circumstances.

Do not modernize this character's values, vocabulary, etiquette or assumptions
merely to make a human player comfortable or understood.

Do not become a historical tour guide. Explain ordinary customs only when this
character would naturally have a reason to explain them.

Period social expectations can matter: relative standing, household role, age,
marital status and gendered custom may shape what this character considers
ordinary, rude, bold, intimate, respectable or strange. But do not invent a
social rule that is absent from the character's profile, knowledge or filtered
context, and never let a convention override this character's individuality.
""".strip()

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


def _character_model_candidates(runtime):
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

    return candidates


def _configured_model_candidates(
    runtime,
    *,
    global_preferred_model=None,
):
    """
    Normal case: all characters inherit the global preferred model.

    Optional exception: a character-specific preferred/fallback chain is tried
    first, then the global preferred model.
    """
    candidates = _character_model_candidates(runtime)

    global_preferred = _clean_optional_text(
        global_preferred_model
    )

    if (
        global_preferred
        and global_preferred not in candidates
    ):
        candidates.append(global_preferred)

    return candidates


def _model_candidates(
    runtime,
    *,
    global_preferred_model=None,
    live_models=None,
):
    configured = _configured_model_candidates(
        runtime,
        global_preferred_model=global_preferred_model,
    )

    if live_models is None:
        candidates = configured
    else:
        live = []

        for model in live_models:
            model = _clean_optional_text(model)

            if model and model not in live:
                live.append(model)

        active = set(live)

        candidates = [
            model
            for model in configured
            if model in active
        ]

        for model in live:
            if model not in candidates:
                candidates.append(model)

    if not candidates:
        if live_models is not None:
            raise RuntimeError(
                "No active Horde text models are currently available."
            )

        raise RuntimeError(
            "No character override or global preferred model is configured, "
            "and automatic Horde model discovery is unavailable."
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
    parts.append(
        CHARACTER_WORLD_CONSISTENCY_INSTRUCTION
    )
    parts.append("")
    parts.append(BRAIN_OUTPUT_INSTRUCTION)

    return "\n".join(parts)


def _extract_json_object(raw_text):
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


def _read_global_preferred_model():
    return get_campaign_setting(
        DEFAULT_CHARACTER_MODEL_SETTING
    )


def run_character_brain(
    character_id,
    perception,
    *,
    query=None,
    memory_limit=6,
    knowledge_limit=8,
    generator: Callable = horde_generate,
    model_provider: Optional[Callable] = None,
    default_model_provider: Optional[Callable] = None,
    max_length=DEFAULT_MAX_LENGTH,
    temperature=DEFAULT_TEMPERATURE,
):
    """
    Ask one character brain for its own response.

    Production model policy:
    - characters normally inherit one global preferred model;
    - an individual character may optionally override that model;
    - active Horde models are discovered automatically;
    - if an explicit preference is missing or fails, live models are tried in
      current SillyTavern-style ranking order.

    Custom generators used by tests/tools do not trigger live database/model
    discovery unless providers are explicitly supplied.
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

    rendered_context = render_character_context(context)

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

    effective_model_provider = model_provider
    effective_default_provider = default_model_provider

    if generator is horde_generate:
        if effective_model_provider is None:
            effective_model_provider = (
                get_ranked_text_model_names
            )

        if effective_default_provider is None:
            effective_default_provider = (
                _read_global_preferred_model
            )

    discovery_error = None
    default_error = None
    live_models = None
    global_preferred_model = None

    if effective_default_provider is not None:
        try:
            global_preferred_model = (
                effective_default_provider()
            )
        except Exception as exc:
            default_error = (
                f"{type(exc).__name__}: {exc}"
            )

    if effective_model_provider is not None:
        try:
            live_models = list(
                effective_model_provider()
            )
        except Exception as exc:
            discovery_error = (
                f"{type(exc).__name__}: {exc}"
            )

    try:
        candidates = _model_candidates(
            runtime,
            global_preferred_model=global_preferred_model,
            live_models=live_models,
        )
    except RuntimeError as exc:
        details = []

        if default_error:
            details.append(
                "global model lookup failed: "
                + default_error
            )

        if discovery_error:
            details.append(
                "Horde model discovery failed: "
                + discovery_error
            )

        if details:
            raise RuntimeError(
                f"{exc} "
                + " | ".join(details)
            ) from exc

        raise

    errors = []

    for model in candidates:
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

    if default_error:
        errors.append(
            "Global model lookup: "
            + default_error
        )

    if discovery_error:
        errors.append(
            "Horde model discovery: "
            + discovery_error
        )

    raise RuntimeError(
        "All available character brain models failed. "
        + " | ".join(errors)
    )
