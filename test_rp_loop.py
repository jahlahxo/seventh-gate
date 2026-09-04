import unittest
from unittest.mock import patch

from character_brain import (
    CharacterBrainResponse,
)
from director import (
    DirectorPerceptionResult,
)
from rp_loop import (
    CharacterTurnResult,
    run_character_turn,
)


class RPLoopTests(unittest.TestCase):
    @patch(
        "rp_loop.run_character_brain",
    )
    @patch(
        "rp_loop.run_director_perception",
    )
    def test_full_cognition_chain_passes_director_perception_to_brain(
        self,
        mocked_director,
        mocked_brain,
    ):
        perception = {
            "current":
                "A knock sounds at the door.",
            "environment":
                "Rain taps the roof.",
            "people": [],
            "objects": [],
            "recent": [],
            "private": [],
        }

        mocked_director.return_value = (
            DirectorPerceptionResult(
                character_id=7,
                model="director-model",
                perception=perception,
                raw_text="{}",
            )
        )

        mocked_brain.return_value = (
            CharacterBrainResponse(
                character_id=7,
                model="brain-model",
                speech="Who is it?",
                thought=(
                    "I was not expecting anyone."
                ),
                action=(
                    "I move toward the door."
                ),
                raw_text="{}",
            )
        )

        result = run_character_turn(
            7,
            {
                "event":
                    "Someone knocks on the door."
            },
        )

        mocked_brain.assert_called_once()

        args, kwargs = (
            mocked_brain.call_args
        )

        self.assertEqual(
            args[0],
            7,
        )

        self.assertEqual(
            args[1],
            perception,
        )

        self.assertEqual(
            result.speech,
            "Who is it?",
        )

    @patch(
        "rp_loop.run_character_brain",
    )
    @patch(
        "rp_loop.run_director_perception",
    )
    def test_turn_result_preserves_models_and_private_thought(
        self,
        mocked_director,
        mocked_brain,
    ):
        mocked_director.return_value = (
            DirectorPerceptionResult(
                character_id=3,
                model="director-a",
                perception={
                    "current": "Hello.",
                    "environment": None,
                    "people": [],
                    "objects": [],
                    "recent": [],
                    "private": [],
                },
                raw_text="{}",
            )
        )

        mocked_brain.return_value = (
            CharacterBrainResponse(
                character_id=3,
                model="brain-b",
                speech="Hello.",
                thought="I know that voice.",
                action=None,
                raw_text="{}",
            )
        )

        result = run_character_turn(
            3,
            {"event": "A greeting."},
        )

        self.assertIsInstance(
            result,
            CharacterTurnResult,
        )

        self.assertEqual(
            result.director_model,
            "director-a",
        )

        self.assertEqual(
            result.brain_model,
            "brain-b",
        )

        self.assertEqual(
            result.thought,
            "I know that voice.",
        )

        self.assertFalse(
            result.action_requires_interpretation,
        )

    @patch(
        "rp_loop.run_character_brain",
    )
    @patch(
        "rp_loop.run_director_perception",
    )
    def test_brain_action_is_marked_for_interpretation_not_execution(
        self,
        mocked_director,
        mocked_brain,
    ):
        mocked_director.return_value = (
            DirectorPerceptionResult(
                character_id=9,
                model="director",
                perception={
                    "current": "The door is closed.",
                    "environment": None,
                    "people": [],
                    "objects": [
                        "a closed door"
                    ],
                    "recent": [],
                    "private": [],
                },
                raw_text="{}",
            )
        )

        mocked_brain.return_value = (
            CharacterBrainResponse(
                character_id=9,
                model="brain",
                speech=None,
                thought=None,
                action=(
                    "I try to open the door."
                ),
                raw_text="{}",
            )
        )

        result = run_character_turn(
            9,
            {"door_state": "closed"},
        )

        self.assertEqual(
            result.action,
            "I try to open the door.",
        )

        self.assertTrue(
            result.action_requires_interpretation,
        )

        self.assertFalse(
            hasattr(
                result,
                "execution_result",
            )
        )

        self.assertFalse(
            hasattr(
                result,
                "resolved_action",
            )
        )

    @patch(
        "rp_loop.run_character_brain",
    )
    @patch(
        "rp_loop.run_director_perception",
    )
    def test_no_action_requires_no_interpretation(
        self,
        mocked_director,
        mocked_brain,
    ):
        mocked_director.return_value = (
            DirectorPerceptionResult(
                character_id=2,
                model="director",
                perception={
                    "current": "Quiet.",
                    "environment": None,
                    "people": [],
                    "objects": [],
                    "recent": [],
                    "private": [],
                },
                raw_text="{}",
            )
        )

        mocked_brain.return_value = (
            CharacterBrainResponse(
                character_id=2,
                model="brain",
                speech=None,
                thought="I should wait.",
                action=None,
                raw_text="{}",
            )
        )

        result = run_character_turn(
            2,
            {"event": "Nothing changes."},
        )

        self.assertFalse(
            result.action_requires_interpretation,
        )

        self.assertFalse(
            result.has_public_output,
        )

        self.assertTrue(
            result.has_any_output,
        )

    @patch(
        "rp_loop.run_character_brain",
    )
    @patch(
        "rp_loop.run_director_perception",
    )
    def test_query_and_memory_limits_are_forwarded_to_character_brain(
        self,
        mocked_director,
        mocked_brain,
    ):
        mocked_director.return_value = (
            DirectorPerceptionResult(
                character_id=5,
                model="director",
                perception={
                    "current": "A bell rings.",
                    "environment": None,
                    "people": [],
                    "objects": [],
                    "recent": [],
                    "private": [],
                },
                raw_text="{}",
            )
        )

        mocked_brain.return_value = (
            CharacterBrainResponse(
                character_id=5,
                model="brain",
                speech=None,
                thought=None,
                action=None,
                raw_text="{}",
            )
        )

        run_character_turn(
            5,
            {"event": "A bell rings."},
            query="church bell",
            memory_limit=4,
            knowledge_limit=3,
        )

        _, kwargs = (
            mocked_brain.call_args
        )

        self.assertEqual(
            kwargs["query"],
            "church bell",
        )

        self.assertEqual(
            kwargs["memory_limit"],
            4,
        )

        self.assertEqual(
            kwargs["knowledge_limit"],
            3,
        )

    @patch(
        "rp_loop.run_character_brain",
    )
    @patch(
        "rp_loop.run_director_perception",
    )
    def test_custom_generators_are_forwarded_without_live_calls(
        self,
        mocked_director,
        mocked_brain,
    ):
        director_generator = object()
        brain_generator = object()

        mocked_director.return_value = (
            DirectorPerceptionResult(
                character_id=4,
                model="director",
                perception={
                    "current": "Test.",
                    "environment": None,
                    "people": [],
                    "objects": [],
                    "recent": [],
                    "private": [],
                },
                raw_text="{}",
            )
        )

        mocked_brain.return_value = (
            CharacterBrainResponse(
                character_id=4,
                model="brain",
                speech=None,
                thought=None,
                action=None,
                raw_text="{}",
            )
        )

        run_character_turn(
            4,
            {"event": "Test."},
            director_generator=
                director_generator,
            brain_generator=
                brain_generator,
        )

        _, director_kwargs = (
            mocked_director.call_args
        )

        _, brain_kwargs = (
            mocked_brain.call_args
        )

        self.assertIs(
            director_kwargs[
                "generator"
            ],
            director_generator,
        )

        self.assertIs(
            brain_kwargs[
                "generator"
            ],
            brain_generator,
        )

    @patch(
        "rp_loop.run_character_brain",
    )
    @patch(
        "rp_loop.run_director_perception",
    )
    def test_director_failure_stops_before_character_brain(
        self,
        mocked_director,
        mocked_brain,
    ):
        mocked_director.side_effect = (
            RuntimeError(
                "Director unavailable"
            )
        )

        with self.assertRaises(
            RuntimeError
        ):
            run_character_turn(
                1,
                {"event": "Test."},
            )

        mocked_brain.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
