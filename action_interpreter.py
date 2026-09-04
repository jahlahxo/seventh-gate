from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from actions import (
    ActionIntent,
    ActionType,
    EntityRef,
    make_action,
    make_entity,
)
from campaign import get_campaign_setting
from horde import generate as horde_generate


# ============================================================
# ACTION INTERPRETATION BRIDGE
#
# Converts one character's natural-language intended action into
# the structured ActionIntent already understood by resolver.py.
#
# SECURITY / KNOWLEDGE BOUNDARY:
#
# - The actor is fixed by orchestration. The model cannot change it.
# - The interpreter receives only explicitly permitted entity references.
# - Any target/destination/instrument returned by the model must match one
#   of those permitted references exactly.
# - No world-state mutation happens here.
# - No action outcome is accepted here.
# - No difficulty, automatic success, impossibility, stat pairing, or other
#   resolver metadata is accepted from the model in this first version.
#
# Therefore:
#
#   Character Brain: "I try to open the oak door."
#       ->
#   Action Interpreter: ActionIntent(OPEN, target=oak_door)
#       ->
#   Resolver: decides whether/how it can succeed
#       ->
#   Executor: applies authoritative consequences
# ============================================================


DEFAULT_MAX_LENGTH = 300
DEFAULT_TEMPERATURE = 0.2

ALLOWED_OUTPUT_KEYS = {
    "action_type",
    "target_ref",
    "destination_ref",
    "instrument_ref",
}

INTERPRETER_OUTPUT_INSTRUCTION = """
OUTPUT FORMAT

Return exactly one JSON object:

{
  "action_type": "open",
  "target_ref": "object:12",
  "destination_ref": null,
  "instrument_ref": null
}

Rules:
- Interpret ONLY the supplied intended action.
- Choose action_type only from the supplied allowed action types.
- Use only entity reference keys from the supplied PERMITTED REFERENCES.
- If no target/destination/instrument is required or clearly intended, use null.
- Do not invent entity IDs or refer to entities outside the permitted references.
- Do not decide success, failure, difficulty, rolls, consequences, hidden facts,
  another character's response, or any world-state change.
- Do not rewrite the actor.
- Do not add narration outside the JSON object.
""".strip()


@dataclass(frozen=True)
class PermittedEntity:
    ref_key: str
    entity: EntityRef


@dataclass(frozen=True)
class ActionInterpretationResult:
    character_id: int
    model: str
    intent: ActionIntent
    raw_text: str


def _clean_text(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def _model_candidates():
    """
    Reuse the campaign's Director model configuration.

    Action interpretation is part of orchestration/directing rather than a
    character's mind, so it should not consume the character's personality
    model configuration.
    """
    preferred = _clean_text(
        get_campaign_setting(
            "director_model"
        )
    )

    fallback_raw = _clean_text(
        get_campaign_setting(
            "director_fallback_models"
        )
    )

    candidates = []

    if preferred:
        candidates.append(preferred)

    if fallback_raw:
        for model in fallback_raw.split(","):
            model = model.strip()

            if (
                model
                and model not in candidates
            ):
                candidates.append(model)

    if not candidates:
        raise RuntimeError(
            "No orchestration model is configured. "
            "Set campaign setting 'director_model'."
        )

    return candidates


def _normalize_permitted_entities(
    permitted_entities: Optional[Iterable],
):
    """
    Accept EntityRef objects, PermittedEntity objects, or dictionaries with
    entity_type/entity_id/name.

    Duplicate ref keys are rejected rather than silently picking one.
    """
    if permitted_entities is None:
        permitted_entities = []

    normalized = []
    seen = set()

    for item in permitted_entities:
        if isinstance(
            item,
            PermittedEntity,
        ):
            permitted = item

        elif isinstance(
            item,
            EntityRef,
        ):
            ref_key = (
                f"{item.entity_type}:"
                f"{item.entity_id}"
            )

            permitted = PermittedEntity(
                ref_key=ref_key,
                entity=item,
            )

        elif isinstance(
            item,
            dict,
        ):
            entity_type = _clean_text(
                item.get(
                    "entity_type"
                )
            )

            entity_id = _clean_text(
                item.get(
                    "entity_id"
                )
            )

            if (
                entity_type is None
                or entity_id is None
            ):
                raise ValueError(
                    "Permitted entity dictionaries require "
                    "entity_type and entity_id."
                )

            entity = make_entity(
                entity_type,
                entity_id,
                item.get("name"),
            )

            ref_key = _clean_text(
                item.get("ref_key")
            ) or (
                f"{entity.entity_type}:"
                f"{entity.entity_id}"
            )

            permitted = PermittedEntity(
                ref_key=ref_key,
                entity=entity,
            )

        else:
            raise TypeError(
                "permitted_entities must contain EntityRef, "
                "PermittedEntity, or dict values."
            )

        if permitted.ref_key in seen:
            raise ValueError(
                "Duplicate permitted entity reference: "
                f"{permitted.ref_key}"
            )

        seen.add(
            permitted.ref_key
        )

        normalized.append(
            permitted
        )

    return normalized


def _permitted_reference_map(
    permitted_entities,
):
    return {
        item.ref_key: item.entity
        for item in permitted_entities
    }


def build_action_interpreter_prompt(
    character_id,
    action_text,
    permitted_entities=None,
):
    action_text = _clean_text(
        action_text
    )

    if action_text is None:
        raise ValueError(
            "action_text cannot be empty."
        )

    permitted = (
        _normalize_permitted_entities(
            permitted_entities
        )
    )

    references = [
        {
            "ref_key": item.ref_key,
            "entity_type":
                item.entity.entity_type,
            "entity_id":
                item.entity.entity_id,
            "name":
                item.entity.name,
        }
        for item in permitted
    ]

    allowed_types = [
        action_type.value
        for action_type
        in ActionType
    ]

    return (
        "ACTION INTERPRETATION TASK\n\n"
        f"Actor is fixed as character:{int(character_id)}.\n"
        "The actor cannot be changed.\n\n"
        "INTENDED ACTION\n"
        f"{action_text}\n\n"
        "ALLOWED ACTION TYPES\n"
        + json.dumps(
            allowed_types,
            ensure_ascii=False,
        )
        + "\n\n"
        "PERMITTED REFERENCES\n"
        + json.dumps(
            references,
            ensure_ascii=False,
            indent=2,
        )
        + "\n\n"
        + INTERPRETER_OUTPUT_INSTRUCTION
    )


def _extract_json_object(
    raw_text,
):
    text = str(
        raw_text or ""
    ).strip()

    if not text:
        raise ValueError(
            "Action interpreter returned empty output."
        )

    if text.startswith("```"):
        lines = text.splitlines()

        if lines:
            lines = lines[1:]

        if (
            lines
            and lines[-1].strip()
            == "```"
        ):
            lines = lines[:-1]

        text = "\n".join(
            lines
        ).strip()

    try:
        data = json.loads(
            text
        )
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")

        if (
            start == -1
            or end == -1
            or end <= start
        ):
            raise ValueError(
                "Action interpreter did not return a JSON object."
            )

        try:
            data = json.loads(
                text[
                    start:end + 1
                ]
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Action interpreter returned malformed JSON."
            ) from exc

    if not isinstance(
        data,
        dict,
    ):
        raise ValueError(
            "Action interpreter output must be one JSON object."
        )

    return data


def _resolve_reference(
    reference_key,
    reference_map,
    field_name,
):
    if reference_key is None:
        return None

    reference_key = _clean_text(
        reference_key
    )

    if reference_key is None:
        return None

    if (
        reference_key
        not in reference_map
    ):
        raise ValueError(
            f"Interpreter returned unpermitted {field_name} "
            f"reference: {reference_key}"
        )

    return reference_map[
        reference_key
    ]


def parse_action_interpretation(
    character_id,
    action_text,
    model,
    raw_text,
    *,
    permitted_entities=None,
):
    action_text = _clean_text(
        action_text
    )

    if action_text is None:
        raise ValueError(
            "action_text cannot be empty."
        )

    data = _extract_json_object(
        raw_text
    )

    unexpected = (
        set(data)
        - ALLOWED_OUTPUT_KEYS
    )

    if unexpected:
        raise ValueError(
            "Action interpreter returned unsupported fields: "
            + ", ".join(
                sorted(unexpected)
            )
        )

    action_type_raw = _clean_text(
        data.get(
            "action_type"
        )
    )

    if action_type_raw is None:
        raise ValueError(
            "Action interpreter did not supply action_type."
        )

    try:
        action_type = ActionType(
            action_type_raw
        )
    except ValueError as exc:
        raise ValueError(
            "Action interpreter returned an unsupported action_type: "
            f"{action_type_raw}"
        ) from exc

    permitted = (
        _normalize_permitted_entities(
            permitted_entities
        )
    )

    reference_map = (
        _permitted_reference_map(
            permitted
        )
    )

    target = _resolve_reference(
        data.get(
            "target_ref"
        ),
        reference_map,
        "target",
    )

    destination = (
        _resolve_reference(
            data.get(
                "destination_ref"
            ),
            reference_map,
            "destination",
        )
    )

    instrument = (
        _resolve_reference(
            data.get(
                "instrument_ref"
            ),
            reference_map,
            "instrument",
        )
    )

    actor = make_entity(
        "character",
        int(character_id),
    )

    intent = make_action(
        action_type,
        actor=actor,
        description=action_text,
        target=target,
        destination=destination,
        instrument=instrument,
        source_type=
            "character_brain",
        source_id=
            str(character_id),
        asserted_outcome=None,
        metadata={},
    )

    return ActionInterpretationResult(
        character_id=int(
            character_id
        ),
        model=str(model),
        intent=intent,
        raw_text=str(raw_text),
    )


def run_action_interpreter(
    character_id,
    action_text,
    *,
    permitted_entities=None,
    generator: Callable = horde_generate,
    max_length=
        DEFAULT_MAX_LENGTH,
    temperature=
        DEFAULT_TEMPERATURE,
):
    """
    Interpret a Character Brain action into an ActionIntent.

    No resolver or executor is called here.
    """
    permitted = (
        _normalize_permitted_entities(
            permitted_entities
        )
    )

    prompt = (
        build_action_interpreter_prompt(
            character_id,
            action_text,
            permitted,
        )
    )

    errors = []

    for model in _model_candidates():
        try:
            raw_text = generator(
                prompt=prompt,
                model=model,
                max_length=max_length,
                temperature=
                    temperature,
                stop_sequences=[],
            )

            return (
                parse_action_interpretation(
                    character_id,
                    action_text,
                    model,
                    raw_text,
                    permitted_entities=
                        permitted,
                )
            )

        except Exception as exc:
            errors.append(
                f"{model}: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

    raise RuntimeError(
        "All configured action interpretation models failed. "
        + " | ".join(errors)
    )
