from __future__ import annotations

from campaign_clock import get_campaign_datetime
from database import get_connection


VALID_OWNER_TYPES = {
    "character",
    "player_persona",
}


def _require_entity(
    owner_type,
    owner_id,
    *,
    conn=None,
):
    owner_type = str(owner_type)

    if owner_type not in VALID_OWNER_TYPES:
        raise ValueError(
            f"Invalid owner type: {owner_type}"
        )

    table = (
        "characters"
        if owner_type == "character"
        else "player_personas"
    )

    owns_connection = conn is None

    if conn is None:
        conn = get_connection()

    row = conn.execute(
        f"""
        SELECT id
        FROM {table}
        WHERE id = ?
        """,
        (int(owner_id),),
    ).fetchone()

    if owns_connection:
        conn.close()

    if row is None:
        raise ValueError(
            f"{owner_type} {owner_id} does not exist."
        )

    return owner_type, str(owner_id)


def get_mortality(
    owner_type,
    owner_id,
):
    owner_type, owner_id = _require_entity(
        owner_type,
        owner_id,
    )

    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM entity_mortality
        WHERE owner_type = ?
          AND owner_id = ?
        """,
        (
            owner_type,
            owner_id,
        ),
    ).fetchone()

    conn.close()

    if row is None:
        return {
            "owner_type": owner_type,
            "owner_id": owner_id,
            "status": "living",
            "death_datetime": None,
            "cause_of_death": None,
            "manner_of_death": None,
            "world_event_id": None,
            "notes": None,
        }

    return row


def is_alive(
    owner_type,
    owner_id,
):
    return (
        get_mortality(
            owner_type,
            owner_id,
        )["status"]
        == "living"
    )


def _record_death_with_connection(
    conn,
    owner_type,
    owner_id,
    *,
    death_datetime=None,
    cause_of_death=None,
    manner_of_death=None,
    world_event_id=None,
    notes=None,
):
    owner_type, owner_id = _require_entity(
        owner_type,
        owner_id,
        conn=conn,
    )

    current = conn.execute(
        """
        SELECT *
        FROM entity_mortality
        WHERE owner_type = ?
          AND owner_id = ?
        """,
        (
            owner_type,
            owner_id,
        ),
    ).fetchone()

    if (
        current is not None
        and current["status"] == "deceased"
    ):
        raise ValueError(
            f"{owner_type} {owner_id} is already deceased."
        )

    if death_datetime is None:
        death_datetime = (
            get_campaign_datetime()
            .strftime("%Y-%m-%d %H:%M:%S")
        )
    elif hasattr(
        death_datetime,
        "strftime",
    ):
        death_datetime = (
            death_datetime
            .strftime("%Y-%m-%d %H:%M:%S")
        )
    else:
        death_datetime = str(
            death_datetime
        ).strip()

    conn.execute(
        """
        INSERT INTO entity_mortality (
            owner_type,
            owner_id,
            status,
            death_datetime,
            cause_of_death,
            manner_of_death,
            world_event_id,
            notes
        )
        VALUES (
            ?,
            ?,
            'deceased',
            ?,
            ?,
            ?,
            ?,
            ?
        )
        ON CONFLICT(owner_type, owner_id)
        DO UPDATE SET
            status = 'deceased',
            death_datetime = excluded.death_datetime,
            cause_of_death = excluded.cause_of_death,
            manner_of_death = excluded.manner_of_death,
            world_event_id = excluded.world_event_id,
            notes = excluded.notes,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            owner_type,
            owner_id,
            death_datetime,
            cause_of_death,
            manner_of_death,
            world_event_id,
            notes,
        ),
    )

    # Death does not remove the body from its physical location.
    # It does, however, prevent the deceased participant from
    # remaining marked conscious in any currently recorded scene.
    conn.execute(
        """
        UPDATE scene_participants
        SET conscious = 0
        WHERE participant_type = ?
          AND participant_id = ?
          AND present = 1
        """,
        (
            owner_type,
            owner_id,
        ),
    )

    return {
        "owner_type": owner_type,
        "owner_id": owner_id,
        "status": "deceased",
        "death_datetime": death_datetime,
        "cause_of_death": cause_of_death,
        "manner_of_death": manner_of_death,
        "world_event_id": world_event_id,
        "notes": notes,
    }


def record_death(
    owner_type,
    owner_id,
    *,
    death_datetime=None,
    cause_of_death=None,
    manner_of_death=None,
    world_event_id=None,
    notes=None,
):
    conn = get_connection()

    try:
        result = _record_death_with_connection(
            conn,
            owner_type,
            owner_id,
            death_datetime=death_datetime,
            cause_of_death=cause_of_death,
            manner_of_death=manner_of_death,
            world_event_id=world_event_id,
            notes=notes,
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return result
