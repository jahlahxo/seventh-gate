import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from campaign import set_campaign_setting
from campaign_clock import initialize_campaign_clock
from development import set_development_profile
from director import (
    DirectorPerceptionResult,
    build_director_prompt,
    parse_director_perception,
    run_director_perception,
)
from life import set_birth_date


class DirectorPerceptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.set_database_path(
            Path(self.tmp.name) / "director.db"
        )
        database.initialize_database()
        initialize_campaign_clock(
            "2001-01-01 12:00:00"
        )

        conn = database.get_connection()
        cursor = conn.execute(
            """
            INSERT INTO characters (
                name,
                preferred_model
            )
            VALUES (?, ?)
            """,
            (
                "Mara",
                "character-model",
            ),
        )
        self.character_id = cursor.lastrowid
        conn.commit()
        conn.close()

        set_campaign_setting(
            "director_model",
            "director-primary",
        )
        set_campaign_setting(
            "director_fallback_models",
            "director-fallback",
        )

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_prompt_contains_objective_scene_without_assigning_character_mind(self):
        prompt = build_director_prompt(
            self.character_id,
            {
                "current_event":
                    "A cup falls from the table.",
                "weather": "Rain.",
            },
        )

        self.assertIn(
            "A cup falls from the table.",
            prompt,
        )
        self.assertIn(
            "Do not decide the character's thoughts",
            prompt,
        )
        self.assertIn(
            "Do not convert hidden engine truth",
            prompt,
        )

    def test_child_perception_constraint_is_supplied_to_director(self):
        set_birth_date(
            "character",
            self.character_id,
            "1996-01-01",
        )
        set_development_profile(
            self.character_id,
            ai_participation_mode="full",
        )

        prompt = build_director_prompt(
            self.character_id,
            {
                "observable":
                    "Two adults whisper and embrace."
            },
        )

        self.assertIn(
            "Describe perceivable concrete details first",
            prompt,
        )
        self.assertIn(
            "Preserve ambiguity",
            prompt,
        )

    def test_parser_accepts_only_perception_shape(self):
        raw = json.dumps(
            {
                "current":
                    "The cup hits the floor.",
                "environment":
                    "Rain taps the roof.",
                "people": [
                    {
                        "name": "Elias",
                        "observable":
                            "standing by the door",
                    }
                ],
                "objects": [
                    "a broken cup"
                ],
                "recent": [],
                "private": [],
            }
        )

        result = parse_director_perception(
            self.character_id,
            "director-primary",
            raw,
        )

        self.assertIsInstance(
            result,
            DirectorPerceptionResult,
        )
        self.assertEqual(
            result.perception["current"],
            "The cup hits the floor.",
        )

    def test_parser_rejects_hidden_truth_or_character_mind_fields(self):
        raw = json.dumps(
            {
                "current": "Elias smiles.",
                "environment": None,
                "people": [],
                "objects": [],
                "recent": [],
                "private": [],
                "hidden_truth":
                    "Elias plans betrayal.",
            }
        )

        with self.assertRaises(ValueError):
            parse_director_perception(
                self.character_id,
                "director-primary",
                raw,
            )

    def test_private_notice_can_be_sensory_without_engine_conclusion(self):
        raw = json.dumps(
            {
                "current": "Mara wakes.",
                "environment": None,
                "people": [],
                "objects": [],
                "recent": [],
                "private": [
                    "You feel unusually nauseated this morning."
                ],
            }
        )

        result = parse_director_perception(
            self.character_id,
            "director-primary",
            raw,
        )

        self.assertIn(
            "nauseated",
            result.perception["private"][0],
        )

    @patch(
        "director.get_director_perception_constraints",
        return_value=None,
    )
    def test_run_returns_packet_without_world_mutation(
        self,
        mocked_constraints,
    ):
        def generator(**kwargs):
            return json.dumps(
                {
                    "current": "A knock sounds.",
                    "environment": "The room is dim.",
                    "people": [],
                    "objects": [],
                    "recent": [],
                    "private": [],
                }
            )

        result = run_director_perception(
            self.character_id,
            {
                "event":
                    "Someone knocks on the door."
            },
            generator=generator,
        )

        self.assertEqual(
            result.model,
            "director-primary",
        )
        self.assertEqual(
            result.perception["current"],
            "A knock sounds.",
        )
        self.assertFalse(
            hasattr(result, "world_event_id")
        )

    @patch(
        "director.get_director_perception_constraints",
        return_value=None,
    )
    def test_fallback_director_model_is_used(
        self,
        mocked_constraints,
    ):
        attempted = []

        def generator(**kwargs):
            attempted.append(
                kwargs["model"]
            )

            if kwargs["model"] == "director-primary":
                raise RuntimeError(
                    "primary unavailable"
                )

            return json.dumps(
                {
                    "current": "Hello.",
                    "environment": None,
                    "people": [],
                    "objects": [],
                    "recent": [],
                    "private": [],
                }
            )

        result = run_director_perception(
            self.character_id,
            {"event": "A greeting."},
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

    def test_missing_director_model_is_explicit_error(self):
        conn = database.get_connection()
        conn.execute(
            """
            DELETE FROM campaign_settings
            WHERE setting_key IN (
                'director_model',
                'director_fallback_models'
            )
            """
        )
        conn.commit()
        conn.close()

        with self.assertRaises(RuntimeError):
            run_director_perception(
                self.character_id,
                {"event": "Anything."},
                generator=lambda **kwargs: "{}",
            )

    def test_objective_scene_must_be_structured(self):
        with self.assertRaises(TypeError):
            build_director_prompt(
                self.character_id,
                "raw prose dump",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
