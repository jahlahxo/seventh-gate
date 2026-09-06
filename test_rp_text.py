import unittest

from rp_text import (
    parse_story_post,
    render_story_turn,
)


class RPTextTests(unittest.TestCase):
    def test_mixed_action_and_dialogue_remain_one_public_story(self):
        parsed = parse_story_post(
            'Anna walks to the door and knocks. "Is anyone home?"'
        )
        self.assertEqual(
            parsed.public_text,
            'Anna walks to the door and knocks. "Is anyone home?"',
        )

    def test_italic_thought_is_removed_from_observable_text(self):
        parsed = parse_story_post(
            'Anna smiles. "Fine." *I do not believe him.*'
        )
        self.assertEqual(
            parsed.public_text,
            'Anna smiles. "Fine."',
        )
        self.assertEqual(
            parsed.thoughts,
            ("I do not believe him.",),
        )

    def test_multiple_private_thoughts_are_extracted(self):
        parsed = parse_story_post(
            '*Too quiet.* Anna opens the door. *Bad idea.*'
        )
        self.assertEqual(
            parsed.public_text,
            "Anna opens the door.",
        )
        self.assertEqual(
            parsed.thoughts,
            (
                "Too quiet.",
                "Bad idea.",
            ),
        )

    def test_renderer_puts_private_thought_in_discord_italics(self):
        rendered = render_story_turn(
            'Antti shrugs. "Maybe."',
            "This will end badly.",
        )
        self.assertEqual(
            rendered,
            'Antti shrugs. "Maybe."\n*This will end badly.*',
        )

    def test_bold_markdown_is_not_mistaken_for_thought(self):
        parsed = parse_story_post(
            'Anna says, "**Absolutely not.**"'
        )
        self.assertEqual(
            parsed.public_text,
            'Anna says, "**Absolutely not.**"',
        )
        self.assertEqual(
            parsed.thoughts,
            (),
        )

    def test_plain_post_has_no_private_component(self):
        parsed = parse_story_post(
            "Anna sits beside the stove."
        )
        self.assertEqual(
            parsed.public_text,
            "Anna sits beside the stove.",
        )
        self.assertFalse(
            parsed.thoughts
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
