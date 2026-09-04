from database import get_connection


VALID_HOLDER_TYPES = {
    "location",
    "character",
    "player_persona",
    "object",
}

VALID_RELATIONS = {
    "at",
    "carried",
    "held",
    "worn",
    "inside",
    "on",
}


def _require_object(object_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT *
        FROM objects
        WHERE id = ?
          AND active = 1
        """,
        (int(object_id),),
    ).fetchone()
    conn.close()

    if row is None:
        raise ValueError(f"Object {object_id} does not exist or is inactive.")

    return row


def get_object(object_id):
    return _require_object(object_id)


def create_object(
    name,
    object_type="item",
    description=None,
    portable=True,
    is_container=False,
    is_openable=False,
    is_lockable=False,
    initial_holder_type=None,
    initial_holder_id=None,
    initial_relation="at",
    starts_open=None,
    starts_locked=None,
    condition_name="intact",
    condition_level=0,
    lock_code=None,
    notes=None,
):
    name = str(name).strip()

    if not name:
        raise ValueError("Object name cannot be empty.")

    if is_lockable and not is_openable:
        raise ValueError("A lockable object must also be openable.")

    if starts_locked and not is_lockable:
        raise ValueError("A non-lockable object cannot start locked.")

    if starts_open is not None and not is_openable:
        raise ValueError("A non-openable object cannot have an open/closed state.")

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO objects (
            name,
            object_type,
            description,
            portable,
            is_container,
            is_openable,
            is_lockable
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            str(object_type),
            description,
            int(bool(portable)),
            int(bool(is_container)),
            int(bool(is_openable)),
            int(bool(is_lockable)),
        ),
    )

    object_id = cursor.lastrowid

    conn.execute(
        """
        INSERT INTO object_states (
            object_id,
            is_open,
            is_locked,
            condition_name,
            condition_level,
            lock_code,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            object_id,
            None if starts_open is None else int(bool(starts_open)),
            None if starts_locked is None else int(bool(starts_locked)),
            str(condition_name),
            int(condition_level),
            lock_code,
            notes,
        ),
    )

    conn.commit()
    conn.close()

    if initial_holder_type is not None:
        place_object(
            object_id=object_id,
            holder_type=initial_holder_type,
            holder_id=initial_holder_id,
            relation=initial_relation,
        )

    return object_id


def get_object_state(object_id):
    _require_object(object_id)

    conn = get_connection()
    row = conn.execute(
        """
        SELECT *
        FROM object_states
        WHERE object_id = ?
        """,
        (int(object_id),),
    ).fetchone()
    conn.close()

    return row


def get_object_placement(object_id):
    _require_object(object_id)

    conn = get_connection()
    row = conn.execute(
        """
        SELECT *
        FROM object_placements
        WHERE object_id = ?
        """,
        (int(object_id),),
    ).fetchone()
    conn.close()

    return row


def _validate_holder(holder_type, holder_id):
    holder_type = str(holder_type)

    if holder_type not in VALID_HOLDER_TYPES:
        raise ValueError(
            f"Invalid holder type: {holder_type}. "
            f"Expected one of: {sorted(VALID_HOLDER_TYPES)}"
        )

    if holder_id is None:
        raise ValueError("holder_id is required.")

    holder_id = str(holder_id)

    conn = get_connection()

    if holder_type == "location":
        row = conn.execute(
            """
            SELECT id
            FROM locations
            WHERE id = ?
              AND active = 1
            """,
            (int(holder_id),),
        ).fetchone()

    elif holder_type == "character":
        row = conn.execute(
            """
            SELECT id
            FROM characters
            WHERE id = ?
              AND active = 1
            """,
            (int(holder_id),),
        ).fetchone()

    elif holder_type == "player_persona":
        row = conn.execute(
            """
            SELECT id
            FROM player_personas
            WHERE id = ?
              AND active = 1
            """,
            (int(holder_id),),
        ).fetchone()

    else:
        row = conn.execute(
            """
            SELECT id
            FROM objects
            WHERE id = ?
              AND active = 1
            """,
            (int(holder_id),),
        ).fetchone()

    conn.close()

    if row is None:
        raise ValueError(
            f"Holder {holder_type} {holder_id} does not exist or is inactive."
        )


def _container_chain_contains(candidate_container_id, searched_object_id):
    current_id = int(candidate_container_id)
    searched_object_id = int(searched_object_id)
    visited = set()

    while current_id not in visited:
        visited.add(current_id)

        if current_id == searched_object_id:
            return True

        conn = get_connection()
        placement = conn.execute(
            """
            SELECT holder_type, holder_id
            FROM object_placements
            WHERE object_id = ?
            """,
            (current_id,),
        ).fetchone()
        conn.close()

        if placement is None or placement["holder_type"] != "object":
            return False

        current_id = int(placement["holder_id"])

    raise ValueError("Existing object placement cycle detected.")


def place_object(
    object_id,
    holder_type,
    holder_id,
    relation="at",
):
    obj = _require_object(object_id)

    holder_type = str(holder_type)
    holder_id = str(holder_id)
    relation = str(relation)

    if relation not in VALID_RELATIONS:
        raise ValueError(
            f"Invalid placement relation: {relation}. "
            f"Expected one of: {sorted(VALID_RELATIONS)}"
        )

    _validate_holder(holder_type, holder_id)

    if holder_type in {"character", "player_persona"} and not obj["portable"]:
        raise ValueError("A non-portable object cannot be placed in an inventory.")

    if holder_type == "object":
        container = _require_object(holder_id)

        if int(holder_id) == int(object_id):
            raise ValueError("An object cannot contain or hold itself.")

        if not container["is_container"]:
            raise ValueError("The destination object is not a container.")

        if relation not in {"inside", "on"}:
            raise ValueError(
                "An object placed on/in another object must use relation 'inside' or 'on'."
            )

        if _container_chain_contains(holder_id, object_id):
            raise ValueError("This placement would create a container cycle.")

        state = get_object_state(holder_id)

        if relation == "inside" and container["is_openable"]:
            if state is not None and state["is_open"] == 0:
                raise PermissionError("The container is closed.")

    if holder_type == "location" and relation not in {"at", "on"}:
        raise ValueError("Objects at locations must use relation 'at' or 'on'.")

    if holder_type in {"character", "player_persona"} and relation not in {
        "carried",
        "held",
        "worn",
    }:
        raise ValueError(
            "Objects possessed by a character/persona must be carried, held, or worn."
        )

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO object_placements (
            object_id,
            holder_type,
            holder_id,
            relation
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(object_id)
        DO UPDATE SET
            holder_type = excluded.holder_type,
            holder_id = excluded.holder_id,
            relation = excluded.relation,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            int(object_id),
            holder_type,
            holder_id,
            relation,
        ),
    )

    conn.commit()
    conn.close()

    return get_object_placement(object_id)


def remove_object_placement(object_id):
    _require_object(object_id)

    conn = get_connection()
    conn.execute(
        """
        DELETE FROM object_placements
        WHERE object_id = ?
        """,
        (int(object_id),),
    )
    conn.commit()
    conn.close()


def get_objects_held_by(
    holder_type,
    holder_id,
    relation=None,
):
    _validate_holder(holder_type, holder_id)

    conn = get_connection()

    if relation is None:
        rows = conn.execute(
            """
            SELECT
                objects.*,
                object_placements.relation
            FROM object_placements
            JOIN objects
              ON objects.id = object_placements.object_id
            WHERE object_placements.holder_type = ?
              AND object_placements.holder_id = ?
              AND objects.active = 1
            ORDER BY objects.id
            """,
            (
                str(holder_type),
                str(holder_id),
            ),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT
                objects.*,
                object_placements.relation
            FROM object_placements
            JOIN objects
              ON objects.id = object_placements.object_id
            WHERE object_placements.holder_type = ?
              AND object_placements.holder_id = ?
              AND object_placements.relation = ?
              AND objects.active = 1
            ORDER BY objects.id
            """,
            (
                str(holder_type),
                str(holder_id),
                str(relation),
            ),
        ).fetchall()

    conn.close()
    return rows


def get_inventory(owner_type, owner_id):
    if owner_type not in {"character", "player_persona"}:
        raise ValueError("Inventory owner must be a character or player_persona.")

    return get_objects_held_by(owner_type, owner_id)


def set_object_open(object_id, is_open):
    obj = _require_object(object_id)

    if not obj["is_openable"]:
        raise ValueError("This object cannot be opened or closed.")

    state = get_object_state(object_id)

    if bool(is_open) and state is not None and state["is_locked"] == 1:
        raise PermissionError("The object is locked.")

    conn = get_connection()
    conn.execute(
        """
        UPDATE object_states
        SET
            is_open = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE object_id = ?
        """,
        (
            int(bool(is_open)),
            int(object_id),
        ),
    )
    conn.commit()
    conn.close()

    return get_object_state(object_id)


def set_object_locked(object_id, is_locked):
    obj = _require_object(object_id)

    if not obj["is_lockable"]:
        raise ValueError("This object cannot be locked or unlocked.")

    state = get_object_state(object_id)

    if bool(is_locked) and state is not None and state["is_open"] == 1:
        raise ValueError("An open object cannot be locked.")

    conn = get_connection()
    conn.execute(
        """
        UPDATE object_states
        SET
            is_locked = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE object_id = ?
        """,
        (
            int(bool(is_locked)),
            int(object_id),
        ),
    )
    conn.commit()
    conn.close()

    return get_object_state(object_id)


def set_object_condition(
    object_id,
    condition_name,
    condition_level=0,
    notes=None,
):
    _require_object(object_id)

    condition_name = str(condition_name).strip()

    if not condition_name:
        raise ValueError("condition_name cannot be empty.")

    condition_level = int(condition_level)

    if condition_level < 0:
        raise ValueError("condition_level cannot be negative.")

    conn = get_connection()
    conn.execute(
        """
        UPDATE object_states
        SET
            condition_name = ?,
            condition_level = ?,
            notes = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE object_id = ?
        """,
        (
            condition_name,
            condition_level,
            notes,
            int(object_id),
        ),
    )
    conn.commit()
    conn.close()

    return get_object_state(object_id)


def add_condition(
    owner_type,
    owner_id,
    condition_type,
    name,
    severity=1,
    description=None,
    source_world_event_id=None,
):
    owner_type = str(owner_type)

    if owner_type not in {"character", "player_persona"}:
        raise ValueError("Condition owner must be a character or player_persona.")

    _validate_holder(owner_type, owner_id)

    condition_type = str(condition_type).strip()
    name = str(name).strip()
    severity = int(severity)

    if not condition_type:
        raise ValueError("condition_type cannot be empty.")

    if not name:
        raise ValueError("Condition name cannot be empty.")

    if severity < 0:
        raise ValueError("Severity cannot be negative.")

    if source_world_event_id is not None:
        conn = get_connection()
        event = conn.execute(
            """
            SELECT id
            FROM world_events
            WHERE id = ?
            """,
            (int(source_world_event_id),),
        ).fetchone()
        conn.close()

        if event is None:
            raise ValueError("source_world_event_id does not exist.")

    conn = get_connection()
    cursor = conn.execute(
        """
        INSERT INTO entity_conditions (
            owner_type,
            owner_id,
            condition_type,
            name,
            severity,
            description,
            source_world_event_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_type,
            str(owner_id),
            condition_type,
            name,
            severity,
            description,
            source_world_event_id,
        ),
    )
    condition_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return condition_id


def get_active_conditions(owner_type, owner_id):
    _validate_holder(owner_type, owner_id)

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM entity_conditions
        WHERE owner_type = ?
          AND owner_id = ?
          AND active = 1
        ORDER BY id
        """,
        (
            str(owner_type),
            str(owner_id),
        ),
    ).fetchall()
    conn.close()

    return rows


def update_condition(
    condition_id,
    severity=None,
    description=None,
):
    conn = get_connection()

    current = conn.execute(
        """
        SELECT *
        FROM entity_conditions
        WHERE id = ?
        """,
        (int(condition_id),),
    ).fetchone()

    if current is None:
        conn.close()
        raise ValueError("Condition does not exist.")

    new_severity = current["severity"] if severity is None else int(severity)
    new_description = (
        current["description"] if description is None else description
    )

    if new_severity < 0:
        conn.close()
        raise ValueError("Severity cannot be negative.")

    conn.execute(
        """
        UPDATE entity_conditions
        SET
            severity = ?,
            description = ?
        WHERE id = ?
        """,
        (
            new_severity,
            new_description,
            int(condition_id),
        ),
    )

    conn.commit()
    conn.close()

    return condition_id


def end_condition(condition_id):
    conn = get_connection()

    current = conn.execute(
        """
        SELECT id
        FROM entity_conditions
        WHERE id = ?
        """,
        (int(condition_id),),
    ).fetchone()

    if current is None:
        conn.close()
        raise ValueError("Condition does not exist.")

    conn.execute(
        """
        UPDATE entity_conditions
        SET
            active = 0,
            ended_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (int(condition_id),),
    )

    conn.commit()
    conn.close()


def deactivate_object(object_id):
    _require_object(object_id)

    conn = get_connection()

    child = conn.execute(
        """
        SELECT object_id
        FROM object_placements
        WHERE holder_type = 'object'
          AND holder_id = ?
        LIMIT 1
        """,
        (str(object_id),),
    ).fetchone()

    if child is not None:
        conn.close()
        raise ValueError(
            "Cannot deactivate a container while active objects are placed in/on it."
        )

    conn.execute(
        """
        UPDATE objects
        SET
            active = 0,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (int(object_id),),
    )

    conn.execute(
        """
        DELETE FROM object_placements
        WHERE object_id = ?
        """,
        (int(object_id),),
    )

    conn.commit()
    conn.close()
