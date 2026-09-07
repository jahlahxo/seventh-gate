import unittest

from actions import (
    ActionType,
    make_action,
    make_entity,
)
from characters import (
    ATTRIBUTE_NAMES,
    validate_attribute_name,
)
import resolver


class AttributePolicyTests(unittest.TestCase):
    def _intent(self, action_type):
        return make_action(
            action_type,
            actor=make_entity(
                "character",
                1,
            ),
            description="test",
        )

    def test_only_objective_core_attributes_remain(self):
        self.assertEqual(
            ATTRIBUTE_NAMES,
            (
                "Strength",
                "Agility",
                "Endurance",
                "Perception",
            ),
        )

    def test_wits_and_presence_are_not_valid_attributes(self):
        with self.assertRaises(ValueError):
            validate_attribute_name("Wits")

        with self.assertRaises(ValueError):
            validate_attribute_name("Presence")

    def test_perception_handles_observation_search_and_inspection(self):
        expected = {
            ActionType.OBSERVE:
                ("Perception", "Observation"),
            ActionType.LISTEN:
                ("Perception", "Observation"),
            ActionType.SEARCH:
                ("Perception", "Investigation"),
            ActionType.INSPECT:
                ("Perception", "Investigation"),
        }

        for action_type, pairing in expected.items():
            with self.subTest(
                action_type=action_type
            ):
                self.assertEqual(
                    resolver.get_actor_pairing(
                        self._intent(
                            action_type
                        )
                    ),
                    pairing,
                )

    def test_social_skills_do_not_use_presence_or_wits(self):
        expected = {
            ActionType.PERSUADE:
                (None, "Persuasion"),
            ActionType.DECEIVE:
                (None, "Deception"),
            ActionType.INTIMIDATE:
                (None, "Intimidation"),
        }

        for action_type, pairing in expected.items():
            with self.subTest(
                action_type=action_type
            ):
                self.assertEqual(
                    resolver.get_actor_pairing(
                        self._intent(
                            action_type
                        )
                    ),
                    pairing,
                )

    def test_deception_has_no_mechanical_lie_detector_opposition(self):
        self.assertNotIn(
            ActionType.DECEIVE,
            resolver.DEFAULT_OPPOSITION,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
