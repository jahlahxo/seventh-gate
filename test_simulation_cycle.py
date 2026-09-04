import unittest
from unittest.mock import (
    patch,
    sentinel,
)

from action_interpreter import (
    ActionInterpretationResult,
)
from actions import (
    ActionType,
    make_action,
    make_entity,
)
from rp_loop import (
    CharacterTurnResult,
)
from scene_refresh import (
    SceneRefreshResult,
)
from simulation_cycle import (
    CharacterActionCycleResult,
    run_character_action_cycle,
)


def make_turn(
    *,
    character_id=7,
    action=(
        "I try to open the oak door."
    ),
    perception=None,
):
    if perception is None:
        perception = {
            "current":
                "An oak door stands ahead.",
            "environment": None,
            "people": [],
            "objects": [],
            "recent": [],
            "private": [],
        }

    return CharacterTurnResult(
        character_id=character_id,
        perception=perception,
        director_model=
            "director-model",
        brain_model="brain-model",
        speech=None,
        thought=(
            "I should see what is "
            "beyond it."
        ),
        action=action,
        action_requires_interpretation=
            bool(action),
    )


def make_interpretation(
    *,
    character_id=7,
):
    actor = make_entity(
        "character",
        character_id,
    )

    door = make_entity(
        "object",
        12,
        "oak door",
    )

    intent = make_action(
        ActionType.OPEN,
        actor=actor,
        description=(
            "I try to open the oak door."
        ),
        target=door,
        source_type=
            "character_brain",
        source_id=
            str(character_id),
    )

    return ActionInterpretationResult(
        character_id=
            character_id,
        model="director-model",
        intent=intent,
        raw_text="{}",
    )


def make_refresh(
    character_id=7,
):
    return SceneRefreshResult(
        character_id=
            character_id,
        location_id=4,
        objective_scene={
            "location": {
                "name":
                    "Refreshed Room"
            }
        },
        permitted_entities=(),
        source_world_event_id=321,
    )


class SimulationCycleTests(
    unittest.TestCase
):
    @patch(
        "simulation_cycle.build_scene_refresh",
        return_value=make_refresh(),
    )
    @patch(
        "simulation_cycle.executor.execute_resolved_action"
    )
    @patch(
        "simulation_cycle.resolver.resolve_action"
    )
    @patch(
        "simulation_cycle.run_action_interpreter"
    )
    @patch(
        "simulation_cycle.run_character_turn"
    )
    def test_full_cycle_runs_in_authority_order(
        self,
        mocked_turn,
        mocked_interpreter,
        mocked_resolver,
        mocked_executor,
        mocked_refresh,
    ):
        order = []

        turn = make_turn()
        interpretation = (
            make_interpretation()
        )

        def turn_side_effect(
            *args,
            **kwargs,
        ):
            order.append("turn")
            return turn

        def interpreter_side_effect(
            *args,
            **kwargs,
        ):
            order.append(
                "interpreter"
            )
            return interpretation

        def resolver_side_effect(
            *args,
            **kwargs,
        ):
            order.append(
                "resolver"
            )
            return sentinel.resolved

        def executor_side_effect(
            *args,
            **kwargs,
        ):
            order.append(
                "executor"
            )
            return sentinel.execution

        def refresh_side_effect(
            *args,
            **kwargs,
        ):
            order.append(
                "refresh"
            )
            return make_refresh()

        mocked_turn.side_effect = (
            turn_side_effect
        )
        mocked_interpreter.side_effect = (
            interpreter_side_effect
        )
        mocked_resolver.side_effect = (
            resolver_side_effect
        )
        mocked_executor.side_effect = (
            executor_side_effect
        )
        mocked_refresh.side_effect = (
            refresh_side_effect
        )

        result = (
            run_character_action_cycle(
                7,
                {
                    "event":
                        "A door is present."
                },
            )
        )

        self.assertEqual(
            order,
            [
                "turn",
                "interpreter",
                "resolver",
                "executor",
                "refresh",
            ],
        )

        self.assertIs(
            result.resolved_action,
            sentinel.resolved,
        )
        self.assertIs(
            result.execution,
            sentinel.execution,
        )

    @patch(
        "simulation_cycle.build_scene_refresh"
    )
    @patch(
        "simulation_cycle.executor.execute_resolved_action"
    )
    @patch(
        "simulation_cycle.resolver.resolve_action"
    )
    @patch(
        "simulation_cycle.run_action_interpreter"
    )
    @patch(
        "simulation_cycle.run_character_turn"
    )
    def test_no_brain_action_stops_before_interpretation(
        self,
        mocked_turn,
        mocked_interpreter,
        mocked_resolver,
        mocked_executor,
        mocked_refresh,
    ):
        mocked_turn.return_value = (
            make_turn(
                action=None
            )
        )

        result = (
            run_character_action_cycle(
                7,
                {
                    "event":
                        "Quiet room."
                },
            )
        )

        mocked_interpreter.assert_not_called()
        mocked_resolver.assert_not_called()
        mocked_executor.assert_not_called()
        mocked_refresh.assert_not_called()

        self.assertFalse(
            result.action_attempted
        )
        self.assertIsNone(
            result.interpretation
        )
        self.assertIsNone(
            result.resolved_action
        )
        self.assertIsNone(
            result.execution
        )
        self.assertIsNone(
            result.refresh
        )

    @patch(
        "simulation_cycle.build_scene_refresh",
        return_value=make_refresh(),
    )
    @patch(
        "simulation_cycle.executor.execute_resolved_action",
        return_value=
            sentinel.execution,
    )
    @patch(
        "simulation_cycle.resolver.resolve_action",
        return_value=
            sentinel.resolved,
    )
    @patch(
        "simulation_cycle.run_action_interpreter",
        return_value=
            make_interpretation(),
    )
    @patch(
        "simulation_cycle.run_character_turn",
        return_value=make_turn(
            perception={
                "current":
                    "A model-described scene.",
                "environment": None,
                "people": [],
                "objects": [
                    {
                        "name":
                            "hallucinated key",
                        "entity_id":
                            "999999",
                    }
                ],
                "recent": [],
                "private": [],
            },
        ),
    )
    def test_permitted_entities_come_only_from_trusted_argument(
        self,
        mocked_turn,
        mocked_interpreter,
        mocked_resolver,
        mocked_executor,
        mocked_refresh,
    ):
        trusted_door = (
            make_entity(
                "object",
                12,
                "oak door",
            )
        )

        trusted = [
            trusted_door
        ]

        run_character_action_cycle(
            7,
            {
                "event":
                    "Engine scene."
            },
            permitted_entities=
                trusted,
        )

        _, kwargs = (
            mocked_interpreter
            .call_args
        )

        self.assertIs(
            kwargs[
                "permitted_entities"
            ],
            trusted,
        )

        self.assertNotIn(
            "999999",
            repr(
                kwargs[
                    "permitted_entities"
                ]
            ),
        )

    @patch(
        "simulation_cycle.build_scene_refresh"
    )
    @patch(
        "simulation_cycle.executor.execute_resolved_action"
    )
    @patch(
        "simulation_cycle.resolver.resolve_action"
    )
    @patch(
        "simulation_cycle.run_action_interpreter",
        side_effect=ValueError(
            "Unpermitted reference."
        ),
    )
    @patch(
        "simulation_cycle.run_character_turn",
        return_value=make_turn(),
    )
    def test_interpreter_failure_prevents_resolution_and_execution(
        self,
        mocked_turn,
        mocked_interpreter,
        mocked_resolver,
        mocked_executor,
        mocked_refresh,
    ):
        with self.assertRaises(
            ValueError
        ):
            run_character_action_cycle(
                7,
                {
                    "event":
                        "Door."
                },
            )

        mocked_resolver.assert_not_called()
        mocked_executor.assert_not_called()
        mocked_refresh.assert_not_called()

    @patch(
        "simulation_cycle.build_scene_refresh",
        return_value=make_refresh(),
    )
    @patch(
        "simulation_cycle.executor.execute_resolved_action",
        return_value=
            sentinel.execution,
    )
    @patch(
        "simulation_cycle.resolver.resolve_action",
        return_value=
            sentinel.resolved,
    )
    @patch(
        "simulation_cycle.run_action_interpreter",
        return_value=
            make_interpretation(),
    )
    @patch(
        "simulation_cycle.run_character_turn",
        return_value=make_turn(
            action=(
                "I open it easily and "
                "the door swings wide."
            )
        ),
    )
    def test_executor_receives_resolver_output_not_brain_prose(
        self,
        mocked_turn,
        mocked_interpreter,
        mocked_resolver,
        mocked_executor,
        mocked_refresh,
    ):
        run_character_action_cycle(
            7,
            {
                "event":
                    "Door."
            },
        )

        mocked_resolver.assert_called_once_with(
            mocked_interpreter
            .return_value
            .intent
        )

        mocked_executor.assert_called_once_with(
            sentinel.resolved
        )

    @patch(
        "simulation_cycle.run_character_turn",
        return_value=
            make_turn(
                action=None
            ),
    )
    def test_turn_options_are_forwarded(
        self,
        mocked_turn,
    ):
        director_generator = (
            sentinel
            .director_generator
        )
        brain_generator = (
            sentinel
            .brain_generator
        )

        run_character_action_cycle(
            9,
            {
                "event":
                    "Something happens."
            },
            query="door",
            memory_limit=3,
            knowledge_limit=4,
            director_generator=
                director_generator,
            brain_generator=
                brain_generator,
        )

        mocked_turn.assert_called_once_with(
            9,
            {
                "event":
                    "Something happens."
            },
            query="door",
            memory_limit=3,
            knowledge_limit=4,
            director_generator=
                director_generator,
            brain_generator=
                brain_generator,
        )

    @patch(
        "simulation_cycle.build_scene_refresh",
        return_value=make_refresh(),
    )
    @patch(
        "simulation_cycle.executor.execute_resolved_action",
        return_value=
            sentinel.execution,
    )
    @patch(
        "simulation_cycle.resolver.resolve_action",
        return_value=
            sentinel.resolved,
    )
    @patch(
        "simulation_cycle.run_action_interpreter",
        return_value=
            make_interpretation(),
    )
    @patch(
        "simulation_cycle.run_character_turn",
        return_value=make_turn(),
    )
    def test_interpreter_generator_is_forwarded(
        self,
        mocked_turn,
        mocked_interpreter,
        mocked_resolver,
        mocked_executor,
        mocked_refresh,
    ):
        generator = (
            sentinel
            .interpreter_generator
        )

        run_character_action_cycle(
            7,
            {
                "event":
                    "Door."
            },
            interpreter_generator=
                generator,
        )

        _, kwargs = (
            mocked_interpreter
            .call_args
        )

        self.assertIs(
            kwargs[
                "generator"
            ],
            generator,
        )

    @patch(
        "simulation_cycle.build_scene_refresh"
    )
    @patch(
        "simulation_cycle.executor.execute_resolved_action"
    )
    @patch(
        "simulation_cycle.resolver.resolve_action"
    )
    @patch(
        "simulation_cycle.run_action_interpreter"
    )
    @patch(
        "simulation_cycle.run_character_turn"
    )
    def test_result_preserves_every_stage_and_world_event(
        self,
        mocked_turn,
        mocked_interpreter,
        mocked_resolver,
        mocked_executor,
        mocked_refresh,
    ):
        turn = make_turn()
        interpretation = (
            make_interpretation()
        )

        class FakeExecution:
            world_event_id = 321

        execution = FakeExecution()
        refresh = make_refresh()

        mocked_turn.return_value = (
            turn
        )
        mocked_interpreter.return_value = (
            interpretation
        )
        mocked_resolver.return_value = (
            sentinel.resolved
        )
        mocked_executor.return_value = (
            execution
        )
        mocked_refresh.return_value = (
            refresh
        )

        result = (
            run_character_action_cycle(
                7,
                {
                    "event":
                        "Door."
                },
            )
        )

        self.assertIsInstance(
            result,
            CharacterActionCycleResult,
        )
        self.assertIs(
            result.turn,
            turn,
        )
        self.assertIs(
            result.interpretation,
            interpretation,
        )
        self.assertIs(
            result.resolved_action,
            sentinel.resolved,
        )
        self.assertIs(
            result.execution,
            execution,
        )
        self.assertIs(
            result.refresh,
            refresh,
        )
        self.assertTrue(
            result.action_attempted
        )
        self.assertEqual(
            result.world_event_id,
            321,
        )
        self.assertEqual(
            result.refreshed_scene[
                "location"
            ]["name"],
            "Refreshed Room",
        )

    @patch(
        "simulation_cycle.build_scene_refresh",
        return_value=make_refresh(),
    )
    @patch(
        "simulation_cycle.executor.execute_resolved_action",
        return_value=
            sentinel.execution,
    )
    @patch(
        "simulation_cycle.resolver.resolve_action",
        return_value=
            sentinel.resolved,
    )
    @patch(
        "simulation_cycle.run_action_interpreter",
        return_value=
            make_interpretation(),
    )
    @patch(
        "simulation_cycle.run_character_turn",
        return_value=make_turn(),
    )
    def test_refresh_receives_authoritative_execution_result(
        self,
        mocked_turn,
        mocked_interpreter,
        mocked_resolver,
        mocked_executor,
        mocked_refresh,
    ):
        run_character_action_cycle(
            7,
            {
                "event":
                    "Door."
            },
        )

        mocked_refresh.assert_called_once_with(
            7,
            execution=
                sentinel.execution,
        )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
