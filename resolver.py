import random

from actions import (
    ActionType,
    ResolutionClass,
    OutcomeDegree,
    ValidationResult,
    ResolvedAction,
)
from characters import (
    get_attribute,
    get_skill,
    get_traits,
)
from world import (
    get_connection_between,
    get_location,
    get_participant_location,
)
from mortality import is_alive


DIFFICULTY = {
    "easy": 8,
    "standard": 10,
    "challenging": 12,
    "hard": 14,
    "very_hard": 16,
    "extreme": 18,
}

DEFAULT_DIFFICULTY = DIFFICULTY["standard"]

MOVEMENT_ACTIONS = {
    ActionType.MOVE,
    ActionType.ENTER,
    ActionType.LEAVE,
    ActionType.FOLLOW,
}

ORDINARY_ACTIONS = {
    ActionType.TAKE,
    ActionType.GIVE,
    ActionType.DROP,
    ActionType.USE,
    ActionType.OPEN,
    ActionType.CLOSE,
    ActionType.LOCK,
}

CONTESTED_PHYSICAL_ACTIONS = {
    ActionType.ATTACK,
    ActionType.GRAB,
    ActionType.RESTRAIN,
    ActionType.DISARM,
    ActionType.ESCAPE,
    ActionType.PUSH,
}

INVESTIGATIVE_ACTIONS = {
    ActionType.OBSERVE,
    ActionType.LISTEN,
    ActionType.SEARCH,
    ActionType.INSPECT,
}

SOCIAL_ACTIONS = {
    ActionType.PERSUADE,
    ActionType.DECEIVE,
    ActionType.INTIMIDATE,
}

# Wits and Presence are deliberately absent.
# Perception is sensory/observable awareness only.
DEFAULT_PAIRINGS = {
    ActionType.OBSERVE:
        ("Perception", "Observation"),
    ActionType.LISTEN:
        ("Perception", "Observation"),
    ActionType.SEARCH:
        ("Perception", "Investigation"),
    ActionType.INSPECT:
        ("Perception", "Investigation"),
    ActionType.ATTACK:
        ("Agility", "Fighting"),
    ActionType.GRAB:
        ("Strength", "Fighting"),
    ActionType.RESTRAIN:
        ("Strength", "Fighting"),
    ActionType.DISARM:
        ("Agility", "Fighting"),
    ActionType.ESCAPE:
        ("Agility", "Athletics"),
    ActionType.PUSH:
        ("Strength", "Athletics"),
    ActionType.PERSUADE:
        (None, "Persuasion"),
    ActionType.DECEIVE:
        (None, "Deception"),
    ActionType.INTIMIDATE:
        (None, "Intimidation"),
    ActionType.UNLOCK:
        ("Agility", "Craft"),
    ActionType.OTHER:
        (None, None),
}

DEFAULT_OPPOSITION = {
    ActionType.ATTACK:
        ("Agility", "Fighting"),
    ActionType.GRAB:
        ("Agility", "Athletics"),
    ActionType.RESTRAIN:
        ("Strength", "Athletics"),
    ActionType.DISARM:
        ("Agility", "Fighting"),
    ActionType.ESCAPE:
        ("Strength", "Fighting"),
    ActionType.PUSH:
        ("Strength", "Athletics"),
}


def is_human_entity(entity):
    return (
        entity is not None
        and entity.entity_type == "player_persona"
    )


def get_entity_traits(entity):
    if entity is None:
        return []

    if entity.entity_type not in {
        "character",
        "player_persona",
    }:
        return []

    return get_traits(
        entity.entity_type,
        entity.entity_id,
    )


def get_actor_pairing(intent):
    attribute = intent.metadata.get(
        "attribute"
    )
    skill = intent.metadata.get(
        "skill"
    )

    default_attribute, default_skill = (
        DEFAULT_PAIRINGS.get(
            intent.action_type,
            (None, None),
        )
    )

    return (
        attribute
        if attribute is not None
        else default_attribute,
        skill
        if skill is not None
        else default_skill,
    )


def get_target_pairing(intent):
    attribute = intent.metadata.get(
        "opposing_attribute"
    )
    skill = intent.metadata.get(
        "opposing_skill"
    )

    default_attribute, default_skill = (
        DEFAULT_OPPOSITION.get(
            intent.action_type,
            (None, None),
        )
    )

    return (
        attribute
        if attribute is not None
        else default_attribute,
        skill
        if skill is not None
        else default_skill,
    )


def validate_action(intent):
    action_type = intent.action_type

    if (
        intent.actor.entity_type
        in {"character", "player_persona"}
        and not is_alive(
            intent.actor.entity_type,
            intent.actor.entity_id,
        )
    ):
        return ValidationResult(
            allowed=False,
            resolution_class=
                ResolutionClass.IMPOSSIBLE,
            reason=(
                "A deceased character cannot perform this action."
            ),
        )

    if intent.metadata.get("impossible"):
        return ValidationResult(
            allowed=False,
            resolution_class=
                ResolutionClass.IMPOSSIBLE,
            reason=intent.metadata.get(
                "impossible_reason",
                (
                    "The action is not physically or logically possible."
                ),
            ),
        )

    if intent.metadata.get("automatic"):
        return ValidationResult(
            allowed=True,
            resolution_class=
                ResolutionClass.AUTOMATIC,
            reason=(
                "The action does not require a roll."
            ),
        )

    if action_type in MOVEMENT_ACTIONS:
        if intent.destination is None:
            return ValidationResult(
                allowed=False,
                resolution_class=
                    ResolutionClass.IMPOSSIBLE,
                reason="No destination was specified.",
            )

        destination = get_location(
            int(
                intent.destination.entity_id
            )
        )

        if destination is None:
            return ValidationResult(
                allowed=False,
                resolution_class=
                    ResolutionClass.IMPOSSIBLE,
                reason="The destination does not exist.",
            )

        current = get_participant_location(
            intent.actor.entity_type,
            intent.actor.entity_id,
        )

        if current is None:
            return ValidationResult(
                allowed=True,
                resolution_class=
                    ResolutionClass.AUTOMATIC,
                reason="Initial placement.",
            )

        if (
            current["location_id"]
            == int(
                intent.destination.entity_id
            )
        ):
            return ValidationResult(
                allowed=False,
                resolution_class=
                    ResolutionClass.IMPOSSIBLE,
                reason="The actor is already there.",
            )

        connection = get_connection_between(
            current["location_id"],
            int(
                intent.destination.entity_id
            ),
        )

        if connection is None:
            return ValidationResult(
                allowed=False,
                resolution_class=
                    ResolutionClass.IMPOSSIBLE,
                reason=(
                    "There is no direct route between those locations."
                ),
            )

        if connection["locked"]:
            return ValidationResult(
                allowed=False,
                resolution_class=
                    ResolutionClass.IMPOSSIBLE,
                reason="The route is locked.",
            )

        if connection["restricted"]:
            return ValidationResult(
                allowed=False,
                resolution_class=
                    ResolutionClass.IMPOSSIBLE,
                reason=(
                    "The route is currently restricted."
                ),
            )

        return ValidationResult(
            allowed=True,
            resolution_class=
                ResolutionClass.AUTOMATIC,
            reason="The movement is unobstructed.",
        )

    requested_class = intent.metadata.get(
        "resolution_class"
    )

    if requested_class:
        resolution_class = ResolutionClass(
            requested_class
        )
    elif (
        action_type
        in CONTESTED_PHYSICAL_ACTIONS
    ):
        resolution_class = (
            ResolutionClass.CONTESTED
        )
    elif (
        action_type
        in INVESTIGATIVE_ACTIONS
    ):
        resolution_class = (
            ResolutionClass.UNCERTAIN
        )
    elif action_type in SOCIAL_ACTIONS:
        # Social resolution judges only external effectiveness.
        # It is not a lie detector and never decides a mind.
        resolution_class = (
            ResolutionClass.UNCERTAIN
        )
    elif action_type == ActionType.UNLOCK:
        resolution_class = (
            ResolutionClass.UNCERTAIN
        )
    elif action_type in ORDINARY_ACTIONS:
        resolution_class = (
            ResolutionClass.AUTOMATIC
        )
    else:
        resolution_class = (
            ResolutionClass.UNCERTAIN
        )

    if (
        action_type in SOCIAL_ACTIONS
        and is_human_entity(
            intent.target
        )
    ):
        actor_attribute, actor_skill = (
            get_actor_pairing(intent)
        )

        return ValidationResult(
            allowed=True,
            resolution_class=
                ResolutionClass.UNCERTAIN,
            reason=(
                "Resolve external effectiveness only; "
                "the human player retains control of their "
                "character's internal response."
            ),
            difficulty=intent.metadata.get(
                "difficulty",
                DEFAULT_DIFFICULTY,
            ),
            relevant_stat=actor_attribute,
            relevant_skill=actor_skill,
            requires_roll=True,
            preserves_human_agency=True,
        )

    if (
        resolution_class
        == ResolutionClass.AUTOMATIC
    ):
        return ValidationResult(
            allowed=True,
            resolution_class=
                ResolutionClass.AUTOMATIC,
            reason=(
                "No meaningful uncertainty requires a roll."
            ),
        )

    actor_attribute, actor_skill = (
        get_actor_pairing(intent)
    )

    if (
        resolution_class
        == ResolutionClass.UNCERTAIN
    ):
        return ValidationResult(
            allowed=True,
            resolution_class=
                ResolutionClass.UNCERTAIN,
            reason=(
                "The outcome is meaningfully uncertain."
            ),
            difficulty=intent.metadata.get(
                "difficulty",
                DEFAULT_DIFFICULTY,
            ),
            relevant_stat=actor_attribute,
            relevant_skill=actor_skill,
            requires_roll=True,
        )

    if (
        resolution_class
        == ResolutionClass.CONTESTED
    ):
        if intent.target is None:
            return ValidationResult(
                allowed=False,
                resolution_class=
                    ResolutionClass.IMPOSSIBLE,
                reason=(
                    "A contested action requires an opposing target."
                ),
            )

        target_attribute, target_skill = (
            get_target_pairing(intent)
        )

        return ValidationResult(
            allowed=True,
            resolution_class=
                ResolutionClass.CONTESTED,
            reason=(
                "Another character can actively oppose it."
            ),
            relevant_stat=actor_attribute,
            relevant_skill=actor_skill,
            opposing_stat=target_attribute,
            opposing_skill=target_skill,
            requires_roll=True,
        )

    return ValidationResult(
        allowed=False,
        resolution_class=
            ResolutionClass.IMPOSSIBLE,
        reason="No valid resolution rule was found.",
    )


def roll_2d6():
    die_one = random.randint(1, 6)
    die_two = random.randint(1, 6)
    return (
        die_one,
        die_two,
        die_one + die_two,
    )


def calculate_total(
    entity,
    attribute_name=None,
    skill_name=None,
    modifier=0,
):
    attribute_value = 0
    skill_value = 0

    if (
        attribute_name
        and entity.entity_type
        in {"character", "player_persona"}
    ):
        attribute_value = get_attribute(
            entity.entity_type,
            entity.entity_id,
            attribute_name,
        )

    if (
        skill_name
        and entity.entity_type
        in {"character", "player_persona"}
    ):
        skill_value = get_skill(
            entity.entity_type,
            entity.entity_id,
            skill_name,
        )

    die_one, die_two, dice_total = roll_2d6()

    total = (
        dice_total
        + attribute_value
        + skill_value
        + int(modifier)
    )

    return {
        "dice": (die_one, die_two),
        "dice_total": dice_total,
        "attribute": attribute_value,
        "skill": skill_value,
        "modifier": int(modifier),
        "total": total,
    }


def degree_from_margin(margin):
    if margin < 0:
        return OutcomeDegree.FAILURE

    if margin <= 2:
        return OutcomeDegree.PARTIAL_SUCCESS

    if margin <= 6:
        return OutcomeDegree.SUCCESS

    return OutcomeDegree.EXCEPTIONAL_SUCCESS


def resolve_action(intent):
    validation = validate_action(intent)

    if not validation.allowed:
        return ResolvedAction(
            intent=intent,
            resolution_class=
                validation.resolution_class,
            degree=OutcomeDegree.FAILURE,
            success=False,
            outcome=validation.reason,
        )

    if (
        validation.resolution_class
        == ResolutionClass.AUTOMATIC
    ):
        return ResolvedAction(
            intent=intent,
            resolution_class=
                ResolutionClass.AUTOMATIC,
            degree=OutcomeDegree.SUCCESS,
            success=True,
            outcome=(
                "The action succeeds without requiring "
                "a mechanical roll."
            ),
        )

    if (
        validation.resolution_class
        == ResolutionClass.UNCERTAIN
    ):
        actor_result = calculate_total(
            intent.actor,
            validation.relevant_stat,
            validation.relevant_skill,
            intent.metadata.get(
                "modifier",
                0,
            ),
        )

        difficulty = (
            validation.difficulty
            if validation.difficulty is not None
            else DEFAULT_DIFFICULTY
        )

        margin = (
            actor_result["total"]
            - difficulty
        )
        degree = degree_from_margin(
            margin
        )
        success = (
            degree != OutcomeDegree.FAILURE
        )

        if validation.preserves_human_agency:
            outcome = (
                f"External effectiveness: {degree.value}. "
                "This result does not determine the human "
                "target's thoughts, feelings, beliefs, or "
                "voluntary choices."
            )
        elif intent.action_type in SOCIAL_ACTIONS:
            outcome = (
                f"External effectiveness: {degree.value}. "
                "This does not determine the target's "
                "private thoughts, beliefs, feelings, or choices."
            )
        else:
            outcome = (
                f"The action resolves as {degree.value}."
            )

        return ResolvedAction(
            intent=intent,
            resolution_class=
                validation.resolution_class,
            degree=degree,
            success=success,
            outcome=outcome,
            actor_roll=
                actor_result["dice_total"],
            actor_total=
                actor_result["total"],
            difficulty=difficulty,
            metadata={
                "dice":
                    actor_result["dice"],
                "attribute_value":
                    actor_result["attribute"],
                "skill_value":
                    actor_result["skill"],
                "modifier":
                    actor_result["modifier"],
                "preserves_human_agency":
                    validation.preserves_human_agency,
            },
        )

    if (
        validation.resolution_class
        == ResolutionClass.CONTESTED
    ):
        actor_result = calculate_total(
            intent.actor,
            validation.relevant_stat,
            validation.relevant_skill,
            intent.metadata.get(
                "modifier",
                0,
            ),
        )

        target_result = calculate_total(
            intent.target,
            validation.opposing_stat,
            validation.opposing_skill,
            intent.metadata.get(
                "opposing_modifier",
                0,
            ),
        )

        margin = (
            actor_result["total"]
            - target_result["total"]
        )
        degree = degree_from_margin(
            margin
        )
        success = (
            degree != OutcomeDegree.FAILURE
        )

        return ResolvedAction(
            intent=intent,
            resolution_class=
                ResolutionClass.CONTESTED,
            degree=degree,
            success=success,
            outcome=(
                f"The contested action resolves as "
                f"{degree.value}."
            ),
            actor_roll=
                actor_result["dice_total"],
            actor_total=
                actor_result["total"],
            target_roll=
                target_result["dice_total"],
            target_total=
                target_result["total"],
            metadata={
                "actor_dice":
                    actor_result["dice"],
                "target_dice":
                    target_result["dice"],
                "actor_attribute_value":
                    actor_result["attribute"],
                "actor_skill_value":
                    actor_result["skill"],
                "target_attribute_value":
                    target_result["attribute"],
                "target_skill_value":
                    target_result["skill"],
                "actor_modifier":
                    actor_result["modifier"],
                "target_modifier":
                    target_result["modifier"],
            },
        )

    return ResolvedAction(
        intent=intent,
        resolution_class=
            ResolutionClass.IMPOSSIBLE,
        degree=OutcomeDegree.FAILURE,
        success=False,
        outcome="No valid resolution path was found.",
    )
