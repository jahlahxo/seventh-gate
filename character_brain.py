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
from rp_text import (
    parse_story_post,
    strip_outer_italics,
)
from scene_memory import (
    render_scene_continuity,
)


DEFAULT_MAX_LENGTH = 420
DEFAULT_TEMPERATURE = 0.8
DEFAULT_CHARACTER_MODEL_SETTING = (
    "default_character_model"
)


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


CHARACTER_RP_STYLE_INSTRUCTION = """
DISCORD STORY-RP STYLE

Write the human-facing turn like compact collaborative fiction.

- `public` is natural story prose. Actions/narration are ordinary text and
  spoken words appear naturally inside quotation marks.
- Action and dialogue may freely share the same sentence or line. Do NOT split
  the response into mechanical "speech lines" and "action lines".
- Usually use 1-3 short Discord lines. Four is a normal upper bound, but an
  occasional slightly longer turn is allowed when the moment genuinely needs
  it. Never produce an exposition paragraph merely to fill space.
- Reveal atmosphere, history, customs, relationships and status through what
  the character notices, does and naturally says. Do not recap the room or
  explain the setting to the player.
- You are not required to answer every perceived message. Silence, watching,
  continuing another activity, or doing nothing can be the most natural turn.
- Do not automatically greet, introduce yourself to, or acknowledge every new
  arrival.
- You may initiate conversation, movement, conflict, humour, work, plans,
  departures, approaches and other behaviour when your own motives make that
  natural. Do not exist only to react to the human player.
- Do not overperform signature traits. Avoid repeating the same phrase,
  mannerism, joke, pet name, gesture or reaction merely to prove personality.
  Recent perceived history includes your own prior public behaviour; vary it
  naturally.
""".strip()


BRAIN_OUTPUT_INSTRUCTION = """
OUTPUT FORMAT

Return exactly one JSON object with these keys:

{
  "public": null,
  "thought": null,
  "action": null,
  "open_threads": [],
  "resolve_thread_ids": []
}

Rules:
- public: only compact story prose humans should read in Discord. It may
  naturally mix observable action/narration and quoted speech.
- thought: only this character's private thought, feeling or interpretation.
  Do NOT add Markdown asterisks; Seventh Gate renders it in italics later.
- action: a plain, precise description of any externally meaningful physical
  action this character intends or attempts. This is engine metadata and is
  NOT posted separately to Discord.
- If an attempted action is externally observable, `public` should describe
  the attempt naturally without claiming an unresolved result.
- open_threads: short pieces of concrete unfinished business THIS character
  should continue carrying: an unanswered question, promise, plan, task,
  unresolved conflict, or intention. Do not create a thread for every topic.
- resolve_thread_ids: IDs from supplied unresolved-business context that this
  turn genuinely resolves.
- Use null/empty lists when fields do not apply.
- Never state that an attempted action succeeded unless supplied context
  already establishes that result.
- Never decide another person's thoughts, feelings, beliefs, consent,
  intentions, dialogue, or voluntary actions.
- Private thought must never be copied into `public`.
- Do not add narration outside the JSON object.

Compatibility note for old test/import material only: the legacy
{"speech": null, "thought": null, "action": null} shape may be accepted on
input, but you must return the new `public` shape above.
""".strip()


@dataclass(
    frozen=True,
    init=False,
)
class CharacterBrainResponse:
    character_id: int
    model: str
    public: Optional[str]
    thought: Optional[str]
    action: Optional[str]
    raw_text: str
    open_threads: tuple[str, ...]
    resolve_thread_ids: tuple[int, ...]

    def __init__(
        self,
        character_id,
        model,
        public=None,
        thought=None,
        action=None,
        raw_text="",
        open_threads=(),
        resolve_thread_ids=(),
        speech=None,
    ):
        if public is None:
            public = speech
        elif (
            speech is not None
            and str(
                speech
            ).strip()
            != str(
                public
            ).strip()
        ):
            raise ValueError(
                "public and legacy speech values disagree."
            )

        object.__setattr__(
            self,
            "character_id",
            int(
                character_id
            ),
        )
        object.__setattr__(
            self,
            "model",
            str(
                model
            ),
        )
        object.__setattr__(
            self,
            "public",
            _clean_optional_text(
                public
            ),
        )
        object.__setattr__(
            self,
            "thought",
            _clean_optional_text(
                thought
            ),
        )
        object.__setattr__(
            self,
            "action",
            _clean_optional_text(
                action
            ),
        )
        object.__setattr__(
            self,
            "raw_text",
            str(
                raw_text
            ),
        )
        object.__setattr__(
            self,
            "open_threads",
            tuple(
                open_threads
                or ()
            ),
        )
        object.__setattr__(
            self,
            "resolve_thread_ids",
            tuple(
                int(
                    value
                )
                for value
                in (
                    resolve_thread_ids
                    or ()
                )
            ),
        )

    @property
    def speech(self):
        """
        Backward-compatible alias. New code should use `.public`.
        """
        return self.public

    @property
    def has_public_output(self):
        return bool(
            self.public
        )

    @property
    def has_any_output(self):
        return bool(
            self.public
            or self.thought
            or self.action
            or self.open_threads
            or self.resolve_thread_ids
        )


def _clean_optional_text(
    value,
):
    if value is None:
        return None

    value = str(
        value
    ).strip()

    return (
        value
        or None
    )


def _clean_string_list(
    value,
    field_name,
):
    if value is None:
        return ()

    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            f"Character brain field '{field_name}' must be a list."
        )

    result = []

    for item in value:
        item = (
            _clean_optional_text(
                item
            )
        )

        if item:
            result.append(
                item
            )

    return tuple(
        result
    )


def _clean_int_list(
    value,
    field_name,
):
    if value is None:
        return ()

    if not isinstance(
        value,
        list,
    ):
        raise ValueError(
            f"Character brain field '{field_name}' must be a list."
        )

    result = []

    for item in value:
        try:
            item = int(
                item
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                f"Character brain field '{field_name}' must contain integers."
            ) from exc

        if item not in result:
            result.append(
                item
            )

    return tuple(
        result
    )


def _character_model_candidates(
    runtime,
):
    preferred = _clean_optional_text(
        runtime.get(
            "preferred_model"
        )
    )

    fallback_raw = _clean_optional_text(
        runtime.get(
            "fallback_models"
        )
    )

    candidates = []

    if preferred:
        candidates.append(
            preferred
        )

    if fallback_raw:
        for model in fallback_raw.split(
            ","
        ):
            model = (
                model.strip()
            )

            if (
                model
                and model
                not in candidates
            ):
                candidates.append(
                    model
                )

    return candidates


def _configured_model_candidates(
    runtime,
    *,
    global_preferred_model=None,
):
    candidates = (
        _character_model_candidates(
            runtime
        )
    )

    global_preferred = (
        _clean_optional_text(
            global_preferred_model
        )
    )

    if (
        global_preferred
        and global_preferred
        not in candidates
    ):
        candidates.append(
            global_preferred
        )

    return candidates


def _model_candidates(
    runtime,
    *,
    global_preferred_model=None,
    live_models=None,
):
    configured = (
        _configured_model_candidates(
            runtime,
            global_preferred_model=
                global_preferred_model,
        )
    )

    if live_models is None:
        candidates = (
            configured
        )
    else:
        live = []

        for model in live_models:
            model = (
                _clean_optional_text(
                    model
                )
            )

            if (
                model
                and model
                not in live
            ):
                live.append(
                    model
                )

        active = set(
            live
        )

        candidates = [
            model
            for model
            in configured
            if model in active
        ]

        for model in live:
            if model not in candidates:
                candidates.append(
                    model
                )

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
            str(
                profile_text
            ).strip(),
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

    parts.append(
        rendered_context.rstrip()
    )
    parts.append("")
    parts.append(
        CHARACTER_WORLD_CONSISTENCY_INSTRUCTION
    )
    parts.append("")
    parts.append(
        CHARACTER_RP_STYLE_INSTRUCTION
    )
    parts.append("")
    parts.append(
        BRAIN_OUTPUT_INSTRUCTION
    )

    return "\n".join(
        parts
    )


def _extract_json_object(
    raw_text,
):
    text = str(
        raw_text
        or ""
    ).strip()

    if not text:
        raise ValueError(
            "Character brain returned empty output."
        )

    if text.startswith(
        "```"
    ):
        lines = (
            text.splitlines()
        )

        if lines:
            lines = lines[
                1:
            ]

        if (
            lines
            and lines[-1].strip()
            == "```"
        ):
            lines = lines[
                :-1
            ]

        text = "\n".join(
            lines
        ).strip()

    try:
        data = json.loads(
            text
        )
    except json.JSONDecodeError:
        start = text.find(
            "{"
        )
        end = text.rfind(
            "}"
        )

        if (
            start == -1
            or end == -1
            or end <= start
        ):
            raise ValueError(
                "Character brain did not return a JSON object."
            )

        candidate = text[
            start:
            end + 1
        ]

        try:
            data = json.loads(
                candidate
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Character brain returned malformed JSON."
            ) from exc

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Character brain output must be one JSON object."
        )

    return data


def parse_character_brain_output(
    character_id,
    model,
    raw_text,
):
    data = _extract_json_object(
        raw_text
    )

    allowed = {
        "public",
        "speech",
        "thought",
        "action",
        "open_threads",
        "resolve_thread_ids",
    }

    unexpected = (
        set(
            data
        )
        - allowed
    )

    if unexpected:
        raise ValueError(
            "Character brain returned unsupported fields: "
            + ", ".join(
                sorted(
                    unexpected
                )
            )
        )

    public_value = (
        data.get(
            "public"
        )
    )
    legacy_speech = (
        data.get(
            "speech"
        )
    )

    if (
        public_value is not None
        and legacy_speech
        is not None
        and str(
            public_value
        ).strip()
        != str(
            legacy_speech
        ).strip()
    ):
        raise ValueError(
            "Character brain returned conflicting public/speech fields."
        )

    if public_value is None:
        public_value = (
            legacy_speech
        )

    parsed_public = (
        parse_story_post(
            public_value
        )
    )

    explicit_thought = (
        strip_outer_italics(
            data.get(
                "thought"
            )
        )
    )

    thoughts = []

    if explicit_thought:
        thoughts.append(
            explicit_thought
        )

    thoughts.extend(
        parsed_public.thoughts
    )

    thought = (
        "\n".join(
            thoughts
        )
        if thoughts
        else None
    )

    return CharacterBrainResponse(
        character_id=
            int(
                character_id
            ),
        model=
            str(
                model
            ),
        public=
            parsed_public.public_text,
        thought=
            thought,
        action=
            _clean_optional_text(
                data.get(
                    "action"
                )
            ),
        raw_text=
            str(
                raw_text
            ),
        open_threads=
            _clean_string_list(
                data.get(
                    "open_threads",
                    [],
                ),
                "open_threads",
            ),
        resolve_thread_ids=
            _clean_int_list(
                data.get(
                    "resolve_thread_ids",
                    [],
                ),
                "resolve_thread_ids",
            ),
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
    generator: Callable =
        horde_generate,
    model_provider:
        Optional[Callable] = None,
    default_model_provider:
        Optional[Callable] = None,
    continuity_provider:
        Optional[Callable] = None,
    max_length=DEFAULT_MAX_LENGTH,
    temperature=DEFAULT_TEMPERATURE,
):
    context = build_character_context(
        character_id,
        perception,
        query=query,
        memory_limit=
            memory_limit,
        knowledge_limit=
            knowledge_limit,
    )

    runtime = context[
        "runtime"
    ]

    if not runtime[
        "may_invoke_ai_brain"
    ]:
        raise RuntimeError(
            "This character is not currently eligible for AI brain invocation."
        )

    rendered_context = (
        render_character_context(
            context
        )
    )

    effective_continuity_provider = (
        continuity_provider
    )

    # Existing tests/tools commonly supply a custom generator without a real
    # production DB. Production Horde turns automatically receive continuity.
    if (
        effective_continuity_provider
        is None
        and generator
        is horde_generate
    ):
        effective_continuity_provider = (
            render_scene_continuity
        )

    if (
        effective_continuity_provider
        is not None
    ):
        continuity_text = (
            effective_continuity_provider(
                character_id
            )
        )

        if continuity_text:
            rendered_context = (
                rendered_context.rstrip()
                + "\n\n"
                + str(
                    continuity_text
                ).strip()
            )

    rich_profile = (
        get_character_profile(
            character_id
        )
    )

    prompt = build_character_brain_prompt(
        rendered_context,
        profile_text=(
            None
            if rich_profile
            is None
            else rich_profile.profile_text
        ),
    )

    effective_model_provider = (
        model_provider
    )
    effective_default_provider = (
        default_model_provider
    )

    if generator is horde_generate:
        if (
            effective_model_provider
            is None
        ):
            effective_model_provider = (
                get_ranked_text_model_names
            )

        if (
            effective_default_provider
            is None
        ):
            effective_default_provider = (
                _read_global_preferred_model
            )

    discovery_error = None
    default_error = None
    live_models = None
    global_preferred_model = None

    if (
        effective_default_provider
        is not None
    ):
        try:
            global_preferred_model = (
                effective_default_provider()
            )
        except Exception as exc:
            default_error = (
                f"{type(exc).__name__}: {exc}"
            )

    if (
        effective_model_provider
        is not None
    ):
        try:
            live_models = list(
                effective_model_provider()
            )
        except Exception as exc:
            discovery_error = (
                f"{type(exc).__name__}: {exc}"
            )

    try:
        candidates = (
            _model_candidates(
                runtime,
                global_preferred_model=
                    global_preferred_model,
                live_models=
                    live_models,
            )
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
                + " | ".join(
                    details
                )
            ) from exc

        raise

    errors = []

    for model in candidates:
        try:
            raw_text = generator(
                prompt=prompt,
                model=model,
                max_length=
                    max_length,
                temperature=
                    temperature,
                stop_sequences=[],
            )

            return (
                parse_character_brain_output(
                    character_id,
                    model,
                    raw_text,
                )
            )

        except Exception as exc:
            errors.append(
                f"{model}: "
                f"{type(exc).__name__}: "
                f"{exc}"
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
        + " | ".join(
            errors
        )
    )
