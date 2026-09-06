from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from actions import EntityRef, make_entity
from campaign_clock import get_campaign_datetime
from database import get_connection
from entities import (
    get_object_state,
    get_objects_held_by,
)
from world import (
    get_location,
    get_participant_location,
    get_people_at_location,
    get_world_event,
)


# ============================================================
# TRUSTED SCENE REFRESH
#
# Rebuilds a fresh objective scene packet from authoritative Engine /
# database state AFTER execution.
#
# Governing rule:
#
#   Models may describe the world.
#   Only Engine state determines what is actually in the refreshed scene.
#
# This module deliberately whitelists fields. It does NOT expose:
# - location.private_notes
# - character personality / private_character_notes
# - object lock codes / notes
# - memories / beliefs / hidden family or reproductive state
# - raw Discord history
#
# It also returns the trusted entity whitelist that may later be supplied
# to action_interpreter.py. Those references come from Engine state, never
# from Director or Character Brain output.
# ============================================================


@dataclass(frozen=True)
class SceneRefreshResult:
    character_id: int
    location_id: int
    objective_scene: dict
    permitted_entities: tuple[EntityRef, ...]
    source_world_event_id: Optional[int] = None


def _clean_text(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def _public_location(location):
    return {
        "entity_type": "location",
        "entity_id": str(location["id"]),
        "name": location["name"],
        "description": _clean_text(
            location["description"]
        ),
    }


def _participant_public_identity(
    participant_type,
    participant_id,
):
    participant_type = str(participant_type)
    participant_id = str(participant_id)

    conn = get_connection()

    if participant_type == "character":
        row = conn.execute(
            """
            SELECT id, name, appearance
            FROM characters
            WHERE id = ?
              AND active = 1
            """,
            (int(participant_id),),
        ).fetchone()

        conn.close()

        if row is None:
            return None

        return {
            "entity_type": "character",
            "entity_id": str(row["id"]),
            "name": row["name"],
            "appearance": _clean_text(
                row["appearance"]
            ),
        }

    if participant_type == "player_persona":
        row = conn.execute(
            """
            SELECT
                id,
                rp_name,
                discord_name,
                appearance
            FROM player_personas
            WHERE id = ?
              AND active = 1
            """,
            (int(participant_id),),
        ).fetchone()

        conn.close()

        if row is None:
            return None

        name = (
            _clean_text(row["rp_name"])
            or _clean_text(row["discord_name"])
            or f"player_persona {row['id']}"
        )

        return {
            "entity_type": "player_persona",
            "entity_id": str(row["id"]),
            "name": name,
            "appearance": _clean_text(
                row["appearance"]
            ),
        }

    conn.close()
    return None


def _public_people_at_location(
    location_id,
    *,
    exclude_character_id=None,
):
    people = []

    for row in get_people_at_location(
        location_id
    ):
        if (
            exclude_character_id is not None
            and row["participant_type"]
            == "character"
            and str(row["participant_id"])
            == str(exclude_character_id)
        ):
            continue

        public = _participant_public_identity(
            row["participant_type"],
            row["participant_id"],
        )

        if public is not None:
            people.append(public)

    return people


def _public_object(object_row):
    state = get_object_state(
        object_row["id"]
    )

    public = {
        "entity_type": "object",
        "entity_id": str(
            object_row["id"]
        ),
        "name": object_row["name"],
        "object_type":
            object_row["object_type"],
        "description": _clean_text(
            object_row["description"]
        ),
        "relation":
            object_row["relation"],
    }

    if state is not None:
        if state["is_open"] is not None:
            public["is_open"] = bool(
                state["is_open"]
            )

        if state["condition_name"] is not None:
            public["condition"] = str(
                state["condition_name"]
            )

    return public


def _public_objects_at_location(
    location_id,
):
    return [
        _public_object(row)
        for row in get_objects_held_by(
            "location",
            location_id,
        )
    ]


def _connected_exits(location_id):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            location_connections.to_location_id,
            location_connections.connection_type,
            locations.name AS destination_name
        FROM location_connections
        JOIN locations
          ON locations.id =
             location_connections.to_location_id
        WHERE location_connections.from_location_id = ?
          AND locations.active = 1
        ORDER BY location_connections.to_location_id
        """,
        (int(location_id),),
    ).fetchall()

    conn.close()

    return [
        {
            "entity_type": "location",
            "entity_id": str(
                row["to_location_id"]
            ),
            "name":
                row["destination_name"],
            "connection_type":
                row["connection_type"],
        }
        for row in rows
    ]


def _character_witnessed_event(
    character_id,
    world_event_id,
):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT 1
        FROM event_witnesses
        WHERE world_event_id = ?
          AND witness_type = 'character'
          AND witness_id = ?
        LIMIT 1
        """,
        (
            int(world_event_id),
            str(character_id),
        ),
    ).fetchone()

    conn.close()

    return row is not None


def _recent_event_for_character(
    character_id,
    current_location_id,
    world_event_id,
):
    if world_event_id is None:
        return None

    event = get_world_event(
        int(world_event_id)
    )

    if event is None:
        return None

    actor_is_character = (
        event["actor_type"] == "character"
        and str(event["actor_id"])
        == str(character_id)
    )

    same_location = (
        event["location_id"] is not None
        and int(event["location_id"])
        == int(current_location_id)
    )

    witnessed = _character_witnessed_event(
        character_id,
        world_event_id,
    )

    if not (
        actor_is_character
        or same_location
        or witnessed
    ):
        return None

    return {
        "world_event_id":
            int(event["id"]),
        "event_type":
            event["event_type"],
        "content":
            event["content"],
        "outcome":
            event["outcome"],
        "actor_type":
            event["actor_type"],
        "actor_id":
            event["actor_id"],
        "target_type":
            event["target_type"],
        "target_id":
            event["target_id"],
    }


def _execution_world_event_id(
    execution,
):
    if execution is None:
        return None

    if isinstance(execution, dict):
        value = execution.get(
            "world_event_id"
        )
    else:
        value = getattr(
            execution,
            "world_event_id",
            None,
        )

    if value is None:
        return None

    return int(value)


def _execution_summary(execution):
    if execution is None:
        return None

    if isinstance(execution, dict):
        executed = bool(
            execution.get("executed")
        )
        description = _clean_text(
            execution.get("description")
        )
        reason = _clean_text(
            execution.get("reason")
        )
    else:
        executed = bool(
            getattr(
                execution,
                "executed",
                False,
            )
        )
        description = _clean_text(
            getattr(
                execution,
                "description",
                None,
            )
        )
        reason = _clean_text(
            getattr(
                execution,
                "reason",
                None,
            )
        )

    return {
        "executed": executed,
        "description": description,
        "reason": reason,
    }


def _dedupe_entity_refs(refs):
    seen = set()
    result = []

    for ref in refs:
        key = (
            ref.entity_type,
            ref.entity_id,
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(ref)

    return tuple(result)


def build_scene_refresh(
    character_id,
    *,
    execution: Optional[Any] = None,
):
    """
    Rebuild one character's scene from current authoritative state.

    The returned objective_scene is suitable for the Director on the next
    cognition pass. permitted_entities is the trusted reference whitelist
    suitable for the next Action Interpreter call.
    """
    character_id = int(
        character_id
    )

    location_row = get_participant_location(
        "character",
        character_id,
    )

    if location_row is None:
        raise RuntimeError(
            f"Character {character_id} has no current location."
        )

    location_id = int(
        location_row["location_id"]
    )

    location = get_location(
        location_id
    )

    if location is None:
        raise RuntimeError(
            f"Current location {location_id} does not exist."
        )

    people = _public_people_at_location(
        location_id,
        exclude_character_id=
            character_id,
    )

    objects = _public_objects_at_location(
        location_id
    )

    exits = _connected_exits(
        location_id
    )

    world_event_id = (
        _execution_world_event_id(
            execution
        )
    )

    recent_event = (
        _recent_event_for_character(
            character_id,
            location_id,
            world_event_id,
        )
    )

    objective_scene = {
        "campaign_datetime":
            get_campaign_datetime()
            .strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        "location":
            _public_location(location),
        "people": people,
        "objects": objects,
        "exits": exits,
        "recent_event":
            recent_event,
        "execution":
            _execution_summary(
                execution
            ),
    }

    permitted = []

    for person in people:
        permitted.append(
            make_entity(
                person["entity_type"],
                person["entity_id"],
                person["name"],
            )
        )

    for obj in objects:
        permitted.append(
            make_entity(
                "object",
                obj["entity_id"],
                obj["name"],
            )
        )

    for exit_info in exits:
        permitted.append(
            make_entity(
                "location",
                exit_info["entity_id"],
                exit_info["name"],
            )
        )

    return SceneRefreshResult(
        character_id=character_id,
        location_id=location_id,
        objective_scene=
            objective_scene,
        permitted_entities=
            _dedupe_entity_refs(
                permitted
            ),
        source_world_event_id=
            world_event_id,
    )
