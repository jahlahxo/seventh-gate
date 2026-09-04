from __future__ import annotations

from database import get_connection
from characters import get_character_sheet
from development import (
    build_developmental_grounding,
    get_development_profile,
)
from entities import get_inventory
from life import (
    get_age_months,
    get_age_years,
)
from memory import retrieve_for_character
from mortality import is_alive
from world import (
    get_location,
    get_participant_location,
)


# ============================================================
# CHARACTER CONTEXT ASSEMBLY
#
# Governing rule:
#
#   Start with nothing. Add only information this character is
#   entitled to receive.
#
# IMPORTANT ARCHITECTURAL BOUNDARY:
#
# This module does NOT inspect raw Discord/RP messages, raw world
# events, co-located characters, global lore, canonical facts,
# hidden family/reproductive facts, or another character's private
# state in order to decide what was perceived.
#
# The future Director/perception layer owns that job.
#
# Character Context accepts an already-filtered PERCEPTION PACKET
# and combines it with this character's own identity, self-knowledge,
# subjective relationships, relevant memories/knowledge, possessions,
# development, and current physical location.
# ============================================================


ATTRIBUTE_LABELS = {
    0: "notably weak",
    1: "below average",
    2: "ordinary",
    3: "strong",
    4: "exceptional",
}

SKILL_LABELS = {
    0: "untrained",
    1: "novice",
    2: "competent",
    3: "skilled",
    4: "exceptional",
}


# Prompt-size safeguards. These are intentionally generous enough for
# rich RP while preventing a malformed/oversized database field from
# consuming the character brain's entire context window.
MAX_IDENTITY_FIELD_CHARS = 1200
MAX_RELATIONSHIP_SUMMARY_CHARS = 700
MAX_MEMORY_ITEM_CHARS = 900
MAX_PERCEPTION_ITEM_CHARS = 1200
MAX_RENDERED_CONTEXT_CHARS = 16000


def _require_character(character_id):
    character_id = int(character_id)

    conn = get_connection()
    row = conn.execute(
        """
        SELECT *
        FROM characters
        WHERE id = ?
          AND active = 1
        """,
        (character_id,),
    ).fetchone()
    conn.close()

    if row is None:
        raise ValueError(
            f"Character {character_id} does not exist or is inactive."
        )

    return row


def _clean_text(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def _clip(value, max_chars):
    value = _clean_text(value)

    if value is None:
        return None

    if len(value) <= max_chars:
        return value

    return value[: max_chars - 1].rstrip() + "…"


def _character_identity(character):
    """
    Whitelist character-self information.

    private_character_notes is intentionally excluded. Those notes are
    author/engine metadata and may contain facts the character does not know.

    Convention: `background` is treated as the character's own known history.
    Unknown/secret biography belongs in private notes, canonical facts, or
    another engine-owned store rather than this field.
    """
    fields = (
        "name",
        "description",
        "personality",
        "background",
        "appearance",
        "speech_style",
        "goals",
        "fears",
        "values_beliefs",
        "habits_mannerisms",
    )

    result = {}

    for field in fields:
        value = _clip(
            character[field],
            MAX_IDENTITY_FIELD_CHARS,
        )

        if value is not None:
            result[field] = value

    return result


def _runtime_metadata(
    character,
    *,
    alive,
    ai_participation_mode,
):
    """
    Orchestration-only metadata.

    render_character_context() never renders this section.
    """
    return {
        "character_id": int(character["id"]),
        "discord_bot_user_id": character["discord_bot_user_id"],
        "preferred_model": character["preferred_model"],
        "fallback_models": character["fallback_models"],
        "alive": bool(alive),
        "ai_participation_mode": ai_participation_mode,
        "may_invoke_ai_brain": (
            bool(alive)
            and ai_participation_mode
            in {"limited", "full"}
        ),
    }


def _explicit_attributes(character_id):
    """
    Distinguish explicitly-established values from an absent sheet.

    characters.get_attributes() correctly returns zero for missing stats for
    mechanical callers, but Character Context must not tell an unconfigured
    character that every attribute is 'notably weak'.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT stat_name, stat_value
        FROM character_stats
        WHERE owner_type = 'character'
          AND owner_id = ?
        ORDER BY stat_name
        """,
        (int(character_id),),
    ).fetchall()
    conn.close()

    return {
        row["stat_name"]: int(row["stat_value"])
        for row in rows
    }


def _qualitative_capabilities(character_id):
    sheet = get_character_sheet(
        "character",
        character_id,
    )

    attributes = {
        name: ATTRIBUTE_LABELS.get(
            value,
            "unknown",
        )
        for name, value
        in _explicit_attributes(
            character_id
        ).items()
    }

    skills = {}

    for name, info in sheet["skills"].items():
        value = int(info["value"])

        if value <= 0:
            continue

        skills[name] = {
            "level": SKILL_LABELS.get(
                value,
                "unknown",
            ),
            "notes": _clip(
                info.get("notes"),
                500,
            ),
        }

    traits = [
        {
            "name": _clip(
                trait["name"],
                250,
            ),
            "description": _clip(
                trait.get("description"),
                600,
            ),
        }
        for trait in sheet["traits"]
    ]

    return {
        "attributes": attributes,
        "skills": skills,
        "traits": traits,
    }


def _current_location_context(character_id):
    placement = get_participant_location(
        "character",
        character_id,
    )

    if placement is None:
        return None

    location = get_location(
        placement["location_id"]
    )

    if location is None:
        return None

    # private_notes is deliberately excluded.
    return {
        "id": int(location["id"]),
        "name": location["name"],
        "description": _clip(
            location["description"],
            1200,
        ),
        "parent_location_id":
            location["parent_location_id"],
    }


def _participant_public_name(
    participant_type,
    participant_id,
):
    conn = get_connection()

    if participant_type == "character":
        row = conn.execute(
            """
            SELECT name
            FROM characters
            WHERE id = ?
              AND active = 1
            """,
            (int(participant_id),),
        ).fetchone()

        name = (
            None
            if row is None
            else row["name"]
        )

    elif participant_type == "player_persona":
        row = conn.execute(
            """
            SELECT rp_name
            FROM player_personas
            WHERE id = ?
              AND active = 1
            """,
            (int(participant_id),),
        ).fetchone()

        name = (
            None
            if row is None
            else row["rp_name"]
        )

    else:
        name = None

    conn.close()
    return name


def _self_inventory(character_id):
    rows = get_inventory(
        "character",
        character_id,
    )

    result = []

    for row in rows:
        result.append(
            {
                "id": int(row["id"]),
                "name": row["name"],
                "object_type": row["object_type"],
                "description": _clip(
                    row["description"],
                    600,
                ),
                "relation": row["relation"],
            }
        )

    return result


def _subjective_relationships(character_id):
    """
    Read ONLY this character's relationship row.

    Objective family_links are intentionally excluded because biology,
    guardianship, adoption, etc. may be engine truth without being known
    or understood by this character.
    """
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM relationships
        WHERE character_id = ?
        ORDER BY id
        """,
        (int(character_id),),
    ).fetchall()

    conn.close()

    result = []

    for row in rows:
        result.append(
            {
                "target_type":
                    row["target_type"],
                "target_id":
                    row["target_id"],
                "target_name":
                    _participant_public_name(
                        row["target_type"],
                        row["target_id"],
                    ),
                "relationship_label":
                    _clip(
                        row["relationship_label"],
                        200,
                    ),
                "summary":
                    _clip(
                        row["summary"],
                        MAX_RELATIONSHIP_SUMMARY_CHARS,
                    ),

                # These are this character's own established subjective
                # dimensions. They remain structured self-state; the prompt
                # renderer currently prefers natural-language label/summary.
                "affection": row["affection"],
                "trust": row["trust"],
                "respect": row["respect"],
                "fear": row["fear"],
                "resentment": row["resentment"],
                "attraction": row["attraction"],
            }
        )

    return result


def _normalize_memory_result(item):
    row = item["row"]

    return {
        "content": _clip(
            row["content"],
            MAX_MEMORY_ITEM_CHARS,
        ),
        "memory_type":
            row["memory_type"],
        "emotional_context":
            _clip(
                row["emotional_context"],
                400,
            ),
        "importance":
            row["importance"],
        "confidence":
            row["confidence"],
        "similarity":
            item["similarity"],
    }


def _normalize_knowledge_result(item):
    row = item["row"]

    return {
        "content": _clip(
            row["content"],
            MAX_MEMORY_ITEM_CHARS,
        ),
        "knowledge_type":
            row["knowledge_type"],
        "subject_type":
            row["subject_type"],
        "subject_id":
            row["subject_id"],
        "confidence":
            row["confidence"],
        "importance":
            row["importance"],
        "is_secret":
            bool(row["is_secret"]),
        "similarity":
            item["similarity"],
    }


def _relevant_character_memory(
    character_id,
    query,
    memory_limit,
    knowledge_limit,
):
    if not str(query or "").strip():
        return {
            "memories": [],
            "knowledge": [],
        }

    found = retrieve_for_character(
        character_id,
        query,
        memory_limit=memory_limit,
        knowledge_limit=knowledge_limit,
    )

    return {
        "memories": [
            _normalize_memory_result(item)
            for item in found["memories"]
        ],
        "knowledge": [
            _normalize_knowledge_result(item)
            for item in found["knowledge"]
        ],
    }


def _developmental_context(character_id):
    profile = get_development_profile(
        character_id
    )

    age_years = get_age_years(
        "character",
        character_id,
    )

    age_months = get_age_months(
        "character",
        character_id,
    )

    grounding = (
        None
        if age_years is None
        else build_developmental_grounding(
            character_id
        )
    )

    # Deliberately do NOT call get_development_context(); that broader
    # engine-facing helper contains objective care/family relationships.
    return {
        "age_years": age_years,
        "age_months": age_months,
        "developmental_stage_override":
            profile[
                "developmental_stage_override"
            ],
        "developmental_notes":
            profile["developmental_notes"],
        "ai_participation_mode":
            profile["ai_participation_mode"],
        "grounding": grounding,
    }


def _normalize_perception_packet(perception):
    """
    Accept ONLY information already filtered for this character.

    Expected optional keys:
        current      -> current perceived event/input
        environment  -> weather/sounds/smells/visible scene description
        people       -> list of perceived people (dicts or strings)
        objects      -> list of perceived objects (dicts or strings)
        recent       -> list of recent perceived dialogue/events
        private      -> private body/sensory notices addressed to this character

    Character Context does not infer perception from co-location.
    """
    if perception is None:
        perception = {}

    if not isinstance(perception, dict):
        raise TypeError(
            "perception must be a dict already filtered for this character."
        )

    def clean_list(key):
        values = perception.get(key) or []

        if not isinstance(values, (list, tuple)):
            raise TypeError(
                f"perception['{key}'] must be a list."
            )

        cleaned = []

        for value in values:
            if isinstance(value, dict):
                item = {}

                for k, v in value.items():
                    if v is not None:
                        item[str(k)] = _clip(
                            v,
                            MAX_PERCEPTION_ITEM_CHARS,
                        )

                cleaned.append(item)
            else:
                cleaned.append(
                    _clip(
                        value,
                        MAX_PERCEPTION_ITEM_CHARS,
                    )
                )

        return cleaned

    return {
        "current": _clip(
            perception.get("current"),
            MAX_PERCEPTION_ITEM_CHARS,
        ),
        "environment": _clip(
            perception.get("environment"),
            MAX_PERCEPTION_ITEM_CHARS,
        ),
        "people": clean_list("people"),
        "objects": clean_list("objects"),
        "recent": clean_list("recent"),
        "private": clean_list("private"),
    }


def build_character_context(
    character_id,
    perception,
    *,
    query=None,
    memory_limit=6,
    knowledge_limit=8,
):
    """
    Build the whitelist-based context packet for one AI character.

    `perception` MUST already be filtered for this character by the future
    Director/perception layer (or by a trusted test/orchestration caller).

    The context assembler does not decide what a character can see/hear and
    does not read raw RP history to guess.

    `query` defaults to the current/environment/recent perceived material and
    is used only to retrieve this character's own memories/knowledge.
    """
    character = _require_character(
        character_id
    )

    perception = _normalize_perception_packet(
        perception
    )

    if query is None:
        query_parts = [
            perception["current"],
            perception["environment"],
        ]

        for item in perception["recent"][-4:]:
            if isinstance(item, dict):
                query_parts.extend(
                    str(value)
                    for value in item.values()
                )
            elif item:
                query_parts.append(str(item))

        query = " ".join(
            part
            for part in query_parts
            if part
        )

    alive = is_alive(
        "character",
        character_id,
    )

    development = _developmental_context(
        character_id
    )

    retrieved = _relevant_character_memory(
        character_id,
        query,
        memory_limit,
        knowledge_limit,
    )

    return {
        "runtime": _runtime_metadata(
            character,
            alive=alive,
            ai_participation_mode=development[
                "ai_participation_mode"
            ],
        ),

        "self": {
            "identity": _character_identity(
                character
            ),
            "alive": alive,
            "capabilities":
                _qualitative_capabilities(
                    character_id
                ),
            "development":
                development,
            "relationships":
                _subjective_relationships(
                    character_id
                ),
            "inventory":
                _self_inventory(
                    character_id
                ),
        },

        "situation": {
            "location":
                _current_location_context(
                    character_id
                ),
            "perception": perception,
        },

        "memory": retrieved,

        "access_boundary": {
            "canonical_world_truth_included":
                False,
            "global_world_lore_included":
                False,
            "raw_world_events_included":
                False,
            "raw_rp_history_included":
                False,
            "automatic_colocation_perception_included":
                False,
            "other_character_internal_state_included":
                False,
            "objective_family_links_included":
                False,
            "hidden_reproductive_state_included":
                False,
        },
    }


def _append_field(lines, label, value):
    value = _clean_text(value)

    if value is not None:
        lines.append(
            f"{label}: {value}"
        )


def _render_perception_item(item):
    if isinstance(item, dict):
        return "; ".join(
            f"{key}: {value}"
            for key, value in item.items()
            if value is not None
        )

    return str(item)


def render_character_context(context):
    """
    Render ONLY the character-facing packet.

    `runtime` and `access_boundary` are orchestration/debug metadata and are
    intentionally not rendered into the character brain prompt.
    """
    identity = context["self"]["identity"]
    situation = context["situation"]
    perception = situation["perception"]
    memory = context["memory"]
    development = context["self"][
        "development"
    ]

    lines = [
        "CHARACTER CONTEXT",
        "",
        "CORE DIRECTIVE",
        (
            "You are this character only. Think, feel, interpret, speak, "
            "and choose only for yourself. Do not write another person's "
            "private thoughts, feelings, beliefs, intentions, or voluntary "
            "choices. Do not treat model knowledge as character knowledge."
        ),
        "",
        "IDENTITY",
    ]

    _append_field(lines, "Name", identity.get("name"))
    _append_field(lines, "Description", identity.get("description"))
    _append_field(lines, "Personality", identity.get("personality"))
    _append_field(lines, "Background", identity.get("background"))
    _append_field(lines, "Appearance", identity.get("appearance"))
    _append_field(lines, "Speech style", identity.get("speech_style"))
    _append_field(lines, "Goals", identity.get("goals"))
    _append_field(lines, "Fears", identity.get("fears"))
    _append_field(lines, "Values/beliefs", identity.get("values_beliefs"))
    _append_field(lines, "Habits/mannerisms", identity.get("habits_mannerisms"))

    if development["grounding"]:
        lines.extend(
            [
                "",
                development["grounding"],
            ]
        )

    capabilities = context["self"][
        "capabilities"
    ]

    if (
        capabilities["attributes"]
        or capabilities["skills"]
        or capabilities["traits"]
    ):
        lines.extend(
            [
                "",
                "CAPABILITIES",
                (
                    "Use these as lived self-knowledge, not as game statistics "
                    "to quote aloud."
                ),
            ]
        )

    if capabilities["attributes"]:
        lines.append(
            "Attributes: "
            + ", ".join(
                f"{name}={level}"
                for name, level
                in capabilities[
                    "attributes"
                ].items()
            )
        )

    if capabilities["skills"]:
        lines.append(
            "Skills: "
            + ", ".join(
                f"{name}={info['level']}"
                for name, info
                in capabilities[
                    "skills"
                ].items()
            )
        )

    if capabilities["traits"]:
        lines.append(
            "Traits: "
            + "; ".join(
                (
                    trait["name"]
                    + (
                        f" ({trait['description']})"
                        if trait["description"]
                        else ""
                    )
                )
                for trait
                in capabilities["traits"]
            )
        )

    relationships = context["self"][
        "relationships"
    ]

    if relationships:
        lines.extend(
            [
                "",
                "YOUR RELATIONSHIPS",
            ]
        )

        for rel in relationships:
            target = (
                rel["target_name"]
                or (
                    f"{rel['target_type']} "
                    f"{rel['target_id']}"
                )
            )

            details = []

            if rel["relationship_label"]:
                details.append(
                    rel["relationship_label"]
                )

            if rel["summary"]:
                details.append(
                    rel["summary"]
                )

            lines.append(
                f"- {target}: "
                + (
                    "; ".join(details)
                    if details
                    else "relationship established"
                )
            )

    inventory = context["self"][
        "inventory"
    ]

    if inventory:
        lines.extend(
            [
                "",
                "WHAT YOU HAVE WITH YOU",
            ]
        )

        for obj in inventory:
            lines.append(
                f"- {obj['name']} "
                f"({obj['relation']})"
            )

    location = situation["location"]

    lines.extend(
        [
            "",
            "CURRENT SITUATION",
        ]
    )

    if location is None:
        lines.append(
            "Current physical location: not established."
        )
    else:
        lines.append(
            f"Current physical location: "
            f"{location['name']}"
        )

        _append_field(
            lines,
            "General location description",
            location.get("description"),
        )

    if perception["environment"]:
        _append_field(
            lines,
            "What you currently perceive around you",
            perception["environment"],
        )

    if perception["people"]:
        lines.append(
            "People you currently perceive:"
        )

        for item in perception["people"]:
            lines.append(
                "- " + _render_perception_item(item)
            )

    if perception["objects"]:
        lines.append(
            "Objects/details you currently perceive:"
        )

        for item in perception["objects"]:
            lines.append(
                "- " + _render_perception_item(item)
            )

    if perception["recent"]:
        lines.extend(
            [
                "",
                "RECENT THINGS YOU PERCEIVED",
            ]
        )

        for item in perception["recent"]:
            lines.append(
                "- " + _render_perception_item(item)
            )

    if perception["private"]:
        lines.extend(
            [
                "",
                "PRIVATE SENSORY / BODY NOTICES",
            ]
        )

        for item in perception["private"]:
            lines.append(
                "- " + _render_perception_item(item)
            )

    if memory["knowledge"]:
        lines.extend(
            [
                "",
                "RELEVANT THINGS YOU KNOW OR BELIEVE",
            ]
        )

        for item in memory["knowledge"]:
            lines.append(
                f"- {item['content']}"
            )

    if memory["memories"]:
        lines.extend(
            [
                "",
                "RELEVANT MEMORIES",
            ]
        )

        for item in memory["memories"]:
            lines.append(
                f"- {item['content']}"
            )

    if perception["current"]:
        lines.extend(
            [
                "",
                "CURRENT PERCEIVED INPUT",
                perception["current"],
            ]
        )

    lines.extend(
        [
            "",
            "RESPONSE BOUNDARY",
            (
                "Respond only from what this character can perceive, remember, "
                "know, believe, infer, feel, and choose. If you lack information, "
                "remain uncertain rather than importing hidden world truth."
            ),
        ]
    )

    rendered = "\n".join(lines)

    if len(rendered) > MAX_RENDERED_CONTEXT_CHARS:
        rendered = (
            rendered[: MAX_RENDERED_CONTEXT_CHARS - 160].rstrip()
            + "\n\n[Context truncated to preserve model headroom.]\n\n"
            + "RESPONSE BOUNDARY\n"
            + (
                "Remain within this character's own perception, knowledge, "
                "memories, feelings, and choices. Do not invent hidden truth."
            )
        )

    return rendered
