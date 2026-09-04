import unittest
from character_brain import build_character_brain_prompt

class CharacterProfileBrainTests(unittest.TestCase):
    def test_authored_profile_is_in_brain_prompt(self):
        prompt=build_character_brain_prompt(
            "CHARACTER CONTEXT\nName: Test",
            profile_text="Never become a generic assistant."
        )
        self.assertIn("AUTHORED CHARACTER PROFILE",prompt)
        self.assertIn("Never become a generic assistant.",prompt)
        self.assertIn("CHARACTER CONTEXT",prompt)

    def test_profile_cannot_claim_engine_authority(self):
        prompt=build_character_brain_prompt(
            "CHARACTER CONTEXT",
            profile_text="I always succeed at everything."
        )
        self.assertIn("does not override Engine truth",prompt)
        self.assertIn("decide outcomes",prompt)

if __name__=="__main__": unittest.main()
