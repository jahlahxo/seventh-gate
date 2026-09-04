from __future__ import annotations

from campaign_clock import get_campaign_datetime
from database import get_connection
from reproduction import get_pregnancy


VALID_ENTITY_TYPES = {
    "character",
    "player_persona",
}

VALID_CERTAINTY = {
    "known",
    "suspected",
    "uncertain",
    "unknown",
}

INVERSE_RELATIONS = {
    "biological_parent": "biological_child",
    "gestational_parent": "gestational_child",
    "adoptive_parent": "adoptive_child",
    "social_parent": "social_child",
    "caregiver": "care_recipient",
    "guardian": "ward",
    "sibling": "sibling",
}


def _validate_entity(entity_type, entity_id):
    entity_type = str(entity_type)

    if entity_type not in VALID_ENTITY_TYPES:
        raise ValueError(
            f"Invalid entity type: {entity_type}"
        )

    table = (
        "characters"
        if entity_type == "character"
        else "player_personas"
    )

    conn = get_connection()

    row = conn.execute(
        f"""
        SELECT id
        FROM {table}
        WHERE id = ?
          AND active = 1
        """,
        (int(entity_id),),
    ).fetchone()

    conn.close()

    if row is None:
        raise ValueError(
            f"{entity_type} {entity_id} does not exist or is inactive."
        )

    return entity_type, str(entity_id)


def _insert_family_link(
    conn,
    *,
    subject_type,
    subject_id,
    relative_type,
    relative_id,
    relation_type,
    certainty,
    source_type,
    source_id=None,
    started_at=None,
    notes=None,
):
    conn.execute(
        """
        INSERT INTO family_links (
            subject_type,
            subject_id,
            relative_type,
            relative_id,
            relation_type,
            certainty,
            source_type,
            source_id,
            active,
            started_at,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(
            subject_type,
            subject_id,
            relative_type,
            relative_id,
            relation_type
        )
        DO UPDATE SET
            certainty = excluded.certainty,
            source_type = excluded.source_type,
            source_id = excluded.source_id,
            active = 1,
            started_at = COALESCE(
                family_links.started_at,
                excluded.started_at
            ),
            ended_at = NULL,
            notes = excluded.notes,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            subject_type,
            str(subject_id),
            relative_type,
            str(relative_id),
            str(relation_type),
            str(certainty),
            str(source_type),
            None if source_id is None else str(source_id),
            started_at,
            notes,
        ),
    )


def add_family_link(
    subject_type,
    subject_id,
    relative_type,
    relative_id,
    relation_type,
    *,
    certainty="known",
    source_type,
    source_id=None,
    started_at=None,
    notes=None,
    create_inverse=True,
):
    subject_type, subject_id = _validate_entity(
        subject_type,
        subject_id,
    )

    relative_type, relative_id = _validate_entity(
        relative_type,
        relative_id,
    )

    certainty = str(certainty).lower().strip()

    if certainty not in VALID_CERTAINTY:
        raise ValueError(
            "Invalid family-link certainty."
        )

    relation_type = str(
        relation_type
    ).lower().strip()

    if not relation_type:
        raise ValueError(
            "relation_type cannot be empty."
        )

    if not str(source_type).strip():
        raise ValueError(
            "source_type is required."
        )

    if started_at is None:
        started_at = get_campaign_datetime().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    conn = get_connection()

    try:
        _insert_family_link(
            conn,
            subject_type=subject_type,
            subject_id=subject_id,
            relative_type=relative_type,
            relative_id=relative_id,
            relation_type=relation_type,
            certainty=certainty,
            source_type=source_type,
            source_id=source_id,
            started_at=started_at,
            notes=notes,
        )

        if create_inverse:
            inverse = INVERSE_RELATIONS.get(
                relation_type
            )

            if inverse is not None:
                _insert_family_link(
                    conn,
                    subject_type=relative_type,
                    subject_id=relative_id,
                    relative_type=subject_type,
                    relative_id=subject_id,
                    relation_type=inverse,
                    certainty=certainty,
                    source_type=source_type,
                    source_id=source_id,
                    started_at=started_at,
                    notes=notes,
                )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return get_family_links(
        subject_type,
        subject_id,
        relation_type=relation_type,
    )[-1]


def get_family_links(
    subject_type,
    subject_id,
    *,
    relation_type=None,
    active_only=True,
):
    subject_type, subject_id = _validate_entity(
        subject_type,
        subject_id,
    )

    sql = """
        SELECT *
        FROM family_links
        WHERE subject_type = ?
          AND subject_id = ?
    """

    params = [
        subject_type,
        subject_id,
    ]

    if relation_type is not None:
        sql += " AND relation_type = ?"
        params.append(
            str(relation_type)
        )

    if active_only:
        sql += " AND active = 1"

    sql += " ORDER BY id"

    conn = get_connection()
    rows = conn.execute(
        sql,
        tuple(params),
    ).fetchall()
    conn.close()

    return rows


def end_family_link(
    subject_type,
    subject_id,
    relative_type,
    relative_id,
    relation_type,
    *,
    end_inverse=True,
):
    subject_type, subject_id = _validate_entity(
        subject_type,
        subject_id,
    )

    relative_type, relative_id = _validate_entity(
        relative_type,
        relative_id,
    )

    relation_type = str(
        relation_type
    ).lower().strip()

    now = get_campaign_datetime().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    conn = get_connection()

    try:
        conn.execute(
            """
            UPDATE family_links
            SET
                active = 0,
                ended_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE subject_type = ?
              AND subject_id = ?
              AND relative_type = ?
              AND relative_id = ?
              AND relation_type = ?
              AND active = 1
            """,
            (
                now,
                subject_type,
                subject_id,
                relative_type,
                relative_id,
                relation_type,
            ),
        )

        if end_inverse:
            inverse = INVERSE_RELATIONS.get(
                relation_type
            )

            if inverse is not None:
                conn.execute(
                    """
                    UPDATE family_links
                    SET
                        active = 0,
                        ended_at = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE subject_type = ?
                      AND subject_id = ?
                      AND relative_type = ?
                      AND relative_id = ?
                      AND relation_type = ?
                      AND active = 1
                    """,
                    (
                        now,
                        relative_type,
                        relative_id,
                        subject_type,
                        subject_id,
                        inverse,
                    ),
                )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def get_birth(birth_id):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM births
        WHERE id = ?
        """,
        (int(birth_id),),
    ).fetchone()

    conn.close()

    if row is None:
        raise ValueError(
            "Birth record does not exist."
        )

    return row


def get_birth_children(birth_id):
    get_birth(birth_id)

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            birth_children.*,
            characters.name AS character_name
        FROM birth_children
        JOIN characters
          ON characters.id = birth_children.child_character_id
        WHERE birth_children.birth_id = ?
        ORDER BY birth_children.birth_order
        """,
        (int(birth_id),),
    ).fetchall()

    conn.close()
    return rows


def get_birth_for_pregnancy(pregnancy_id):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM births
        WHERE pregnancy_id = ?
        """,
        (int(pregnancy_id),),
    ).fetchone()

    conn.close()
    return row


def _unique_unnamed_character_name(
    conn,
    pregnancy_id,
    birth_order,
):
    base = (
        f"__unnamed_child_"
        f"{int(pregnancy_id)}_"
        f"{int(birth_order)}"
    )

    candidate = base
    suffix = 1

    while conn.execute(
        """
        SELECT 1
        FROM characters
        WHERE name = ?
        """,
        (candidate,),
    ).fetchone():
        suffix += 1
        candidate = f"{base}_{suffix}"

    return candidate


def _create_child_character(
    conn,
    *,
    pregnancy_id,
    birth_order,
    given_name=None,
    description=None,
    appearance=None,
    notes=None,
):
    clean_name = (
        None
        if given_name is None
        else str(given_name).strip()
    )

    if clean_name == "":
        clean_name = None

    internal_name = (
        clean_name
        if clean_name is not None
        else _unique_unnamed_character_name(
            conn,
            pregnancy_id,
            birth_order,
        )
    )

    cursor = conn.execute(
        """
        INSERT INTO characters (
            name,
            description,
            appearance,
            private_character_notes
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            internal_name,
            description,
            appearance,
            notes,
        ),
    )

    return cursor.lastrowid, clean_name


def create_birth(
    pregnancy_id,
    children,
    *,
    world_event_id=None,
    location_id=None,
    notes=None,
    derive_biological_parentage=True,
):
    """
    Conclude an ongoing pregnancy with one or more persistent
    child characters.

    Each child entry is a dict. Supported keys:
        name
        description
        appearance
        notes

    The gestational-parent relationship is always objective.
    Biological-parent relationships are derived automatically
    only when the pregnancy origin is explicitly 'biological'.
    """
    pregnancy = get_pregnancy(
        pregnancy_id
    )

    if pregnancy["status"] != "ongoing":
        raise ValueError(
            "Pregnancy is not ongoing."
        )

    if get_birth_for_pregnancy(
        pregnancy_id
    ) is not None:
        raise ValueError(
            "This pregnancy already has a birth record."
        )

    children = list(children)

    if not children:
        raise ValueError(
            "A birth requires at least one child entry."
        )

    now = get_campaign_datetime()
    now_text = now.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    birth_date = now.date().isoformat()

    conn = get_connection()

    try:
        birth_cursor = conn.execute(
            """
            INSERT INTO births (
                pregnancy_id,
                world_event_id,
                location_id,
                birth_datetime,
                notes
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(pregnancy_id),
                world_event_id,
                location_id,
                now_text,
                notes,
            ),
        )

        birth_id = birth_cursor.lastrowid

        created_children = []

        for index, child in enumerate(
            children,
            start=1,
        ):
            if not isinstance(child, dict):
                raise ValueError(
                    "Each child entry must be a dictionary."
                )

            child_id, given_name = _create_child_character(
                conn,
                pregnancy_id=pregnancy_id,
                birth_order=index,
                given_name=child.get("name"),
                description=child.get(
                    "description"
                ),
                appearance=child.get(
                    "appearance"
                ),
                notes=child.get("notes"),
            )

            conn.execute(
                """
                INSERT INTO entity_life_profiles (
                    owner_type,
                    owner_id,
                    birth_date,
                    notes
                )
                VALUES (
                    'character',
                    ?,
                    ?,
                    ?
                )
                """,
                (
                    str(child_id),
                    birth_date,
                    "Born in-story.",
                ),
            )

            conn.execute(
                """
                INSERT INTO birth_children (
                    birth_id,
                    child_character_id,
                    birth_order,
                    given_name,
                    outcome,
                    notes
                )
                VALUES (?, ?, ?, ?, 'live_birth', ?)
                """,
                (
                    birth_id,
                    child_id,
                    index,
                    given_name,
                    child.get("notes"),
                ),
            )

            # Gestational parent is always objective.
            _insert_family_link(
                conn,
                subject_type="character",
                subject_id=child_id,
                relative_type=pregnancy[
                    "gestational_parent_type"
                ],
                relative_id=pregnancy[
                    "gestational_parent_id"
                ],
                relation_type="gestational_parent",
                certainty="known",
                source_type="birth",
                source_id=birth_id,
                started_at=now_text,
            )

            _insert_family_link(
                conn,
                subject_type=pregnancy[
                    "gestational_parent_type"
                ],
                subject_id=pregnancy[
                    "gestational_parent_id"
                ],
                relative_type="character",
                relative_id=child_id,
                relation_type="gestational_child",
                certainty="known",
                source_type="birth",
                source_id=birth_id,
                started_at=now_text,
            )

            if (
                derive_biological_parentage
                and pregnancy["origin_type"]
                == "biological"
            ):
                for parent_type, parent_id in (
                    (
                        pregnancy[
                            "gestational_parent_type"
                        ],
                        pregnancy[
                            "gestational_parent_id"
                        ],
                    ),
                    (
                        pregnancy[
                            "other_parent_type"
                        ],
                        pregnancy[
                            "other_parent_id"
                        ],
                    ),
                ):
                    if (
                        parent_type is None
                        or parent_id is None
                    ):
                        continue

                    _insert_family_link(
                        conn,
                        subject_type="character",
                        subject_id=child_id,
                        relative_type=parent_type,
                        relative_id=parent_id,
                        relation_type="biological_parent",
                        certainty="known",
                        source_type="birth",
                        source_id=birth_id,
                        started_at=now_text,
                    )

                    _insert_family_link(
                        conn,
                        subject_type=parent_type,
                        subject_id=parent_id,
                        relative_type="character",
                        relative_id=child_id,
                        relation_type="biological_child",
                        certainty="known",
                        source_type="birth",
                        source_id=birth_id,
                        started_at=now_text,
                    )

            created_children.append(
                child_id
            )

        # Sibling links among multiples.
        for i, child_id in enumerate(
            created_children
        ):
            for sibling_id in created_children[
                i + 1:
            ]:
                _insert_family_link(
                    conn,
                    subject_type="character",
                    subject_id=child_id,
                    relative_type="character",
                    relative_id=sibling_id,
                    relation_type="sibling",
                    certainty="known",
                    source_type="birth",
                    source_id=birth_id,
                    started_at=now_text,
                )

                _insert_family_link(
                    conn,
                    subject_type="character",
                    subject_id=sibling_id,
                    relative_type="character",
                    relative_id=child_id,
                    relation_type="sibling",
                    certainty="known",
                    source_type="birth",
                    source_id=birth_id,
                    started_at=now_text,
                )

        age_days = int(
            (
                now
                - __import__("datetime").datetime.strptime(
                    pregnancy["conceived_at"],
                    "%Y-%m-%d %H:%M:%S",
                )
            ).days
        )

        conn.execute(
            """
            UPDATE pregnancies
            SET
                status = 'ended',
                ended_at = ?,
                outcome = 'birth'
            WHERE id = ?
            """,
            (
                now_text,
                int(pregnancy_id),
            ),
        )

        conn.execute(
            """
            INSERT INTO pregnancy_events (
                pregnancy_id,
                world_event_id,
                event_type,
                gestational_age_days,
                description
            )
            VALUES (?, ?, 'birth', ?, ?)
            """,
            (
                int(pregnancy_id),
                world_event_id,
                max(0, age_days),
                notes,
            ),
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return {
        "birth": get_birth(
            birth_id
        ),
        "children": get_birth_children(
            birth_id
        ),
    }


def name_child(
    child_character_id,
    given_name,
):
    child_character_id = int(
        child_character_id
    )

    given_name = str(
        given_name
    ).strip()

    if not given_name:
        raise ValueError(
            "A child name cannot be empty."
        )

    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM birth_children
        WHERE child_character_id = ?
        """,
        (child_character_id,),
    ).fetchone()

    if row is None:
        conn.close()
        raise ValueError(
            "Character is not recorded as a born child."
        )

    try:
        conn.execute(
            """
            UPDATE characters
            SET
                name = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                given_name,
                child_character_id,
            ),
        )

        conn.execute(
            """
            UPDATE birth_children
            SET given_name = ?
            WHERE child_character_id = ?
            """,
            (
                given_name,
                child_character_id,
            ),
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

    return given_name
