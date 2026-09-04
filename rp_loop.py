from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from character_brain import (
    CharacterBrainResponse,
    run_character_brain,
)
from director import (
    DirectorPerceptionResult,
    run_director_perception,
)


# ============================================================
# RP LOOP ORCHESTRATION
#
# One turn, one character:
#
#   objective scene truth
#       -> Director/perception
#       -> Character Context + Character Brain
#       -> proposed speech/thought/action
#
# IMPORTANT:
# This module stops BEFORE action resolution.
#
# The Character Brain currently returns a natural-language action
# intention. Converting that intention into a structured ActionIntent
# is a separate interpretation boundary and must be tested before it
# is allowed to reach resolver.py / executor.py.
#
# Therefore this module performs NO world mutation.
# ============================================================


@dataclass(frozen=True)
class CharacterTurnResult:
    character_id: int
    perception: dict
    director_model: str
    brain_model: str
    speech: Optional[str]
    thought: Optional[str]
    action: Optional[str]
    action_requires_interpretation: bool

    @property
    def has_public_output(self):
        return bool(
            self.speech
            or self.action
        )

    @property
    def has_any_output(self):
        return bool(
            self.speech
            or self.thought
            or self.action
        )


def run_character_turn(
    character_id,
    objective_scene,
    *,
    query=None,
    memory_limit=6,
    knowledge_limit=8,
    director_generator: Optional[Callable] = None,
    brain_generator: Optional[Callable] = None,
):
    """
    Run the first complete non-mutating RP cognition loop for one AI
    character.

    `objective_scene` is trusted, relevant Engine/orchestration truth.

    The Director filters it into this character's perception.
    Character Context is built inside run_character_brain().
    The Character Brain then proposes speech/thought/action.

    This function deliberately does NOT call resolve_action() or
    execute_resolved_action(). A natural-language brain action is not
    yet a validated engine ActionIntent.
    """
    director_kwargs = {}

    if director_generator is not None:
        director_kwargs[
            "generator"
        ] = director_generator

    director_result = (
        run_director_perception(
            character_id,
            objective_scene,
            **director_kwargs,
        )
    )

    brain_kwargs = {
        "query": query,
        "memory_limit":
            memory_limit,
        "knowledge_limit":
            knowledge_limit,
    }

    if brain_generator is not None:
        brain_kwargs[
            "generator"
        ] = brain_generator

    brain_result = run_character_brain(
        character_id,
        director_result.perception,
        **brain_kwargs,
    )

    return CharacterTurnResult(
        character_id=int(
            character_id
        ),
        perception=
            director_result.perception,
        director_model=
            director_result.model,
        brain_model=
            brain_result.model,
        speech=
            brain_result.speech,
        thought=
            brain_result.thought,
        action=
            brain_result.action,
        action_requires_interpretation=
            bool(brain_result.action),
    )
