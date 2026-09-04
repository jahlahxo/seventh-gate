from database import get_connection


# ============================================================
# LOCATIONS
# ============================================================

def create_location(
    name,
    description=None,
    parent_location_id=None,
    private_notes=None,
):
    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO locations (
            name,
            parent_location_id,
            description,
            private_notes
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            name,
            parent_location_id,
            description,
            private_notes,
        ),
    )

    location_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return location_id


def get_location(location_id):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM locations
        WHERE id = ?
        """,
        (location_id,),
    ).fetchone()

    conn.close()

    return row


def get_location_by_name(name):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM locations
        WHERE LOWER(name) = LOWER(?)
          AND active = 1
        """,
        (name,),
    ).fetchone()

    conn.close()

    return row


# ============================================================
# DISCORD CHANNEL <-> LOCATION
# ============================================================

def map_channel_to_location(
    location_id,
    discord_channel_id,
    private_location=False,
):
    conn = get_connection()

    conn.execute(
        """
        INSERT INTO location_channels (
            location_id,
            discord_channel_id,
            private_location
        )
        VALUES (?, ?, ?)
        ON CONFLICT(location_id)
        DO UPDATE SET
            discord_channel_id = excluded.discord_channel_id,
            private_location = excluded.private_location
        """,
        (
            location_id,
            str(discord_channel_id),
            int(private_location),
        ),
    )

    conn.commit()
    conn.close()


def get_location_for_channel(discord_channel_id):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT locations.*
        FROM locations
        JOIN location_channels
          ON location_channels.location_id = locations.id
        WHERE location_channels.discord_channel_id = ?
          AND locations.active = 1
        """,
        (str(discord_channel_id),),
    ).fetchone()

    conn.close()

    return row


def get_channel_for_location(location_id):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM location_channels
        WHERE location_id = ?
        """,
        (location_id,),
    ).fetchone()

    conn.close()

    return row


# ============================================================
# LOCATION CONNECTIONS
# ============================================================

def connect_locations(
    from_location_id,
    to_location_id,
    connection_type="passage",
    travel_difficulty=0,
    visible_between=False,
    audible_between=False,
    locked=False,
    restricted=False,
    notes=None,
    bidirectional=True,
):
    conn = get_connection()

    def insert_connection(a, b):
        conn.execute(
            """
            INSERT INTO location_connections (
                from_location_id,
                to_location_id,
                connection_type,
                travel_difficulty,
                visible_between,
                audible_between,
                locked,
                restricted,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(from_location_id, to_location_id)
            DO UPDATE SET
                connection_type = excluded.connection_type,
                travel_difficulty = excluded.travel_difficulty,
                visible_between = excluded.visible_between,
                audible_between = excluded.audible_between,
                locked = excluded.locked,
                restricted = excluded.restricted,
                notes = excluded.notes
            """,
            (
                a,
                b,
                connection_type,
                travel_difficulty,
                int(visible_between),
                int(audible_between),
                int(locked),
                int(restricted),
                notes,
            ),
        )

    insert_connection(
        from_location_id,
        to_location_id,
    )

    if bidirectional:
        insert_connection(
            to_location_id,
            from_location_id,
        )

    conn.commit()
    conn.close()


def get_connection_between(
    from_location_id,
    to_location_id,
):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM location_connections
        WHERE from_location_id = ?
          AND to_location_id = ?
        """,
        (
            from_location_id,
            to_location_id,
        ),
    ).fetchone()

    conn.close()

    return row


# ============================================================
# CURRENT PHYSICAL LOCATION
# ============================================================

def get_participant_location(
    participant_type,
    participant_id,
):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            participant_locations.*,
            locations.name AS location_name
        FROM participant_locations
        JOIN locations
          ON locations.id = participant_locations.location_id
        WHERE participant_type = ?
          AND participant_id = ?
        """,
        (
            participant_type,
            str(participant_id),
        ),
    ).fetchone()

    conn.close()

    return row


def set_participant_location(
    participant_type,
    participant_id,
    location_id,
):
    conn = get_connection()

    conn.execute(
        """
        INSERT INTO participant_locations (
            participant_type,
            participant_id,
            location_id
        )
        VALUES (?, ?, ?)
        ON CONFLICT(participant_type, participant_id)
        DO UPDATE SET
            location_id = excluded.location_id,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            participant_type,
            str(participant_id),
            location_id,
        ),
    )

    conn.commit()
    conn.close()


# ============================================================
# SCENES
# ============================================================

def get_active_scene_for_location(location_id):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM scenes
        WHERE location_id = ?
          AND status = 'active'
        ORDER BY id DESC
        LIMIT 1
        """,
        (location_id,),
    ).fetchone()

    conn.close()

    return row


def get_or_create_scene(location_id):
    existing = get_active_scene_for_location(
        location_id
    )

    if existing:
        return existing["id"]

    channel = get_channel_for_location(location_id)

    if not channel:
        raise ValueError(
            "Location has no Discord channel mapped to it."
        )

    location = get_location(location_id)

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO scenes (
            discord_channel_id,
            title,
            location_id
        )
        VALUES (?, ?, ?)
        """,
        (
            channel["discord_channel_id"],
            location["name"],
            location_id,
        ),
    )

    scene_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return scene_id


# ============================================================
# AUTHORITATIVE WORLD EVENTS
# ============================================================

def record_world_event(
    event_type,
    content,
    source_type,
    source_id=None,
    scene_id=None,
    location_id=None,
    actor_type=None,
    actor_id=None,
    target_type=None,
    target_id=None,
    outcome=None,
    authority=100,
):
    """Record authoritative reality first.

    Semantic embeddings are deliberately NOT generated here. If the
    embedding model is unavailable, slow, or fails, the event must still
    exist in the authoritative ledger. A separate indexing step can attach
    an embedding later.
    """
    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO world_events (
            scene_id,
            location_id,
            event_type,
            actor_type,
            actor_id,
            target_type,
            target_id,
            content,
            outcome,
            source_type,
            source_id,
            authority,
            embedding
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            scene_id,
            location_id,
            event_type,
            actor_type,
            str(actor_id) if actor_id is not None else None,
            target_type,
            str(target_id) if target_id is not None else None,
            content,
            outcome,
            source_type,
            str(source_id) if source_id is not None else None,
            authority,
        ),
    )

    event_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return event_id


def get_world_event(world_event_id):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM world_events
        WHERE id = ?
        """,
        (world_event_id,),
    ).fetchone()

    conn.close()
    return row


def set_world_event_embedding(world_event_id, embedding_text):
    """Attach a precomputed semantic embedding to an existing event.

    Keeping this as a separate operation makes semantic indexing optional
    and retryable without putting authoritative state at risk.
    """
    conn = get_connection()

    conn.execute(
        """
        UPDATE world_events
        SET embedding = ?
        WHERE id = ?
        """,
        (embedding_text, world_event_id),
    )

    conn.commit()
    conn.close()


# ============================================================
# WITNESSES
# ============================================================

def add_event_witness(
    world_event_id,
    witness_type,
    witness_id,
    perception_type="present",
    certainty=1.0,
):
    conn = get_connection()

    conn.execute(
        """
        INSERT OR IGNORE INTO event_witnesses (
            world_event_id,
            witness_type,
            witness_id,
            perception_type,
            certainty
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            world_event_id,
            witness_type,
            str(witness_id),
            perception_type,
            certainty,
        ),
    )

    conn.commit()
    conn.close()


def get_people_at_location(location_id):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM participant_locations
        WHERE location_id = ?
        """,
        (location_id,),
    ).fetchall()

    conn.close()

    return rows


def record_present_witnesses(
    world_event_id,
    location_id,
):
    people = get_people_at_location(location_id)

    for person in people:
        add_event_witness(
            world_event_id=world_event_id,
            witness_type=person["participant_type"],
            witness_id=person["participant_id"],
            perception_type="present",
            certainty=1.0,
        )


# ============================================================
# MOVEMENT
# ============================================================

def move_participant(
    participant_type,
    participant_id,
    destination_location_id,
    source_type,
    source_id=None,
    force=False,
):
    current = get_participant_location(
        participant_type,
        participant_id,
    )

    destination = get_location(
        destination_location_id
    )

    if not destination:
        raise ValueError(
            "Destination location does not exist."
        )

    # Initial placement is allowed without travel validation.
    if current is None:
        set_participant_location(
            participant_type,
            participant_id,
            destination_location_id,
        )

        scene_id = get_or_create_scene(
            destination_location_id
        )

        event_id = record_world_event(
            event_type="arrival",
            content=(
                f"{participant_type} {participant_id} "
                f"is now at {destination['name']}."
            ),
            source_type=source_type,
            source_id=source_id,
            scene_id=scene_id,
            location_id=destination_location_id,
            actor_type=participant_type,
            actor_id=participant_id,
            outcome="arrived",
        )

        record_present_witnesses(
            event_id,
            destination_location_id,
        )

        return event_id

    old_location_id = current["location_id"]

    if old_location_id == destination_location_id:
        return None

    connection = get_connection_between(
        old_location_id,
        destination_location_id,
    )

    if not force:
        if connection is None:
            raise ValueError(
                "Those locations are not directly connected."
            )

        if connection["locked"]:
            raise PermissionError(
                "The route is locked."
            )

        if connection["restricted"]:
            raise PermissionError(
                "The route is restricted."
            )

    old_location = get_location(old_location_id)

    # Witnesses who were present before departure.
    departure_witnesses = get_people_at_location(
        old_location_id
    )

    # Change objective physical state.
    set_participant_location(
        participant_type,
        participant_id,
        destination_location_id,
    )

    destination_scene_id = get_or_create_scene(
        destination_location_id
    )

    event_text = (
        f"{participant_type} {participant_id} moved from "
        f"{old_location['name']} to {destination['name']}."
    )

    event_id = record_world_event(
        event_type="movement",
        content=event_text,
        source_type=source_type,
        source_id=source_id,
        scene_id=destination_scene_id,
        location_id=destination_location_id,
        actor_type=participant_type,
        actor_id=participant_id,
        outcome="moved",
    )

    # People at the old location witnessed the departure.
    for person in departure_witnesses:
        add_event_witness(
            event_id,
            person["participant_type"],
            person["participant_id"],
            perception_type="departure",
        )

    # People at destination witness arrival.
    for person in get_people_at_location(
        destination_location_id
    ):
        add_event_witness(
            event_id,
            person["participant_type"],
            person["participant_id"],
            perception_type="arrival",
        )

    return event_id