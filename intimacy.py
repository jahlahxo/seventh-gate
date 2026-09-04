from database import get_connection


VALID_PARTICIPANT_TYPES = {
    "character",
    "player_persona",
}

VALID_CONSENT_CONTEXTS = {
    "consensual",
    "coercive",
    "nonconsensual",
    "unclear",
}

VALID_WILLINGNESS = {
    "willing",
    "unwilling",
    "ambivalent",
    "unclear",
}

EXPERIENCE_MIN = 0
EXPERIENCE_MAX = 4


def _validate_participant_type(participant_type):
    participant_type = str(participant_type)

    if participant_type not in VALID_PARTICIPANT_TYPES:
        raise ValueError(
            f"Invalid participant type: {participant_type}"
        )

    return participant_type


def _require_participant(participant_type, participant_id):
    participant_type = _validate_participant_type(
        participant_type
    )
    participant_id = str(participant_id)

    conn = get_connection()

    if participant_type == "character":
        row = conn.execute(
            """
            SELECT id
            FROM characters
            WHERE id = ?
              AND active = 1
            """,
            (int(participant_id),),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id
            FROM player_personas
            WHERE id = ?
              AND active = 1
            """,
            (int(participant_id),),
        ).fetchone()

    conn.close()

    if row is None:
        raise ValueError(
            f"{participant_type} {participant_id} "
            "does not exist or is inactive."
        )

    return participant_type, participant_id


def _participant_location(participant_type, participant_id):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT location_id
        FROM participant_locations
        WHERE participant_type = ?
          AND participant_id = ?
        """,
        (
            participant_type,
            str(participant_id),
        ),
    ).fetchone()

    conn.close()

    if row is None:
        return None

    return row["location_id"]


def _validate_level(value, field_name):
    if value is None:
        return None

    value = int(value)

    if not EXPERIENCE_MIN <= value <= EXPERIENCE_MAX:
        raise ValueError(
            f"{field_name} must be between "
            f"{EXPERIENCE_MIN} and {EXPERIENCE_MAX}, "
            "or None when not established."
        )

    return value


# ============================================================
# OBJECTIVE INTIMATE EVENT
#
# Records that an encounter occurred and its in-fiction context.
# It does not create any participant's subjective experience.
# ============================================================

def create_intimate_event(
    participant_a_type,
    participant_a_id,
    participant_b_type,
    participant_b_id,
    consent_context="consensual",
    pregnancy_possible=False,
    world_event_id=None,
    notes=None,
    require_same_location=True,
):
    participant_a_type, participant_a_id = _require_participant(
        participant_a_type,
        participant_a_id,
    )

    participant_b_type, participant_b_id = _require_participant(
        participant_b_type,
        participant_b_id,
    )

    if (
        participant_a_type == participant_b_type
        and participant_a_id == participant_b_id
    ):
        raise ValueError(
            "An intimate event requires two distinct participants."
        )

    consent_context = str(consent_context).lower().strip()

    if consent_context not in VALID_CONSENT_CONTEXTS:
        raise ValueError(
            "consent_context must be one of: "
            + ", ".join(sorted(VALID_CONSENT_CONTEXTS))
        )

    if require_same_location:
        location_a = _participant_location(
            participant_a_type,
            participant_a_id,
        )

        location_b = _participant_location(
            participant_b_type,
            participant_b_id,
        )

        if (
            location_a is None
            or location_b is None
            or location_a != location_b
        ):
            raise ValueError(
                "Participants must share a physical location "
                "for a current intimate event."
            )

    if world_event_id is not None:
        conn = get_connection()

        event = conn.execute(
            """
            SELECT id
            FROM world_events
            WHERE id = ?
            """,
            (int(world_event_id),),
        ).fetchone()

        conn.close()

        if event is None:
            raise ValueError("world_event_id does not exist.")

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO intimate_events (
            world_event_id,
            participant_a_type,
            participant_a_id,
            participant_b_type,
            participant_b_id,
            consent_context,
            pregnancy_possible,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            world_event_id,
            participant_a_type,
            participant_a_id,
            participant_b_type,
            participant_b_id,
            consent_context,
            int(bool(pregnancy_possible)),
            notes,
        ),
    )

    intimate_event_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return intimate_event_id


def get_intimate_event(intimate_event_id):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM intimate_events
        WHERE id = ?
        """,
        (int(intimate_event_id),),
    ).fetchone()

    conn.close()

    if row is None:
        raise ValueError("Intimate event does not exist.")

    return row


def _require_event_participant(
    intimate_event_id,
    participant_type,
    participant_id,
):
    event = get_intimate_event(intimate_event_id)

    participant_type = str(participant_type)
    participant_id = str(participant_id)

    matches_a = (
        event["participant_a_type"] == participant_type
        and event["participant_a_id"] == participant_id
    )

    matches_b = (
        event["participant_b_type"] == participant_type
        and event["participant_b_id"] == participant_id
    )

    if not (matches_a or matches_b):
        raise ValueError(
            "That participant is not part of this intimate event."
        )

    return event


# ============================================================
# SUBJECTIVE EXPERIENCE OWNERSHIP
#
# A human persona can only establish its own internal state.
# An NPC can only establish its own internal state.
# One character can never author another character's mind.
# ============================================================

def _validate_experience_source(
    participant_type,
    participant_id,
    source_type,
    source_id,
):
    source_type = str(source_type)
    source_id = str(source_id)
    participant_id = str(participant_id)

    if participant_type == "player_persona":
        if (
            source_type != "player_self"
            or source_id != participant_id
        ):
            raise PermissionError(
                "A human-controlled persona's internal "
                "experience can only be established by "
                "that same player persona."
            )

    elif participant_type == "character":
        if (
            source_type != "character_self"
            or source_id != participant_id
        ):
            raise PermissionError(
                "An NPC's internal experience can only be "
                "established for that same NPC character."
            )


# ============================================================
# PARTICIPANT-SPECIFIC EXPERIENCE
#
# All subjective dimensions are intentionally independent.
# Physical response never implies willingness or enjoyment.
# ============================================================

def set_participant_experience(
    intimate_event_id,
    participant_type,
    participant_id,
    source_type,
    source_id,
    willingness=None,
    desire_level=None,
    physical_arousal_level=None,
    enjoyment_level=None,
    pain_level=None,
    climax=None,
    emotional_response=None,
    private_notes=None,
):
    participant_type, participant_id = _require_participant(
        participant_type,
        participant_id,
    )

    _require_event_participant(
        intimate_event_id,
        participant_type,
        participant_id,
    )

    _validate_experience_source(
        participant_type,
        participant_id,
        source_type,
        source_id,
    )

    if willingness is not None:
        willingness = str(willingness).lower().strip()

        if willingness not in VALID_WILLINGNESS:
            raise ValueError(
                "willingness must be one of: "
                + ", ".join(sorted(VALID_WILLINGNESS))
            )

    desire_level = _validate_level(
        desire_level,
        "desire_level",
    )

    physical_arousal_level = _validate_level(
        physical_arousal_level,
        "physical_arousal_level",
    )

    enjoyment_level = _validate_level(
        enjoyment_level,
        "enjoyment_level",
    )

    pain_level = _validate_level(
        pain_level,
        "pain_level",
    )

    if climax is not None:
        climax = int(bool(climax))

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO intimate_experiences (
            intimate_event_id,
            participant_type,
            participant_id,
            willingness,
            desire_level,
            physical_arousal_level,
            enjoyment_level,
            pain_level,
            climax,
            emotional_response,
            private_notes,
            source_type,
            source_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(
            intimate_event_id,
            participant_type,
            participant_id
        )
        DO UPDATE SET
            willingness = excluded.willingness,
            desire_level = excluded.desire_level,
            physical_arousal_level =
                excluded.physical_arousal_level,
            enjoyment_level = excluded.enjoyment_level,
            pain_level = excluded.pain_level,
            climax = excluded.climax,
            emotional_response =
                excluded.emotional_response,
            private_notes = excluded.private_notes,
            source_type = excluded.source_type,
            source_id = excluded.source_id,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            int(intimate_event_id),
            participant_type,
            participant_id,
            willingness,
            desire_level,
            physical_arousal_level,
            enjoyment_level,
            pain_level,
            climax,
            emotional_response,
            private_notes,
            str(source_type),
            str(source_id),
        ),
    )

    conn.commit()
    conn.close()

    return get_participant_experience(
        intimate_event_id,
        participant_type,
        participant_id,
    )


def get_participant_experience(
    intimate_event_id,
    participant_type,
    participant_id,
):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM intimate_experiences
        WHERE intimate_event_id = ?
          AND participant_type = ?
          AND participant_id = ?
        """,
        (
            int(intimate_event_id),
            str(participant_type),
            str(participant_id),
        ),
    ).fetchone()

    conn.close()

    return row


def get_event_experiences(intimate_event_id):
    get_intimate_event(intimate_event_id)

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM intimate_experiences
        WHERE intimate_event_id = ?
        ORDER BY id
        """,
        (int(intimate_event_id),),
    ).fetchall()

    conn.close()

    return rows
