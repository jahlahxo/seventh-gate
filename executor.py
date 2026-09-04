from actions import (
    ActionType,
    OutcomeDegree,
    ResolutionClass,
)
from database import get_connection
from entities import (
    get_object,
    get_object_placement,
    get_object_state,
    place_object,
    set_object_open,
    set_object_locked,
)
from world import (
    get_participant_location,
    get_location,
    get_or_create_scene,
    move_participant,
    record_world_event,
)


# ============================================================
# EXECUTION RESULT
#
# Returned to the Director after an authoritative consequence
# has been applied.
# ============================================================

class ExecutionResult:
    def __init__(
        self,
        executed,
        world_event_id=None,
        description=None,
        state_changes=None,
        reason=None,
    ):
        self.executed = executed
        self.world_event_id = world_event_id
        self.description = description
        self.state_changes = state_changes or []
        self.reason = reason

    def as_dict(self):
        return {
            "executed": self.executed,
            "world_event_id": self.world_event_id,
            "description": self.description,
            "state_changes": self.state_changes,
            "reason": self.reason,
        }


# ============================================================
# STATE CHANGE AUDIT
#
# world_events = what happened
# state_changes = exactly what objective value changed
# ============================================================

def record_state_change(
    world_event_id,
    entity_type,
    entity_id,
    field_name,
    old_value,
    new_value,
):
    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO state_changes (
            world_event_id,
            entity_type,
            entity_id,
            field_name,
            old_value,
            new_value
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            world_event_id,
            entity_type,
            (
                str(entity_id)
                if entity_id is not None
                else None
            ),
            field_name,
            (
                str(old_value)
                if old_value is not None
                else None
            ),
            (
                str(new_value)
                if new_value is not None
                else None
            ),
        ),
    )

    state_change_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return state_change_id


# ============================================================
# WORLD EVENT FOR A RESOLVED ACTION
# ============================================================

def create_action_event(
    resolved_action,
    content,
    outcome,
    location_id=None,
    scene_id=None,
):
    intent = resolved_action.intent

    return record_world_event(
        event_type=intent.action_type.value,
        content=content,
        outcome=outcome,

        source_type=intent.source_type,
        source_id=intent.source_id,

        scene_id=scene_id,
        location_id=location_id,

        actor_type=intent.actor.entity_type,
        actor_id=intent.actor.entity_id,

        target_type=(
            intent.target.entity_type
            if intent.target
            else None
        ),

        target_id=(
            intent.target.entity_id
            if intent.target
            else None
        ),

        authority=100,
    )


# ============================================================
# CURRENT LOCATION HELPER
# ============================================================

def get_actor_location(intent):
    row = get_participant_location(
        intent.actor.entity_type,
        intent.actor.entity_id,
    )

    if row is None:
        return None

    return row["location_id"]


# ============================================================
# MOVEMENT EXECUTION
# ============================================================

def execute_movement(resolved_action):
    intent = resolved_action.intent

    if intent.destination is None:
        return ExecutionResult(
            executed=False,
            reason="Movement has no destination.",
        )

    destination_id = int(
        intent.destination.entity_id
    )

    old_location = get_participant_location(
        intent.actor.entity_type,
        intent.actor.entity_id,
    )

    old_location_id = (
        old_location["location_id"]
        if old_location
        else None
    )

    # world.move_participant performs the authoritative move
    # and writes the movement event.
    event_id = move_participant(
        participant_type=intent.actor.entity_type,
        participant_id=intent.actor.entity_id,
        destination_location_id=destination_id,
        source_type=intent.source_type,
        source_id=intent.source_id,
    )

    destination = get_location(destination_id)

    if old_location_id is None:
        description = (
            f"{intent.actor.name or intent.actor.entity_id} "
            f"is now at {destination['name']}."
        )
    else:
        old_location_row = get_location(
            old_location_id
        )

        description = (
            f"{intent.actor.name or intent.actor.entity_id} "
            f"moves from {old_location_row['name']} "
            f"to {destination['name']}."
        )

    state_change_ids = []

    if event_id is not None:
        state_change_ids.append(
            record_state_change(
                world_event_id=event_id,
                entity_type=intent.actor.entity_type,
                entity_id=intent.actor.entity_id,
                field_name="location_id",
                old_value=old_location_id,
                new_value=destination_id,
            )
        )

    return ExecutionResult(
        executed=True,
        world_event_id=event_id,
        description=description,
        state_changes=state_change_ids,
    )


# ============================================================
# NON-STATEFUL ACTION EVENT
#
# Some resolved events matter historically without changing a
# persistent field immediately.
#
# Example:
# Matti successfully notices a footprint.
#
# The event is authoritative even though nobody's location,
# ownership, etc. changes.
# ============================================================

def execute_event_only(resolved_action):
    intent = resolved_action.intent

    location_id = get_actor_location(intent)

    scene_id = None

    if location_id is not None:
        scene_id = get_or_create_scene(
            location_id
        )

    if resolved_action.degree == OutcomeDegree.PARTIAL_SUCCESS:
        outcome_text = "partial_success"

    elif resolved_action.degree == OutcomeDegree.SUCCESS:
        outcome_text = "success"

    elif (
        resolved_action.degree
        == OutcomeDegree.EXCEPTIONAL_SUCCESS
    ):
        outcome_text = "exceptional_success"

    else:
        outcome_text = "failure"

    content = intent.description

    if resolved_action.metadata.get("preserves_human_agency"):
        content = (
            f"{intent.description} "
            f"External effectiveness: {resolved_action.degree.value}. "
            "No internal state or voluntary choice is assigned "
            "to the human-controlled target."
        )

    event_id = create_action_event(
        resolved_action=resolved_action,
        content=content,
        outcome=outcome_text,
        location_id=location_id,
        scene_id=scene_id,
    )

    return ExecutionResult(
        executed=True,
        world_event_id=event_id,
        description=content,
    )


# ============================================================
# FAILED ATTEMPT
#
# Failure can still be an authoritative event.
#
# "Matti tried to seize Pekka's wrist but failed."
#
# That matters for witnesses and memory even though the
# intended state change did not occur.
# ============================================================

def execute_failed_attempt(resolved_action):
    intent = resolved_action.intent

    location_id = get_actor_location(intent)

    scene_id = None

    if location_id is not None:
        scene_id = get_or_create_scene(
            location_id
        )

    content = (
        f"{intent.description} "
        f"The attempt does not succeed."
    )

    event_id = create_action_event(
        resolved_action=resolved_action,
        content=content,
        outcome="failure",
        location_id=location_id,
        scene_id=scene_id,
    )

    return ExecutionResult(
        executed=True,
        world_event_id=event_id,
        description=content,
    )



# ============================================================
# OBJECT / INVENTORY HELPERS
# ============================================================

def _placement_text(placement):
    if placement is None:
        return None

    return (
        f"{placement['holder_type']}:"
        f"{placement['holder_id']}:"
        f"{placement['relation']}"
    )


def _entity_location(entity_type, entity_id):
    if entity_type not in {
        "character",
        "player_persona",
    }:
        return None

    row = get_participant_location(
        entity_type,
        entity_id,
    )

    if row is None:
        return None

    return row["location_id"]


def _object_context(object_id):
    """
    Return the object's effective location and whether it is
    physically accessible from that location.

    Objects inside a closed openable container are not
    accessible until that container is opened.
    """
    visited = set()
    current_object_id = int(object_id)
    accessible = True

    while True:
        if current_object_id in visited:
            raise ValueError(
                "Object placement cycle detected."
            )

        visited.add(current_object_id)

        placement = get_object_placement(
            current_object_id
        )

        if placement is None:
            return {
                "location_id": None,
                "accessible": False,
            }

        holder_type = placement["holder_type"]
        holder_id = placement["holder_id"]
        relation = placement["relation"]

        if holder_type == "location":
            return {
                "location_id": int(holder_id),
                "accessible": accessible,
            }

        if holder_type in {
            "character",
            "player_persona",
        }:
            return {
                "location_id": _entity_location(
                    holder_type,
                    holder_id,
                ),
                "accessible": accessible,
            }

        if holder_type != "object":
            return {
                "location_id": None,
                "accessible": False,
            }

        container = get_object(
            holder_id
        )

        state = get_object_state(
            holder_id
        )

        if (
            relation == "inside"
            and container["is_openable"]
            and state is not None
            and state["is_open"] == 0
        ):
            accessible = False

        current_object_id = int(holder_id)


def _actor_can_reach_object(intent, object_id):
    actor_location_id = get_actor_location(intent)

    if actor_location_id is None:
        return False

    context = _object_context(object_id)

    return (
        context["accessible"]
        and context["location_id"] == actor_location_id
    )


def _same_location(
    first_type,
    first_id,
    second_type,
    second_id,
):
    first = _entity_location(
        first_type,
        first_id,
    )

    second = _entity_location(
        second_type,
        second_id,
    )

    return (
        first is not None
        and second is not None
        and first == second
    )


def _object_action_event(
    resolved_action,
    content=None,
):
    intent = resolved_action.intent

    location_id = get_actor_location(
        intent
    )

    scene_id = None

    if location_id is not None:
        scene_id = get_or_create_scene(
            location_id
        )

    return create_action_event(
        resolved_action=resolved_action,
        content=content or intent.description,
        outcome=resolved_action.degree.value,
        location_id=location_id,
        scene_id=scene_id,
    )


# ============================================================
# TAKE
#
# target = object
# ============================================================

def execute_take(resolved_action):
    intent = resolved_action.intent

    if (
        intent.target is None
        or intent.target.entity_type != "object"
    ):
        return ExecutionResult(
            executed=False,
            reason="TAKE requires an object target.",
        )

    object_id = int(
        intent.target.entity_id
    )

    obj = get_object(
        object_id
    )

    if not obj["portable"]:
        return ExecutionResult(
            executed=False,
            reason="That object is not portable.",
        )

    old_placement = get_object_placement(
        object_id
    )

    if old_placement is None:
        return ExecutionResult(
            executed=False,
            reason="The object has no physical placement.",
        )

    if (
        old_placement["holder_type"]
        == intent.actor.entity_type
        and old_placement["holder_id"]
        == str(intent.actor.entity_id)
    ):
        return ExecutionResult(
            executed=False,
            reason="The actor already possesses that object.",
        )

    if old_placement["holder_type"] in {
        "character",
        "player_persona",
    }:
        return ExecutionResult(
            executed=False,
            reason=(
                "Another character currently possesses "
                "that object; use an appropriate contested "
                "action instead of TAKE."
            ),
        )

    if not _actor_can_reach_object(
        intent,
        object_id,
    ):
        return ExecutionResult(
            executed=False,
            reason="The object is not physically accessible to the actor.",
        )

    event_id = _object_action_event(
        resolved_action
    )

    place_object(
        object_id=object_id,
        holder_type=intent.actor.entity_type,
        holder_id=intent.actor.entity_id,
        relation=intent.metadata.get(
            "result_relation",
            "held",
        ),
    )

    new_placement = get_object_placement(
        object_id
    )

    change_id = record_state_change(
        world_event_id=event_id,
        entity_type="object",
        entity_id=object_id,
        field_name="placement",
        old_value=_placement_text(
            old_placement
        ),
        new_value=_placement_text(
            new_placement
        ),
    )

    return ExecutionResult(
        executed=True,
        world_event_id=event_id,
        description=intent.description,
        state_changes=[change_id],
    )


# ============================================================
# GIVE
#
# target = recipient character/persona
# instrument = object
# ============================================================

def execute_give(resolved_action):
    intent = resolved_action.intent

    if (
        intent.target is None
        or intent.target.entity_type not in {
            "character",
            "player_persona",
        }
    ):
        return ExecutionResult(
            executed=False,
            reason="GIVE requires a character/persona target.",
        )

    if (
        intent.instrument is None
        or intent.instrument.entity_type != "object"
    ):
        return ExecutionResult(
            executed=False,
            reason="GIVE requires an object as instrument.",
        )

    object_id = int(
        intent.instrument.entity_id
    )

    old_placement = get_object_placement(
        object_id
    )

    if (
        old_placement is None
        or old_placement["holder_type"]
        != intent.actor.entity_type
        or old_placement["holder_id"]
        != str(intent.actor.entity_id)
    ):
        return ExecutionResult(
            executed=False,
            reason="The actor does not possess that object.",
        )

    if not _same_location(
        intent.actor.entity_type,
        intent.actor.entity_id,
        intent.target.entity_type,
        intent.target.entity_id,
    ):
        return ExecutionResult(
            executed=False,
            reason="The recipient is not in the same location.",
        )

    event_id = _object_action_event(
        resolved_action
    )

    place_object(
        object_id=object_id,
        holder_type=intent.target.entity_type,
        holder_id=intent.target.entity_id,
        relation=intent.metadata.get(
            "result_relation",
            "carried",
        ),
    )

    new_placement = get_object_placement(
        object_id
    )

    change_id = record_state_change(
        world_event_id=event_id,
        entity_type="object",
        entity_id=object_id,
        field_name="placement",
        old_value=_placement_text(
            old_placement
        ),
        new_value=_placement_text(
            new_placement
        ),
    )

    return ExecutionResult(
        executed=True,
        world_event_id=event_id,
        description=intent.description,
        state_changes=[change_id],
    )


# ============================================================
# DROP
#
# target = object
# ============================================================

def execute_drop(resolved_action):
    intent = resolved_action.intent

    if (
        intent.target is None
        or intent.target.entity_type != "object"
    ):
        return ExecutionResult(
            executed=False,
            reason="DROP requires an object target.",
        )

    object_id = int(
        intent.target.entity_id
    )

    old_placement = get_object_placement(
        object_id
    )

    if (
        old_placement is None
        or old_placement["holder_type"]
        != intent.actor.entity_type
        or old_placement["holder_id"]
        != str(intent.actor.entity_id)
    ):
        return ExecutionResult(
            executed=False,
            reason="The actor does not possess that object.",
        )

    location_id = get_actor_location(
        intent
    )

    if location_id is None:
        return ExecutionResult(
            executed=False,
            reason="The actor has no physical location.",
        )

    event_id = _object_action_event(
        resolved_action
    )

    place_object(
        object_id=object_id,
        holder_type="location",
        holder_id=location_id,
        relation="at",
    )

    new_placement = get_object_placement(
        object_id
    )

    change_id = record_state_change(
        world_event_id=event_id,
        entity_type="object",
        entity_id=object_id,
        field_name="placement",
        old_value=_placement_text(
            old_placement
        ),
        new_value=_placement_text(
            new_placement
        ),
    )

    return ExecutionResult(
        executed=True,
        world_event_id=event_id,
        description=intent.description,
        state_changes=[change_id],
    )


# ============================================================
# OPEN / CLOSE
#
# target = object
# ============================================================

def execute_open_close(
    resolved_action,
    should_open,
):
    intent = resolved_action.intent

    if (
        intent.target is None
        or intent.target.entity_type != "object"
    ):
        return ExecutionResult(
            executed=False,
            reason="OPEN/CLOSE requires an object target.",
        )

    object_id = int(
        intent.target.entity_id
    )

    if not _actor_can_reach_object(
        intent,
        object_id,
    ):
        return ExecutionResult(
            executed=False,
            reason="The object is not physically accessible to the actor.",
        )

    old_state = get_object_state(
        object_id
    )

    if old_state is None:
        return ExecutionResult(
            executed=False,
            reason="The object has no state record.",
        )

    if (
        old_state["is_open"]
        is not None
        and bool(old_state["is_open"])
        == bool(should_open)
    ):
        return ExecutionResult(
            executed=False,
            reason=(
                "The object is already "
                + ("open." if should_open else "closed.")
            ),
        )

    try:
        event_id = _object_action_event(
            resolved_action
        )

        new_state = set_object_open(
            object_id,
            should_open,
        )
    except (ValueError, PermissionError) as exc:
        return ExecutionResult(
            executed=False,
            reason=str(exc),
        )

    change_id = record_state_change(
        world_event_id=event_id,
        entity_type="object",
        entity_id=object_id,
        field_name="is_open",
        old_value=old_state["is_open"],
        new_value=new_state["is_open"],
    )

    return ExecutionResult(
        executed=True,
        world_event_id=event_id,
        description=intent.description,
        state_changes=[change_id],
    )


# ============================================================
# LOCK / UNLOCK
#
# target = object
# ============================================================

def execute_lock_unlock(
    resolved_action,
    should_lock,
):
    intent = resolved_action.intent

    if (
        intent.target is None
        or intent.target.entity_type != "object"
    ):
        return ExecutionResult(
            executed=False,
            reason="LOCK/UNLOCK requires an object target.",
        )

    object_id = int(
        intent.target.entity_id
    )

    if not _actor_can_reach_object(
        intent,
        object_id,
    ):
        return ExecutionResult(
            executed=False,
            reason="The object is not physically accessible to the actor.",
        )

    old_state = get_object_state(
        object_id
    )

    if old_state is None:
        return ExecutionResult(
            executed=False,
            reason="The object has no state record.",
        )

    if (
        old_state["is_locked"]
        is not None
        and bool(old_state["is_locked"])
        == bool(should_lock)
    ):
        return ExecutionResult(
            executed=False,
            reason=(
                "The object is already "
                + ("locked." if should_lock else "unlocked.")
            ),
        )

    try:
        event_id = _object_action_event(
            resolved_action
        )

        new_state = set_object_locked(
            object_id,
            should_lock,
        )
    except (ValueError, PermissionError) as exc:
        return ExecutionResult(
            executed=False,
            reason=str(exc),
        )

    change_id = record_state_change(
        world_event_id=event_id,
        entity_type="object",
        entity_id=object_id,
        field_name="is_locked",
        old_value=old_state["is_locked"],
        new_value=new_state["is_locked"],
    )

    return ExecutionResult(
        executed=True,
        world_event_id=event_id,
        description=intent.description,
        state_changes=[change_id],
    )


# ============================================================
# DISARM
#
# target = opposing character/persona
# instrument = object being taken away
#
# The resolver has already decided whether the contested
# attempt succeeded. The executor only enforces the result.
# ============================================================

def execute_disarm(resolved_action):
    intent = resolved_action.intent

    if (
        intent.target is None
        or intent.target.entity_type not in {
            "character",
            "player_persona",
        }
    ):
        return ExecutionResult(
            executed=False,
            reason="DISARM requires a character/persona target.",
        )

    if (
        intent.instrument is None
        or intent.instrument.entity_type != "object"
    ):
        return ExecutionResult(
            executed=False,
            reason="DISARM requires the relevant object as instrument.",
        )

    object_id = int(
        intent.instrument.entity_id
    )

    old_placement = get_object_placement(
        object_id
    )

    if (
        old_placement is None
        or old_placement["holder_type"]
        != intent.target.entity_type
        or old_placement["holder_id"]
        != str(intent.target.entity_id)
    ):
        return ExecutionResult(
            executed=False,
            reason="The target does not currently possess that object.",
        )

    if not _same_location(
        intent.actor.entity_type,
        intent.actor.entity_id,
        intent.target.entity_type,
        intent.target.entity_id,
    ):
        return ExecutionResult(
            executed=False,
            reason="Actor and target are not in the same location.",
        )

    event_id = _object_action_event(
        resolved_action
    )

    place_object(
        object_id=object_id,
        holder_type=intent.actor.entity_type,
        holder_id=intent.actor.entity_id,
        relation=intent.metadata.get(
            "result_relation",
            "held",
        ),
    )

    new_placement = get_object_placement(
        object_id
    )

    change_id = record_state_change(
        world_event_id=event_id,
        entity_type="object",
        entity_id=object_id,
        field_name="placement",
        old_value=_placement_text(
            old_placement
        ),
        new_value=_placement_text(
            new_placement
        ),
    )

    return ExecutionResult(
        executed=True,
        world_event_id=event_id,
        description=intent.description,
        state_changes=[change_id],
    )


# ============================================================
# MAIN EXECUTOR
# ============================================================

def execute_resolved_action(
    resolved_action,
):
    intent = resolved_action.intent

    # --------------------------------------------------------
    # Invalid / impossible actions do NOT become successful
    # world changes.
    #
    # The attempted prose still exists in rp_messages.
    # --------------------------------------------------------

    if (
        resolved_action.resolution_class
        == ResolutionClass.IMPOSSIBLE
    ):
        return ExecutionResult(
            executed=False,
            reason=resolved_action.outcome,
        )

    # --------------------------------------------------------
    # Failed attempt
    # --------------------------------------------------------

    if not resolved_action.success:
        return execute_failed_attempt(
            resolved_action
        )

    # --------------------------------------------------------
    # Movement
    # --------------------------------------------------------

    if intent.action_type in {
        ActionType.MOVE,
        ActionType.ENTER,
        ActionType.LEAVE,
        ActionType.FOLLOW,
    }:
        return execute_movement(
            resolved_action
        )

    # --------------------------------------------------------
    # Object / inventory state
    # --------------------------------------------------------

    if intent.action_type == ActionType.TAKE:
        return execute_take(
            resolved_action
        )

    if intent.action_type == ActionType.GIVE:
        return execute_give(
            resolved_action
        )

    if intent.action_type == ActionType.DROP:
        return execute_drop(
            resolved_action
        )

    if intent.action_type == ActionType.OPEN:
        return execute_open_close(
            resolved_action,
            True,
        )

    if intent.action_type == ActionType.CLOSE:
        return execute_open_close(
            resolved_action,
            False,
        )

    if intent.action_type == ActionType.LOCK:
        return execute_lock_unlock(
            resolved_action,
            True,
        )

    if intent.action_type == ActionType.UNLOCK:
        return execute_lock_unlock(
            resolved_action,
            False,
        )

    if intent.action_type == ActionType.DISARM:
        return execute_disarm(
            resolved_action
        )

    # --------------------------------------------------------
    # Everything else currently produces an authoritative
    # event, but only explicit state handlers may mutate
    # persistent world state.
    #
    # This is intentional:
    # we never infer arbitrary database changes from prose.
    # --------------------------------------------------------

    return execute_event_only(
        resolved_action
    )