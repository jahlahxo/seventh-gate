from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from character_brain import (
    run_character_brain,
)
from director import (
    run_director_perception,
)
from rp_text import (
    render_story_turn,
)


@dataclass(
    frozen=True,
    init=False,
)
class CharacterTurnResult:
    character_id: int
    perception: dict
    director_model: str
    brain_model: str
    public: Optional[str]
    thought: Optional[str]
    action: Optional[str]
    open_threads: tuple[str, ...]
    resolve_thread_ids: tuple[int, ...]
    action_requires_interpretation: bool

    def __init__(
        self,
        character_id,
        perception,
        director_model,
        brain_model,
        public=None,
        thought=None,
        action=None,
        open_threads=(),
        resolve_thread_ids=(),
        action_requires_interpretation=None,
        speech=None,
    ):
        """
        `speech` is a compatibility alias for older tests/tools.

        New Seventh Gate code should use `public`, because the public field may
        contain natural story prose mixing action/narration and quoted dialogue.
        """
        if public is None:
            public = speech
        elif (
            speech is not None
            and str(public).strip()
            != str(speech).strip()
        ):
            raise ValueError(
                "public and legacy speech values disagree."
            )

        if action_requires_interpretation is None:
            action_requires_interpretation = bool(
                action
            )

        object.__setattr__(
            self,
            "character_id",
            int(character_id),
        )
        object.__setattr__(
            self,
            "perception",
            perception,
        )
        object.__setattr__(
            self,
            "director_model",
            str(director_model),
        )
        object.__setattr__(
            self,
            "brain_model",
            str(brain_model),
        )
        object.__setattr__(
            self,
            "public",
            (
                None
                if public is None
                else str(public).strip() or None
            ),
        )
        object.__setattr__(
            self,
            "thought",
            (
                None
                if thought is None
                else str(thought).strip() or None
            ),
        )
        object.__setattr__(
            self,
            "action",
            (
                None
                if action is None
                else str(action).strip() or None
            ),
        )
        object.__setattr__(
            self,
            "open_threads",
            tuple(
                open_threads
                or ()
            ),
        )
        object.__setattr__(
            self,
            "resolve_thread_ids",
            tuple(
                int(value)
                for value
                in (
                    resolve_thread_ids
                    or ()
                )
            ),
        )
        object.__setattr__(
            self,
            "action_requires_interpretation",
            bool(
                action_requires_interpretation
            ),
        )

    @property
    def speech(self):
        """
        Backward-compatible alias. New code should use `.public`.
        """
        return self.public

    @property
    def discord_text(self):
        return render_story_turn(
            self.public,
            self.thought,
        )

    @property
    def has_public_output(self):
        return bool(
            self.public
        )

    @property
    def has_any_output(self):
        return bool(
            self.public
            or self.thought
            or self.action
            or self.open_threads
            or self.resolve_thread_ids
        )


def run_character_turn(
    character_id,
    objective_scene,
    *,
    query=None,
    memory_limit=6,
    knowledge_limit=8,
    director_generator:
        Optional[Callable] = None,
    brain_generator:
        Optional[Callable] = None,
):
    """
    Run one non-mutating cognition turn.

    Public story prose, private thought and mechanical action intent remain
    separate. Accepted turns are committed by the orchestration layer later.
    """
    director_kwargs = {}

    if (
        director_generator
        is not None
    ):
        director_kwargs[
            "generator"
        ] = (
            director_generator
        )

    director_result = (
        run_director_perception(
            character_id,
            objective_scene,
            **director_kwargs,
        )
    )

    brain_kwargs = {
        "query":
            query,
        "memory_limit":
            memory_limit,
        "knowledge_limit":
            knowledge_limit,
    }

    if (
        brain_generator
        is not None
    ):
        brain_kwargs[
            "generator"
        ] = (
            brain_generator
        )

    brain_result = (
        run_character_brain(
            character_id,
            director_result.perception,
            **brain_kwargs,
        )
    )

    return CharacterTurnResult(
        character_id=
            int(character_id),
        perception=
            director_result.perception,
        director_model=
            director_result.model,
        brain_model=
            brain_result.model,
        public=
            brain_result.public,
        thought=
            brain_result.thought,
        action=
            brain_result.action,
        open_threads=
            brain_result.open_threads,
        resolve_thread_ids=
            brain_result.resolve_thread_ids,
        action_requires_interpretation=
            bool(
                brain_result.action
            ),
    )
