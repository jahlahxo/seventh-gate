import json
import unittest
from unittest.mock import patch

from character_brain import (
    CharacterBrainResponse,
    build_character_brain_prompt,
    parse_character_brain_output,
    run_character_brain,
)


def fake_context(
    *,
    character_id=7,
    preferred_model="model-primary",
    fallback_models="model-fallback",
    may_invoke=True,
):
    return {
        "runtime": {
            "character_id": character_id,
            "preferred_model": preferred_model,
            "fallback_models": fallback_models,
            "may_invoke_ai_brain": may_invoke,
        }
    }


class CharacterBrainTests(unittest.TestCase):
    def test_prompt_preserves_character_context_and_adds_strict_output_contract(self):
        prompt = build_character_brain_prompt(
            "CHARACTER CONTEXT\nName: Mara"
        )

        self.assertIn(
            "CHARACTER CONTEXT",
            prompt,
        )
        self.assertIn(
            '"speech": null',
            prompt,
        )
        self.assertIn(
            "intends or attempts",
            prompt,
        )
        self.assertIn(
            "Never decide another person's",
            prompt,
        )

    def test_parser_accepts_clean_json(self):
        raw = json.dumps(
            {
                "speech": "No.",
                "thought": "I do not trust him.",
                "action": "I step away from the door.",
            }
        )

        result = parse_character_brain_output(
            7,
            "model-a",
            raw,
        )

        self.assertIsInstance(
            result,
            CharacterBrainResponse,
        )
        self.assertEqual(
            result.speech,
            "No.",
        )
        self.assertEqual(
            result.thought,
            "I do not trust him.",
        )
        self.assertEqual(
            result.action,
            "I step away from the door.",
        )

    def test_parser_accepts_json_code_fence(self):
        raw = (
            "```json\n"
            '{"speech":"Hello.","thought":null,"action":null}\n'
            "```"
        )

        result = parse_character_brain_output(
            7,
            "model-a",
            raw,
        )

        self.assertEqual(
            result.speech,
            "Hello.",
        )

    def test_parser_rejects_extra_authority_fields(self):
        raw = json.dumps(
            {
                "speech": "I shove him.",
                "thought": None,
                "action": "I try to shove him.",
                "outcome": "He falls over.",
            }
        )

        with self.assertRaises(
            ValueError
        ):
            parse_character_brain_output(
                7,
                "model-a",
                raw,
            )

    @patch(
        "character_brain.get_character_profile",
        return_value=None,
    )
    @patch(
        "character_brain.render_character_context",
        return_value="CHARACTER CONTEXT\nName: Mara",
    )
    @patch(
        "character_brain.build_character_context",
        return_value=fake_context(),
    )
    def test_run_returns_proposal_without_world_execution(
        self,
        mocked_build,
        mocked_render,
        mocked_profile,
    ):
        calls = []

        def generator(**kwargs):
            calls.append(kwargs)

            return json.dumps(
                {
                    "speech": "Stay back.",
                    "thought": "That noise frightened me.",
                    "action": "I move toward the window.",
                }
            )

        result = run_character_brain(
            7,
            {
                "current":
                    "A crash sounds outside.",
            },
            generator=generator,
        )

        self.assertEqual(
            result.model,
            "model-primary",
        )
        self.assertEqual(
            result.action,
            "I move toward the window.",
        )
        self.assertEqual(
            len(calls),
            1,
        )

        # Character Brain returns an intention as text. It does not import or
        # call resolver/executor and therefore cannot make the movement true.
        self.assertNotIn(
            "success",
            result.__dict__,
        )
        self.assertNotIn(
            "world_event_id",
            result.__dict__,
        )

    @patch(
        "character_brain.get_character_profile",
        return_value=None,
    )
    @patch(
        "character_brain.render_character_context",
        return_value="CHARACTER CONTEXT",
    )
    @patch(
        "character_brain.build_character_context",
        return_value=fake_context(
            fallback_models=(
                "model-fallback-a, model-fallback-b"
            )
        ),
    )
    def test_fallback_models_are_tried_in_order(
        self,
        mocked_build,
        mocked_render,
        mocked_profile,
    ):
        attempted = []

        def generator(**kwargs):
            attempted.append(
                kwargs["model"]
            )

            if kwargs["model"] == "model-primary":
                raise RuntimeError(
                    "primary unavailable"
                )

            return json.dumps(
                {
                    "speech": "I am here.",
                    "thought": None,
                    "action": None,
                }
            )

        result = run_character_brain(
            7,
            {"current": "Hello."},
            generator=generator,
        )

        self.assertEqual(
            attempted,
            [
                "model-primary",
                "model-fallback-a",
            ],
        )
        self.assertEqual(
            result.model,
            "model-fallback-a",
        )

    @patch(
        "character_brain.build_character_context",
        return_value=fake_context(
            may_invoke=False
        ),
    )
    def test_ineligible_character_never_calls_model(
        self,
        mocked_build,
    ):
        called = False

        def generator(**kwargs):
            nonlocal called
            called = True
            return "{}"

        with self.assertRaises(
            RuntimeError
        ):
            run_character_brain(
                7,
                {"current": "Hello."},
                generator=generator,
            )

        self.assertFalse(called)

    @patch(
        "character_brain.get_character_profile",
        return_value=None,
    )
    @patch(
        "character_brain.render_character_context",
        return_value="CHARACTER CONTEXT",
    )
    @patch(
        "character_brain.build_character_context",
        return_value=fake_context(
            preferred_model=None,
            fallback_models=None,
        ),
    )
    def test_character_requires_configured_model(
        self,
        mocked_build,
        mocked_render,
        mocked_profile,
    ):
        with self.assertRaises(
            RuntimeError
        ):
            run_character_brain(
                7,
                {"current": "Hello."},
                generator=lambda **kwargs: "{}",
            )

    @patch(
        "character_brain.get_character_profile",
        return_value=None,
    )
    @patch(
        "character_brain.render_character_context",
        return_value="CHARACTER CONTEXT",
    )
    @patch(
        "character_brain.build_character_context",
        return_value=fake_context(),
    )
    def test_all_model_failures_are_reported_without_fabricating_response(
        self,
        mocked_build,
        mocked_render,
        mocked_profile,
    ):
        def generator(**kwargs):
            raise RuntimeError(
                "generation unavailable"
            )

        with self.assertRaises(
            RuntimeError
        ) as caught:
            run_character_brain(
                7,
                {"current": "Hello."},
                generator=generator,
            )

        message = str(
            caught.exception
        )

        self.assertIn(
            "model-primary",
            message,
        )
        self.assertIn(
            "model-fallback",
            message,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
