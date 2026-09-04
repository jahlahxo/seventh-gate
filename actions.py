from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ============================================================
# ACTION TYPES
#
# These describe what somebody is ATTEMPTING to do.
# They are not proof that the action succeeded.
# ============================================================

class ActionType(str, Enum):
    # Movement
    MOVE = "move"
    ENTER = "enter"
    LEAVE = "leave"
    FOLLOW = "follow"

    # Perception / investigation
    OBSERVE = "observe"
    LISTEN = "listen"
    SEARCH = "search"
    INSPECT = "inspect"

    # Ordinary physical interaction
    TAKE = "take"
    GIVE = "give"
    DROP = "drop"
    USE = "use"
    OPEN = "open"
    CLOSE = "close"
    LOCK = "lock"
    UNLOCK = "unlock"

    # Physical contested actions
    ATTACK = "attack"
    GRAB = "grab"
    RESTRAIN = "restrain"
    DISARM = "disarm"
    ESCAPE = "escape"
    PUSH = "push"

    # Social attempts
    PERSUADE = "persuade"
    DECEIVE = "deceive"
    INTIMIDATE = "intimidate"

    # General fallback
    OTHER = "other"


# ============================================================
# ACTION CLASSIFICATION
#
# The resolver eventually assigns one of these.
# ============================================================

class ResolutionClass(str, Enum):
    AUTOMATIC = "automatic"
    IMPOSSIBLE = "impossible"
    UNCERTAIN = "uncertain"
    CONTESTED = "contested"


# ============================================================
# ACTION STATUS
# ============================================================

class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    VALIDATING = "validating"
    PENDING_ROLL = "pending_roll"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# ============================================================
# OUTCOME DEGREE
# ============================================================

class OutcomeDegree(str, Enum):
    CATASTROPHIC_FAILURE = "catastrophic_failure"
    FAILURE = "failure"
    PARTIAL_SUCCESS = "partial_success"
    SUCCESS = "success"
    EXCEPTIONAL_SUCCESS = "exceptional_success"


# ============================================================
# ACTOR / TARGET REFERENCES
#
# entity_type will normally be:
#
# player_persona
# character
# location
# object
#
# Keeping this generic lets us add animals, groups, etc. later
# without redesigning the action system.
# ============================================================

@dataclass(frozen=True)
class EntityRef:
    entity_type: str
    entity_id: str
    name: Optional[str] = None


# ============================================================
# STRUCTURED ACTION INTENT
#
# This is what both humans and NPCs eventually produce after
# natural-language interpretation.
#
# IMPORTANT:
# description = what was attempted.
# asserted_outcome = what the writer CLAIMED happened.
#
# The asserted outcome is never automatically accepted as
# authoritative reality.
# ============================================================

@dataclass
class ActionIntent:
    action_type: ActionType

    actor: EntityRef

    description: str

    target: Optional[EntityRef] = None
    destination: Optional[EntityRef] = None
    instrument: Optional[EntityRef] = None

    source_type: str = "unknown"
    source_id: Optional[str] = None

    asserted_outcome: Optional[str] = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# VALIDATION RESULT
#
# The resolver uses this before anything becomes reality.
# ============================================================

@dataclass
class ValidationResult:
    allowed: bool

    resolution_class: ResolutionClass

    reason: str = ""

    difficulty: Optional[int] = None

    relevant_stat: Optional[str] = None
    relevant_skill: Optional[str] = None

    opposing_stat: Optional[str] = None
    opposing_skill: Optional[str] = None

    requires_roll: bool = False
    preserves_human_agency: bool = False


# ============================================================
# RESOLVED ACTION
#
# This is produced only AFTER validation/resolution.
#
# It still isn't the event ledger itself. The world engine
# converts successful consequences into authoritative events.
# ============================================================

@dataclass
class ResolvedAction:
    intent: ActionIntent

    resolution_class: ResolutionClass
    degree: OutcomeDegree

    success: bool

    outcome: str

    actor_roll: Optional[int] = None
    actor_total: Optional[int] = None

    target_roll: Optional[int] = None
    target_total: Optional[int] = None

    difficulty: Optional[int] = None

    authority_overridden: bool = False

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    @property
    def gm_overridden(self):
        """Legacy read-only alias; use authority_overridden."""
        return self.authority_overridden


# ============================================================
# HELPERS
# ============================================================

def make_entity(
    entity_type,
    entity_id,
    name=None,
):
    return EntityRef(
        entity_type=str(entity_type),
        entity_id=str(entity_id),
        name=name,
    )


def make_action(
    action_type,
    actor,
    description,
    target=None,
    destination=None,
    instrument=None,
    source_type="unknown",
    source_id=None,
    asserted_outcome=None,
    metadata=None,
):
    if not isinstance(action_type, ActionType):
        action_type = ActionType(action_type)

    return ActionIntent(
        action_type=action_type,
        actor=actor,
        description=description,
        target=target,
        destination=destination,
        instrument=instrument,
        source_type=source_type,
        source_id=(
            str(source_id)
            if source_id is not None
            else None
        ),
        asserted_outcome=asserted_outcome,
        metadata=metadata or {},
    )