import json
import unittest
from unittest.mock import patch

from character_brain import (
    build_character_brain_prompt,
    parse_character_brain_output,
)
from director import (
    build_director_prompt,
)


class StoryBrainTests(unittest.TestCase):
    def test_prompt_uses_natural_story_prose_not_line_types(self):
        prompt = build_character_brain_prompt(
            "CHARACTER CONTEXT"
        )
        self.assertIn(
            "Actions/narration are ordinary text",
            prompt,
        )
        self.assertIn(
            "spoken words appear naturally inside quotation marks",
            prompt,
        )
        self.assertIn(
            "Do NOT split",
            prompt,
        )

    def test_silence_and_no_automatic_greeting_are_explicit(self):
        prompt = build_character_brain_prompt(
            "CHARACTER CONTEXT"
        )
        self.assertIn(
            "not required to answer every perceived message",
            prompt,
        )
        self.assertIn(
            "Do not automatically greet",
            prompt,
        )

    def test_character_may_initiate_based_on_own_motives(self):
        prompt = build_character_brain_prompt(
            "CHARACTER CONTEXT"
        )
        self.assertIn(
            "You may initiate conversation",
            prompt,
        )
        self.assertIn(
            "Do not exist only to react",
            prompt,
        )

    def test_prompt_discourages_repetitive_trait_performance(self):
        prompt = build_character_brain_prompt(
            "CHARACTER CONTEXT"
        )
        self.assertIn(
            "Do not overperform signature traits",
            prompt,
        )
        self.assertIn(
            "Avoid repeating the same phrase",
            prompt,
        )

    def test_italic_text_returned_in_public_becomes_private(self):
        raw = json.dumps({
            "public":
                'Antti shrugs. "Fine." *I hate this plan.*',
            "thought": None,
            "action": None,
            "open_threads": [],
            "resolve_thread_ids": [],
        })

        result = parse_character_brain_output(
            1,
            "model",
            raw,
        )

        self.assertEqual(
            result.public,
            'Antti shrugs. "Fine."',
        )
        self.assertEqual(
            result.thought,
            "I hate this plan.",
        )

    def test_parser_accepts_continuity_thread_updates(self):
        raw = json.dumps({
            "public": None,
            "thought":
                "I should remember that.",
            "action": None,
            "open_threads": [
                "Meet Kaisa outside."
            ],
            "resolve_thread_ids": [
                4,
                7,
            ],
        })

        result = parse_character_brain_output(
            1,
            "model",
            raw,
        )

        self.assertEqual(
            result.open_threads,
            (
                "Meet Kaisa outside.",
            ),
        )
        self.assertEqual(
            result.resolve_thread_ids,
            (
                4,
                7,
            ),
        )

    @patch(
        "director.get_director_perception_constraints",
        return_value=None,
    )
    @patch(
        "director.build_world_grounding",
        return_value=None,
    )
    @patch(
        "director.build_social_grounding",
        return_value=None,
    )
    def test_director_filters_without_exposition_dump(
        self,
        mocked_social,
        mocked_world,
        mocked_development,
    ):
        prompt = build_director_prompt(
            1,
            {
                "event":
                    "Someone opens the door."
            },
        )

        self.assertIn(
            "Do not dump the whole room",
            prompt,
        )
        self.assertIn(
            "through interaction rather than exposition",
            prompt,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
