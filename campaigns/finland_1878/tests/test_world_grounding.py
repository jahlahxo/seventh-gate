from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from campaign_clock import (
    initialize_campaign_clock,
)
from director import (
    build_director_prompt,
)
from world_grounding import (
    build_world_grounding,
    get_world_grounding_sources,
    load_world_grounding_profile,
)


CAMPAIGN_DIR = Path(__file__).resolve().parents[1]


class WorldGroundingTests(
    unittest.TestCase
):
    def setUp(self):
        self.tmp = (
            tempfile.TemporaryDirectory()
        )

        database.set_database_path(
            Path(self.tmp.name)
            / "test_campaign"
            / "seventh_gate.db"
        )

        database.initialize_database()

        initialize_campaign_clock(
            "1878-11-10 12:00:00"
        )

        conn = database.get_connection()

        try:
            cursor = conn.execute(
                """
                INSERT INTO characters (
                    name,
                    preferred_model
                )
                VALUES (?, ?)
                """,
                (
                    "Test Character",
                    "test-model",
                ),
            )
            self.character_id = int(
                cursor.lastrowid
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_profile_loads_from_campaign_folder(
        self,
    ):
        profile = (
            load_world_grounding_profile(
                campaign_dir=CAMPAIGN_DIR
            )
        )

        self.assertEqual(
            profile["profile_id"],
            "southern_ostrobothnia_1878",
        )

    def test_campaign_without_profile_has_no_grounding(
        self,
    ):
        self.assertIsNone(
            build_world_grounding(
                campaign_dir=(
                    Path(self.tmp.name)
                    / "empty_campaign"
                )
            )
        )

    def test_november_grounding_contains_period_and_season_facts(
        self,
    ):
        grounding = (
            build_world_grounding(
                "1878-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )
        )

        texts = [
            item["text"]
            for item
            in grounding[
                "relevant_facts"
            ]
        ]

        rendered = "\n".join(
            texts
        )

        self.assertIn(
            "Grand Duchy",
            rendered,
        )
        self.assertIn(
            "markka",
            rendered,
        )
        self.assertIn(
            "November",
            rendered,
        )
        self.assertIn(
            "not yet compulsory",
            rendered,
        )

    def test_gold_standard_fact_is_date_bounded(
        self,
    ):
        before = (
            build_world_grounding(
                "1877-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )
        )

        after = (
            build_world_grounding(
                "1878-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )
        )

        before_ids = {
            item["fact_id"]
            for item
            in before[
                "relevant_facts"
            ]
        }

        after_ids = {
            item["fact_id"]
            for item
            in after[
                "relevant_facts"
            ]
        }

        self.assertNotIn(
            "gold_standard_1878",
            before_ids,
        )
        self.assertIn(
            "gold_standard_1878",
            after_ids,
        )

    def test_daily_weather_is_deterministic(
        self,
    ):
        first = (
            build_world_grounding(
                "1878-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )["daily_weather"]
        )

        second = (
            build_world_grounding(
                "1878-11-10 21:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )["daily_weather"]
        )

        self.assertEqual(
            first,
            second,
        )

    def test_opening_day_is_sleet_with_current_seed(
        self,
    ):
        weather = (
            build_world_grounding(
                "1878-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )["daily_weather"]
        )

        self.assertEqual(
            weather["kind"],
            "sleet",
        )

        self.assertIn(
            "not a claim",
            weather[
                "simulation_basis"
            ],
        )

    def test_daylight_is_short_in_november(
        self,
    ):
        hours = (
            build_world_grounding(
                "1878-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )[
                "approx_daylight_hours"
            ]
        )

        self.assertGreater(
            hours,
            6.0,
        )
        self.assertLess(
            hours,
            8.5,
        )

    def test_director_can_receive_campaign_grounding_without_character_knowledge(
        self,
    ):
        grounding = (
            build_world_grounding(
                "1878-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )
        )

        with (
            patch(
                "director.get_director_perception_constraints",
                return_value=None,
            ),
            patch(
                "director.build_world_grounding",
                return_value=grounding,
            ),
            patch(
                "director.build_social_grounding",
                return_value=None,
            ),
        ):
            prompt = build_director_prompt(
                self.character_id,
                {
                    "event": (
                        "A stranger enters."
                    )
                },
            )

        self.assertIn(
            "Southern Ostrobothnia",
            prompt,
        )
        self.assertIn(
            "NOT automatically character knowledge",
            prompt,
        )
        self.assertIn(
            "modern time traveller",
            prompt,
        )

    def test_source_metadata_is_kept_for_audit(
        self,
    ):
        sources = (
            get_world_grounding_sources(
                campaign_dir=CAMPAIGN_DIR,
            )
        )

        self.assertIn(
            "fmi_seasons",
            sources,
        )
        self.assertIn(
            "publisher",
            sources[
                "fmi_seasons"
            ],
        )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
