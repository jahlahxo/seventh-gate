import random

from campaign_clock import get_campaign_datetime
from database import get_connection
from reproduction import get_pregnancy, gestational_age_days


VALID_AWARENESS = {
    "unaware",
    "suspected",
    "believed",
    "confirmed",
}

# Broad narrative windows, not guaranteed symptoms.
# min_day/max_day define when a sign is plausible.
SIGN_DEFINITIONS = {
    "missed_period": {
        "min_day": 28,
        "max_day": 84,
        "chance": 0.70,
        "severity": 1,
        "description": "An expected menstrual period has not occurred.",
    },
    "fatigue": {
        "min_day": 21,
        "max_day": 98,
        "chance": 0.45,
        "severity": 1,
        "description": "She feels unusually tired without an obvious reason.",
    },
    "nausea": {
        "min_day": 28,
        "max_day": 112,
        "chance": 0.45,
        "severity": 1,
        "description": "A wave of nausea comes over her.",
    },
    "breast_changes": {
        "min_day": 28,
        "max_day": 112,
        "chance": 0.40,
        "severity": 1,
        "description": "She notices unfamiliar tenderness and bodily changes.",
    },
    "quickening": {
        "min_day": 112,
        "max_day": 168,
        "chance": 0.75,
        "severity": 2,
        "description": "She feels a faint, unfamiliar movement low in her abdomen.",
    },
    "visible_abdominal_change": {
        "min_day": 98,
        "max_day": 224,
        "chance": 0.65,
        "severity": 2,
        "description": "Her abdomen has begun to change noticeably.",
    },
}


def _owner_of(pregnancy):
    return (
        pregnancy["gestational_parent_type"],
        str(pregnancy["gestational_parent_id"]),
    )


def get_awareness(pregnancy_id):
    pregnancy = get_pregnancy(pregnancy_id)
    owner_type, owner_id = _owner_of(pregnancy)

    conn = get_connection()
    row = conn.execute(
        """
        SELECT *
        FROM pregnancy_awareness
        WHERE pregnancy_id = ?
          AND owner_type = ?
          AND owner_id = ?
        """,
        (int(pregnancy_id), owner_type, owner_id),
    ).fetchone()
    conn.close()

    if row is None:
        return {
            "pregnancy_id": int(pregnancy_id),
            "owner_type": owner_type,
            "owner_id": owner_id,
            "awareness_state": "unaware",
            "confidence": 0.0,
        }

    return row


def set_awareness(
    pregnancy_id,
    awareness_state,
    *,
    source_type,
    source_id=None,
    confidence=1.0,
):
    pregnancy = get_pregnancy(pregnancy_id)
    owner_type, owner_id = _owner_of(pregnancy)

    awareness_state = str(awareness_state).lower().strip()
    if awareness_state not in VALID_AWARENESS:
        raise ValueError("Invalid pregnancy awareness state.")

    confidence = float(confidence)
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1.")

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO pregnancy_awareness (
            pregnancy_id,
            owner_type,
            owner_id,
            awareness_state,
            confidence,
            source_type,
            source_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(pregnancy_id, owner_type, owner_id)
        DO UPDATE SET
            awareness_state = excluded.awareness_state,
            confidence = excluded.confidence,
            source_type = excluded.source_type,
            source_id = excluded.source_id,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            int(pregnancy_id),
            owner_type,
            owner_id,
            awareness_state,
            confidence,
            str(source_type),
            None if source_id is None else str(source_id),
        ),
    )
    conn.commit()
    conn.close()

    return get_awareness(pregnancy_id)


def _existing_sign_types(pregnancy_id):
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT sign_type
        FROM pregnancy_signs
        WHERE pregnancy_id = ?
        """,
        (int(pregnancy_id),),
    ).fetchall()
    conn.close()
    return {row["sign_type"] for row in rows}


def generate_plausible_signs(
    pregnancy_id,
    *,
    rng=None,
):
    """
    Generate zero or more bodily signs appropriate to current
    gestational age. Signs are evidence only: this function does
    not change awareness or decide what the character believes.

    Pass a seeded/random-compatible object in tests if desired.
    """
    pregnancy = get_pregnancy(pregnancy_id)

    if pregnancy["status"] != "ongoing":
        return []

    age = gestational_age_days(pregnancy_id)
    existing = _existing_sign_types(pregnancy_id)
    rng = rng or random

    now = get_campaign_datetime().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    created_ids = []
    conn = get_connection()

    for sign_type, definition in SIGN_DEFINITIONS.items():
        if sign_type in existing:
            continue

        if not (
            definition["min_day"]
            <= age
            <= definition["max_day"]
        ):
            continue

        if rng.random() >= definition["chance"]:
            continue

        cursor = conn.execute(
            """
            INSERT INTO pregnancy_signs (
                pregnancy_id,
                sign_type,
                description,
                gestational_age_days,
                severity,
                private_to_owner,
                created_campaign_datetime
            )
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                int(pregnancy_id),
                sign_type,
                definition["description"],
                age,
                definition["severity"],
                now,
            ),
        )
        created_ids.append(cursor.lastrowid)

    conn.commit()
    conn.close()

    return [
        get_sign(sign_id)
        for sign_id in created_ids
    ]


def get_sign(sign_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT *
        FROM pregnancy_signs
        WHERE id = ?
        """,
        (int(sign_id),),
    ).fetchone()
    conn.close()

    if row is None:
        raise ValueError("Pregnancy sign does not exist.")

    return row


def get_pending_private_signs(pregnancy_id):
    pregnancy = get_pregnancy(pregnancy_id)
    owner_type, owner_id = _owner_of(pregnancy)

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM pregnancy_signs
        WHERE pregnancy_id = ?
          AND private_to_owner = 1
          AND noticed = 0
        ORDER BY id
        """,
        (int(pregnancy_id),),
    ).fetchall()
    conn.close()

    return {
        "owner_type": owner_type,
        "owner_id": owner_id,
        "signs": rows,
    }


def mark_sign_noticed(sign_id):
    sign = get_sign(sign_id)
    now = get_campaign_datetime().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    conn = get_connection()
    conn.execute(
        """
        UPDATE pregnancy_signs
        SET
            noticed = 1,
            noticed_at = ?
        WHERE id = ?
        """,
        (now, int(sign_id)),
    )
    conn.commit()
    conn.close()

    return get_sign(sign_id)
