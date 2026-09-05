from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from campaign_clock import (
    initialize_campaign_clock,
)
from character_brain import (
    build_character_brain_prompt,
)
from director import (
    build_director_prompt,
)
from social_grounding import (
    build_social_grounding,
    get_social_grounding_sources,
    load_social_grounding_profile,
)


CAMPAIGN_DIR = Path(__file__).resolve().parents[1]


class SocialGroundingTests(
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
            load_social_grounding_profile(
                campaign_dir=CAMPAIGN_DIR
            )
        )

        self.assertEqual(
            profile["profile_id"],
            "southern_ostrobothnia_rural_1878_social",
        )

    def test_campaign_without_social_profile_has_no_social_grounding(
        self,
    ):
        self.assertIsNone(
            build_social_grounding(
                campaign_dir=(
                    Path(self.tmp.name)
                    / "empty_campaign"
                )
            )
        )

    def test_status_structure_preserves_distinct_rural_strata(
        self,
    ):
        grounding = (
            build_social_grounding(
                "1878-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )
        )

        names = {
            item["name"]
            for item
            in grounding[
                "status_structure"
            ]
        }

        self.assertIn(
            "upper strata",
            names,
        )
        self.assertIn(
            "freeholders / landowning farmers",
            names,
        )
        self.assertIn(
            "crofters / tenant farmers",
            names,
        )
        self.assertIn(
            "agricultural labourers / landless workers",
            names,
        )

    def test_life_cycle_service_includes_young_men_and_women(
        self,
    ):
        grounding = (
            build_social_grounding(
                "1878-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )
        )

        rule = next(
            item
            for item
            in grounding["norms"]
            if item["norm_id"]
            == "life_cycle_service"
        )

        self.assertIn(
            "young men",
            rule["applies_to"],
        )
        self.assertIn(
            "young women",
            rule["applies_to"],
        )

    def test_marriage_norm_is_pattern_not_prohibition(
        self,
    ):
        grounding = (
            build_social_grounding(
                "1878-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )
        )

        rule = next(
            item
            for item
            in grounding["norms"]
            if item["norm_id"]
            == "marriage_and_social_origin"
        )

        self.assertIn(
            "social origin matters",
            rule["expectation"],
        )
        self.assertIn(
            "not a prohibition",
            rule[
                "important_nuance"
            ],
        )

    def test_gendered_work_retains_female_agricultural_agency(
        self,
    ):
        grounding = (
            build_social_grounding(
                "1878-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )
        )

        rule = next(
            item
            for item
            in grounding["norms"]
            if item["norm_id"]
            == "gendered_work"
        )

        self.assertIn(
            "milking",
            rule["expectation"],
        )
        self.assertIn(
            "not passive",
            rule[
                "important_nuance"
            ],
        )

    def test_widowhood_is_not_flattened_into_married_womans_status(
        self,
    ):
        grounding = (
            build_social_grounding(
                "1878-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )
        )

        rule = next(
            item
            for item
            in grounding["norms"]
            if item["norm_id"]
            == "widowhood_changes_position"
        )

        self.assertIn(
            "independent action",
            rule["expectation"],
        )
        self.assertIn(
            "Property matters",
            rule[
                "important_nuance"
            ],
        )

    def test_household_etiquette_marks_local_pattern_as_non_universal(
        self,
    ):
        grounding = (
            build_social_grounding(
                "1878-11-10 12:00:00",
                campaign_dir=CAMPAIGN_DIR,
            )
        )

        rule = next(
            item
            for item
            in grounding["norms"]
            if item["norm_id"]
            == "gendered_household_space"
        )

        self.assertIn(
            "without invitation",
            rule["expectation"],
        )
        self.assertIn(
            "not as a rule for every",
            rule[
                "important_nuance"
            ],
        )

    def test_director_receives_social_grounding_without_mind_control(
        self,
    ):
        grounding = (
            build_social_grounding(
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
                return_value=None,
            ),
            patch(
                "director.build_social_grounding",
                return_value=grounding,
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
            "TRUSTED SOCIAL GROUNDING",
            prompt,
        )
        self.assertIn(
            "outsider",
            prompt.casefold(),
        )
        self.assertIn(
            "never permission to invent",
            prompt,
        )

    def test_character_prompt_keeps_social_norms_bounded_by_knowledge(
        self,
    ):
        prompt = (
            build_character_brain_prompt(
                "CHARACTER CONTEXT"
            )
        )

        self.assertIn(
            "Period social expectations",
            prompt,
        )
        self.assertIn(
            "do not invent a",
            prompt,
        )
        self.assertIn(
            "individuality",
            prompt,
        )

    def test_source_metadata_is_kept_for_audit(
        self,
    ):
        sources = (
            get_social_grounding_sources(
                campaign_dir=CAMPAIGN_DIR,
            )
        )

        self.assertIn(
            "roikonen_hakkinen_stratification",
            sources,
        )
        self.assertIn(
            "seurasaari_farmhouse",
            sources,
        )
        self.assertIn(
            "publisher",
            sources[
                "seurasaari_farmhouse"
            ],
        )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
