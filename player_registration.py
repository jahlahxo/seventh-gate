from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from characters import (
    ATTRIBUTE_NAMES,
    SKILL_NAMES,
)
from database import get_connection


ATTRIBUTE_POINT_BUDGET = 8
SKILL_POINT_BUDGET = 10
REGISTRATION_ATTRIBUTE_MIN = 0
REGISTRATION_ATTRIBUTE_MAX = 4
REGISTRATION_SKILL_MIN = 0
REGISTRATION_SKILL_MAX = 3
MAX_CHARACTER_NAME_LENGTH = 32
PENDING_MARKER = "seventh_gate_registration_pending_v1"


class RegistrationError(ValueError):
    def __init__(self, errors):
        if isinstance(errors, str):
            errors = [errors]

        self.errors = tuple(
            str(error)
            for error in errors
        )
        super().__init__(
            "\n".join(self.errors)
        )


@dataclass(frozen=True)
class RegistrationDraft:
    character_name: str
    age: int
    gender: str
    origin: str
    occupation: str
    appearance: str
    background: str
    attributes: Mapping[str, int]
    skills: Mapping[str, int]


@dataclass(frozen=True)
class PendingRegistration:
    persona_id: int
    draft: RegistrationDraft


def render_registration_template():
    lines = [
        "━━━━━━━━━━━━━━━━━━",
        "CHARACTER REGISTRATION",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "CHARACTER NAME:",
        "AGE:",
        "GENDER:",
        "ORIGIN:",
        "OCCUPATION:",
        "",
        "APPEARANCE:",
        "",
        "BRIEF BACKGROUND:",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "ATTRIBUTES — 8 POINTS",
        "━━━━━━━━━━━━━━━━━━",
        "",
        "Spend exactly 8 points. Minimum 0 / Maximum 4 each.",
        "",
    ]

    for name in ATTRIBUTE_NAMES:
        lines.append(f"{name}:")

    lines.extend(
        [
            "",
            "━━━━━━━━━━━━━━━━━━",
            "SKILLS — 10 POINTS",
            "━━━━━━━━━━━━━━━━━━",
            "",
            (
                "Spend exactly 10 points. Minimum 0 / Maximum 3 "
                "each at character creation."
            ),
            "",
        ]
    )

    for name in SKILL_NAMES:
        lines.append(f"{name}:")

    return "\n".join(lines)


_TEXT_LABELS = {
    "character name": "character_name",
    "age": "age",
    "gender": "gender",
    "origin": "origin",
    "occupation": "occupation",
    "appearance": "appearance",
    "brief background": "background",
    "background": "background",
}

_ATTRIBUTE_LABELS = {
    name.casefold(): name
    for name in ATTRIBUTE_NAMES
}

_SKILL_LABELS = {
    name.casefold(): name
    for name in SKILL_NAMES
}

_RETIRED_ATTRIBUTE_LABELS = {
    "wits",
    "presence",
}


def _clean_label(value):
    return (
        str(value)
        .replace("*", "")
        .replace("_", "")
        .replace("`", "")
        .strip()
        .casefold()
    )


def _looks_like_section_heading(line):
    text = str(line).strip()

    if not text:
        return False

    if text.startswith("━"):
        return True

    upper = text.upper()

    if (
        "POINTS" in upper
        and ":" not in text
    ):
        return True

    if upper == "CHARACTER REGISTRATION":
        return True

    if upper.startswith("SPEND EXACTLY "):
        return True

    return False


def _parse_int(raw, label, errors):
    raw = str(raw or "").strip()

    if not raw:
        errors.append(
            f"{label} needs a number."
        )
        return None

    try:
        return int(raw)
    except ValueError:
        errors.append(
            f"{label} must be a whole number."
        )
        return None


def parse_registration_message(content):
    content = str(
        content or ""
    ).strip()

    if not content:
        raise RegistrationError(
            "Registration message is empty."
        )

    text_values = {}
    numeric_values = {}
    errors = []
    seen_labels = set()
    multiline_key = None

    for raw_line in content.splitlines():
        line = raw_line.rstrip()

        if _looks_like_section_heading(line):
            multiline_key = None
            continue

        stripped = line.strip()

        if not stripped:
            if multiline_key in {
                "appearance",
                "background",
            }:
                existing = text_values.get(
                    multiline_key,
                    "",
                )
                if existing:
                    text_values[
                        multiline_key
                    ] = existing + "\n"
            continue

        if ":" in stripped:
            left, right = stripped.split(
                ":",
                1,
            )
            label = _clean_label(left)

            if label in _RETIRED_ATTRIBUTE_LABELS:
                errors.append(
                    f"{left.strip()} is not a Seventh Gate attribute."
                )
                multiline_key = None
                continue

            if label in _TEXT_LABELS:
                canonical = _TEXT_LABELS[
                    label
                ]
                duplicate_key = (
                    "text:" + canonical
                )

                if duplicate_key in seen_labels:
                    errors.append(
                        f"{left.strip()} was supplied more than once."
                    )
                    continue

                seen_labels.add(
                    duplicate_key
                )
                text_values[
                    canonical
                ] = right.strip()

                if canonical in {
                    "appearance",
                    "background",
                }:
                    multiline_key = canonical
                else:
                    multiline_key = None

                continue

            if label in _ATTRIBUTE_LABELS:
                canonical = (
                    _ATTRIBUTE_LABELS[
                        label
                    ]
                )
                duplicate_key = (
                    "attribute:" + canonical
                )

                if duplicate_key in seen_labels:
                    errors.append(
                        f"{canonical} was supplied more than once."
                    )
                    continue

                seen_labels.add(
                    duplicate_key
                )
                numeric_values[
                    canonical
                ] = right.strip()
                multiline_key = None
                continue

            if label in _SKILL_LABELS:
                canonical = (
                    _SKILL_LABELS[
                        label
                    ]
                )
                duplicate_key = (
                    "skill:" + canonical
                )

                if duplicate_key in seen_labels:
                    errors.append(
                        f"{canonical} was supplied more than once."
                    )
                    continue

                seen_labels.add(
                    duplicate_key
                )
                numeric_values[
                    canonical
                ] = right.strip()
                multiline_key = None
                continue

        if multiline_key in {
            "appearance",
            "background",
        }:
            existing = text_values.get(
                multiline_key,
                "",
            )

            if existing:
                text_values[
                    multiline_key
                ] = (
                    existing.rstrip()
                    + "\n"
                    + stripped
                )
            else:
                text_values[
                    multiline_key
                ] = stripped

    required_text = (
        "character_name",
        "age",
        "gender",
        "origin",
        "occupation",
        "appearance",
        "background",
    )

    for key in required_text:
        if not str(
            text_values.get(
                key,
                "",
            )
        ).strip():
            pretty = (
                key.replace(
                    "_",
                    " ",
                ).title()
            )
            errors.append(
                f"{pretty} is required."
            )

    age = _parse_int(
        text_values.get("age"),
        "Age",
        errors,
    )

    if (
        age is not None
        and not 0 <= age <= 130
    ):
        errors.append(
            "Age must be between 0 and 130."
        )

    character_name = str(
        text_values.get(
            "character_name",
            "",
        )
    ).strip()

    if (
        character_name
        and len(character_name)
        > MAX_CHARACTER_NAME_LENGTH
    ):
        errors.append(
            "Character Name must be "
            f"{MAX_CHARACTER_NAME_LENGTH} characters or fewer "
            "so Discord can use it as the server nickname."
        )

    attributes = {}

    for name in ATTRIBUTE_NAMES:
        if name not in numeric_values:
            errors.append(
                f"{name} needs a number."
            )
            continue

        value = _parse_int(
            numeric_values[name],
            name,
            errors,
        )

        if value is None:
            continue

        if not (
            REGISTRATION_ATTRIBUTE_MIN
            <= value
            <= REGISTRATION_ATTRIBUTE_MAX
        ):
            errors.append(
                f"{name} must be between "
                f"{REGISTRATION_ATTRIBUTE_MIN} and "
                f"{REGISTRATION_ATTRIBUTE_MAX}."
            )

        attributes[name] = value

    if (
        len(attributes)
        == len(ATTRIBUTE_NAMES)
    ):
        total = sum(
            attributes.values()
        )

        if total != ATTRIBUTE_POINT_BUDGET:
            if total > ATTRIBUTE_POINT_BUDGET:
                errors.append(
                    "Attribute budget exceeded: "
                    f"{total}/{ATTRIBUTE_POINT_BUDGET}."
                )
            else:
                errors.append(
                    "Attribute points remaining: "
                    f"{ATTRIBUTE_POINT_BUDGET - total}. "
                    f"Spend exactly {ATTRIBUTE_POINT_BUDGET}."
                )

    skills = {}

    for name in SKILL_NAMES:
        if name not in numeric_values:
            errors.append(
                f"{name} needs a number."
            )
            continue

        value = _parse_int(
            numeric_values[name],
            name,
            errors,
        )

        if value is None:
            continue

        if not (
            REGISTRATION_SKILL_MIN
            <= value
            <= REGISTRATION_SKILL_MAX
        ):
            errors.append(
                f"{name} must be between "
                f"{REGISTRATION_SKILL_MIN} and "
                f"{REGISTRATION_SKILL_MAX} "
                "at character creation."
            )

        skills[name] = value

    if (
        len(skills)
        == len(SKILL_NAMES)
    ):
        total = sum(
            skills.values()
        )

        if total != SKILL_POINT_BUDGET:
            if total > SKILL_POINT_BUDGET:
                errors.append(
                    "Skill budget exceeded: "
                    f"{total}/{SKILL_POINT_BUDGET}."
                )
            else:
                errors.append(
                    "Skill points remaining: "
                    f"{SKILL_POINT_BUDGET - total}. "
                    f"Spend exactly {SKILL_POINT_BUDGET}."
                )

    if errors:
        raise RegistrationError(errors)

    return RegistrationDraft(
        character_name=character_name,
        age=int(age),
        gender=str(
            text_values["gender"]
        ).strip(),
        origin=str(
            text_values["origin"]
        ).strip(),
        occupation=str(
            text_values["occupation"]
        ).strip(),
        appearance=str(
            text_values["appearance"]
        ).strip(),
        background=str(
            text_values["background"]
        ).strip(),
        attributes=dict(attributes),
        skills=dict(skills),
    )


def _ensure_tables():
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS
        player_registration_details (
            persona_id INTEGER PRIMARY KEY,
            declared_age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            origin TEXT NOT NULL,
            registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (persona_id)
                REFERENCES player_personas(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS
        idx_player_registration_origin
        ON player_registration_details(origin);
        """
    )
    conn.commit()
    conn.close()


def _validate_draft_instance(draft):
    if not isinstance(
        draft,
        RegistrationDraft,
    ):
        raise TypeError(
            "draft must be a RegistrationDraft."
        )

    errors = []

    if (
        set(draft.attributes)
        != set(ATTRIBUTE_NAMES)
    ):
        errors.append(
            "Attribute allocation contains missing "
            "or unsupported attributes."
        )

    if (
        sum(draft.attributes.values())
        != ATTRIBUTE_POINT_BUDGET
    ):
        errors.append(
            "Attribute allocation no longer matches "
            "the registration budget."
        )

    for name, value in draft.attributes.items():
        if not (
            REGISTRATION_ATTRIBUTE_MIN
            <= int(value)
            <= REGISTRATION_ATTRIBUTE_MAX
        ):
            errors.append(
                f"{name} is outside the registration attribute range."
            )

    if (
        set(draft.skills)
        != set(SKILL_NAMES)
    ):
        errors.append(
            "Skill allocation contains missing or unsupported skills."
        )

    if (
        sum(draft.skills.values())
        != SKILL_POINT_BUDGET
    ):
        errors.append(
            "Skill allocation no longer matches the registration budget."
        )

    for name, value in draft.skills.items():
        if not (
            REGISTRATION_SKILL_MIN
            <= int(value)
            <= REGISTRATION_SKILL_MAX
        ):
            errors.append(
                f"{name} is outside the registration skill range."
            )

    if errors:
        raise RegistrationError(errors)


def create_pending_player_registration(
    discord_user_id,
    discord_name,
    draft,
):
    _ensure_tables()
    _validate_draft_instance(draft)

    discord_user_id = str(
        discord_user_id
    ).strip()

    if not discord_user_id:
        raise RegistrationError(
            "Discord user ID is missing."
        )

    discord_name = str(
        discord_name or ""
    ).strip() or None

    conn = get_connection()

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        existing_user = conn.execute(
            """
            SELECT id
            FROM player_personas
            WHERE discord_user_id = ?
              AND (
                    active = 1
                    OR private_player_notes = ?
                  )
            LIMIT 1
            """,
            (
                discord_user_id,
                PENDING_MARKER,
            ),
        ).fetchone()

        if existing_user is not None:
            raise RegistrationError(
                "This Discord account already has a "
                "registered or pending character."
            )

        existing_name = conn.execute(
            """
            SELECT id
            FROM player_personas
            WHERE lower(rp_name) = lower(?)
              AND (
                    active = 1
                    OR private_player_notes = ?
                  )
            LIMIT 1
            """,
            (
                draft.character_name,
                PENDING_MARKER,
            ),
        ).fetchone()

        if existing_name is not None:
            raise RegistrationError(
                "That character name is already registered."
            )

        cursor = conn.execute(
            """
            INSERT INTO player_personas (
                discord_user_id,
                discord_name,
                rp_name,
                appearance,
                background,
                occupation,
                private_player_notes,
                active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                discord_user_id,
                discord_name,
                draft.character_name,
                draft.appearance,
                draft.background,
                draft.occupation,
                PENDING_MARKER,
            ),
        )

        persona_id = int(
            cursor.lastrowid
        )

        conn.execute(
            """
            INSERT INTO player_registration_details (
                persona_id,
                declared_age,
                gender,
                origin
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                persona_id,
                int(draft.age),
                draft.gender,
                draft.origin,
            ),
        )

        conn.executemany(
            """
            INSERT INTO character_stats (
                owner_type,
                owner_id,
                stat_name,
                stat_value
            )
            VALUES ('player_persona', ?, ?, ?)
            """,
            [
                (
                    persona_id,
                    name,
                    int(
                        draft.attributes[name]
                    ),
                )
                for name in ATTRIBUTE_NAMES
            ],
        )

        conn.executemany(
            """
            INSERT INTO character_skills (
                owner_type,
                owner_id,
                skill_name,
                skill_value,
                notes
            )
            VALUES ('player_persona', ?, ?, ?, NULL)
            """,
            [
                (
                    persona_id,
                    name,
                    int(
                        draft.skills[name]
                    ),
                )
                for name in SKILL_NAMES
            ],
        )

        conn.commit()

    except Exception:
        conn.rollback()
        conn.close()
        raise

    conn.close()

    return PendingRegistration(
        persona_id=persona_id,
        draft=draft,
    )


def activate_player_registration(
    persona_id,
):
    _ensure_tables()

    conn = get_connection()
    cursor = conn.execute(
        """
        UPDATE player_personas
        SET
            active = 1,
            private_player_notes = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
          AND active = 0
          AND private_player_notes = ?
        """,
        (
            int(persona_id),
            PENDING_MARKER,
        ),
    )
    conn.commit()
    conn.close()

    if cursor.rowcount != 1:
        raise RegistrationError(
            "Pending registration was not found."
        )

    return int(persona_id)


def cancel_player_registration(
    persona_id,
):
    _ensure_tables()
    persona_id = int(persona_id)

    conn = get_connection()

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        row = conn.execute(
            """
            SELECT id
            FROM player_personas
            WHERE id = ?
              AND active = 0
              AND private_player_notes = ?
            """,
            (
                persona_id,
                PENDING_MARKER,
            ),
        ).fetchone()

        if row is None:
            conn.rollback()
            conn.close()
            return False

        for table in (
            "character_stats",
            "character_skills",
            "character_traits",
        ):
            conn.execute(
                f"""
                DELETE FROM {table}
                WHERE owner_type = 'player_persona'
                  AND owner_id = ?
                """,
                (
                    persona_id,
                ),
            )

        conn.execute(
            """
            DELETE FROM player_registration_details
            WHERE persona_id = ?
            """,
            (
                persona_id,
            ),
        )

        conn.execute(
            """
            DELETE FROM player_personas
            WHERE id = ?
            """,
            (
                persona_id,
            ),
        )

        conn.commit()

    except Exception:
        conn.rollback()
        conn.close()
        raise

    conn.close()
    return True


def get_active_player_persona_for_discord(
    discord_user_id,
):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT *
        FROM player_personas
        WHERE discord_user_id = ?
          AND active = 1
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            str(discord_user_id),
        ),
    ).fetchone()
    conn.close()
    return row


def get_player_registration_details(
    persona_id,
):
    _ensure_tables()

    conn = get_connection()
    row = conn.execute(
        """
        SELECT
            d.*,
            p.discord_user_id,
            p.discord_name,
            p.rp_name,
            p.appearance,
            p.background,
            p.occupation,
            p.active
        FROM player_registration_details AS d
        JOIN player_personas AS p
          ON p.id = d.persona_id
        WHERE d.persona_id = ?
        """,
        (
            int(persona_id),
        ),
    ).fetchone()
    conn.close()
    return row


def register_player_immediately(
    discord_user_id,
    discord_name,
    draft,
):
    pending = (
        create_pending_player_registration(
            discord_user_id,
            discord_name,
            draft,
        )
    )

    try:
        activate_player_registration(
            pending.persona_id
        )
    except Exception:
        cancel_player_registration(
            pending.persona_id
        )
        raise

    return pending
