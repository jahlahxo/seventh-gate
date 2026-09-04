import json
import tempfile
import unittest
from pathlib import Path

import database
from actions import (
    ActionIntent,
    ActionType,
    make_entity,
)
from action_interpreter import (
    ActionInterpretationResult,
    build_action_interpreter_prompt,
    parse_action_interpretation,
    run_action_interpreter,
)
from campaign import set_campaign_setting


class ActionInterpreterTests(
    unittest.TestCase
):
    def setUp(self):
        self.tmp = (
            tempfile.TemporaryDirectory()
        )

        database.set_database_path(
            Path(self.tmp.name)
            / "action_interpreter.db"
        )

        database.initialize_database()

        set_campaign_setting(
            "director_model",
            "director-primary",
        )

        set_campaign_setting(
            "director_fallback_models",
            "director-fallback",
        )

        self.door = make_entity(
            "object",
            12,
            "oak door",
        )

        self.elias = make_entity(
            "character",
            4,
            "Elias",
        )

        self.barn = make_entity(
            "location",
            9,
            "barn",
        )

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_prompt_fixes_actor_and_lists_only_permitted_references(self):
        prompt = (
            build_action_interpreter_prompt(
                7,
                "I try to open the oak door.",
                [
                    self.door,
                    self.elias,
                ],
            )
        )

        self.assertIn(
            "Actor is fixed as character:7",
            prompt,
        )

        self.assertIn(
            "object:12",
            prompt,
        )

        self.assertIn(
            "character:4",
            prompt,
        )

        self.assertNotIn(
            "location:9",
            prompt,
        )

    def test_parse_open_action_builds_engine_action_intent(self):
        raw = json.dumps(
            {
                "action_type": "open",
                "target_ref":
                    "object:12",
                "destination_ref":
                    None,
                "instrument_ref":
                    None,
            }
        )

        result = (
            parse_action_interpretation(
                7,
                (
                    "I try to open "
                    "the oak door."
                ),
                "director-primary",
                raw,
                permitted_entities=[
                    self.door
                ],
            )
        )

        self.assertIsInstance(
            result,
            ActionInterpretationResult,
        )

        self.assertIsInstance(
            result.intent,
            ActionIntent,
        )

        self.assertEqual(
            result.intent.action_type,
            ActionType.OPEN,
        )

        self.assertEqual(
            result.intent.actor.entity_type,
            "character",
        )

        self.assertEqual(
            result.intent.actor.entity_id,
            "7",
        )

        self.assertEqual(
            result.intent.target.entity_id,
            "12",
        )

    def test_actor_cannot_be_supplied_or_overridden_by_model(self):
        raw = json.dumps(
            {
                "action_type": "open",
                "target_ref":
                    "object:12",
                "destination_ref":
                    None,
                "instrument_ref":
                    None,
                "actor_ref":
                    "character:999",
            }
        )

        with self.assertRaises(
            ValueError
        ):
            parse_action_interpretation(
                7,
                "I open it.",
                "director-primary",
                raw,
                permitted_entities=[
                    self.door
                ],
            )

    def test_unpermitted_target_reference_is_rejected(self):
        raw = json.dumps(
            {
                "action_type": "grab",
                "target_ref":
                    "character:999",
                "destination_ref":
                    None,
                "instrument_ref":
                    None,
            }
        )

        with self.assertRaises(
            ValueError
        ):
            parse_action_interpretation(
                7,
                "I try to grab him.",
                "director-primary",
                raw,
                permitted_entities=[
                    self.elias
                ],
            )

    def test_outcome_and_mechanical_metadata_are_rejected(self):
        raw = json.dumps(
            {
                "action_type": "open",
                "target_ref":
                    "object:12",
                "destination_ref":
                    None,
                "instrument_ref":
                    None,
                "success": True,
                "difficulty": 1,
            }
        )

        with self.assertRaises(
            ValueError
        ):
            parse_action_interpretation(
                7,
                "I open the door.",
                "director-primary",
                raw,
                permitted_entities=[
                    self.door
                ],
            )

    def test_destination_can_be_structured_without_becoming_movement_truth(self):
        raw = json.dumps(
            {
                "action_type": "move",
                "target_ref": None,
                "destination_ref":
                    "location:9",
                "instrument_ref":
                    None,
            }
        )

        result = (
            parse_action_interpretation(
                7,
                "I head toward the barn.",
                "director-primary",
                raw,
                permitted_entities=[
                    self.barn
                ],
            )
        )

        self.assertEqual(
            result.intent.destination.entity_id,
            "9",
        )

        self.assertFalse(
            hasattr(
                result,
                "resolved_action",
            )
        )

        self.assertFalse(
            hasattr(
                result,
                "execution_result",
            )
        )

    def test_invalid_action_type_is_rejected(self):
        raw = json.dumps(
            {
                "action_type":
                    "teleport_reality",
                "target_ref": None,
                "destination_ref":
                    None,
                "instrument_ref":
                    None,
            }
        )

        with self.assertRaises(
            ValueError
        ):
            parse_action_interpretation(
                7,
                "I teleport.",
                "director-primary",
                raw,
            )

    def test_run_uses_director_models_and_fallback(self):
        attempted = []

        def generator(**kwargs):
            attempted.append(
                kwargs["model"]
            )

            if (
                kwargs["model"]
                == "director-primary"
            ):
                raise RuntimeError(
                    "primary unavailable"
                )

            return json.dumps(
                {
                    "action_type":
                        "open",
                    "target_ref":
                        "object:12",
                    "destination_ref":
                        None,
                    "instrument_ref":
                        None,
                }
            )

        result = run_action_interpreter(
            7,
            "I try to open the oak door.",
            permitted_entities=[
                self.door
            ],
            generator=generator,
        )

        self.assertEqual(
            attempted,
            [
                "director-primary",
                "director-fallback",
            ],
        )

        self.assertEqual(
            result.model,
            "director-fallback",
        )

    def test_interpreter_does_not_call_resolver_or_executor(self):
        calls = []

        def generator(**kwargs):
            calls.append(
                kwargs["model"]
            )

            return json.dumps(
                {
                    "action_type":
                        "grab",
                    "target_ref":
                        "character:4",
                    "destination_ref":
                        None,
                    "instrument_ref":
                        None,
                }
            )

        result = run_action_interpreter(
            7,
            "I try to grab Elias.",
            permitted_entities=[
                self.elias
            ],
            generator=generator,
        )

        self.assertEqual(
            result.intent.action_type,
            ActionType.GRAB,
        )

        self.assertFalse(
            hasattr(
                result,
                "success",
            )
        )

        self.assertFalse(
            hasattr(
                result,
                "world_event_id",
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
