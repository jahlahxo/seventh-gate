from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

import executor
import resolver

from action_interpreter import (
    ActionInterpretationResult,
    run_action_interpreter,
)
from actions import ResolvedAction
from rp_loop import (
    CharacterTurnResult,
    run_character_turn,
)
from scene_refresh import (
    SceneRefreshResult,
    build_scene_refresh,
)


# ============================================================
# CHARACTER ACTION CYCLE
#
#   trusted objective scene
#       -> Director / Character Context / Character Brain
#       -> natural-language intended action
#       -> Action Interpreter
#       -> ActionIntent
#       -> Resolver
#       -> ResolvedAction
#       -> Executor
#       -> authoritative world consequence
#       -> trusted scene refresh from CURRENT Engine state
#
# IMPORTANT AUTHORITY BOUNDARY:
#
# permitted_entities comes from trusted orchestration / scene refresh,
# never from Director or Character Brain output.
# ============================================================


@dataclass(frozen=True)
class CharacterActionCycleResult:
    character_id: int
    turn: CharacterTurnResult
    interpretation: Optional[
        ActionInterpretationResult
    ]
    resolved_action: Optional[
        ResolvedAction
    ]
    execution: Optional[Any]
    refresh: Optional[
        SceneRefreshResult
    ] = None

    @property
    def action_attempted(self):
        return (
            self.interpretation
            is not None
        )

    @property
    def world_event_id(self):
        if self.execution is None:
            return None

        return getattr(
            self.execution,
            "world_event_id",
            None,
        )

    @property
    def refreshed_scene(self):
        if self.refresh is None:
            return None

        return (
            self.refresh
            .objective_scene
        )


def run_character_action_cycle(
    character_id,
    objective_scene,
    *,
    permitted_entities:
        Optional[Iterable] = None,
    query=None,
    memory_limit=6,
    knowledge_limit=8,
    director_generator:
        Optional[Callable] = None,
    brain_generator:
        Optional[Callable] = None,
    interpreter_generator:
        Optional[Callable] = None,
):
    """
    Run one AI character from perception through authoritative execution,
    then rebuild the next trusted objective scene from Engine state.
    """
    turn_kwargs = {
        "query": query,
        "memory_limit":
            memory_limit,
        "knowledge_limit":
            knowledge_limit,
    }

    if director_generator is not None:
        turn_kwargs[
            "director_generator"
        ] = director_generator

    if brain_generator is not None:
        turn_kwargs[
            "brain_generator"
        ] = brain_generator

    turn = run_character_turn(
        character_id,
        objective_scene,
        **turn_kwargs,
    )

    if not turn.action:
        return CharacterActionCycleResult(
            character_id=
                int(character_id),
            turn=turn,
            interpretation=None,
            resolved_action=None,
            execution=None,
            refresh=None,
        )

    interpreter_kwargs = {
        "permitted_entities":
            permitted_entities,
    }

    if interpreter_generator is not None:
        interpreter_kwargs[
            "generator"
        ] = interpreter_generator

    interpretation = (
        run_action_interpreter(
            character_id,
            turn.action,
            **interpreter_kwargs,
        )
    )

    resolved_action = (
        resolver.resolve_action(
            interpretation.intent
        )
    )

    execution = (
        executor
        .execute_resolved_action(
            resolved_action
        )
    )

    refresh = build_scene_refresh(
        character_id,
        execution=execution,
    )

    return CharacterActionCycleResult(
        character_id=
            int(character_id),
        turn=turn,
        interpretation=
            interpretation,
        resolved_action=
            resolved_action,
        execution=execution,
        refresh=refresh,
    )
