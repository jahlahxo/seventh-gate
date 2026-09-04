import tempfile
import unittest
from pathlib import Path

import database
from campaign_clock import (
    advance_campaign_time,
    initialize_campaign_clock,
    set_campaign_datetime,
)
from development import (
    build_developmental_grounding,
    developmental_stage_for_age,
    get_development_context,
    get_development_profile,
    get_director_perception_constraints,
    get_milestones,
    record_milestone,
    set_ai_participation_mode,
    set_development_profile,
)
from life import (
    get_age_days,
    get_age_months,
    set_birth_date,
)
from mortality import record_death


class DevelopmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

        database.set_database_path(
            Path(self.tmp.name)
            / "development.db"
        )
        database.initialize_database()

        initialize_campaign_clock(
            "1850-06-01 12:00:00"
        )

        conn = database.get_connection()
        cursor = conn.execute(
            """
            INSERT INTO characters (
                name,
                personality,
                speech_style,
                preferred_model
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "Mara",
                "Curious, stubborn, affectionate.",
                "Direct and expressive.",
                "test-model",
            ),
        )
        self.child = cursor.lastrowid
        conn.commit()
        conn.close()

        set_birth_date(
            "character",
            self.child,
            "1850-06-01",
        )

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_stage_bands_are_simple_and_recognizable(self):
        self.assertEqual(
            developmental_stage_for_age(0),
            "infant",
        )
        self.assertEqual(
            developmental_stage_for_age(2),
            "toddler",
        )
        self.assertEqual(
            developmental_stage_for_age(5),
            "young_child",
        )
        self.assertEqual(
            developmental_stage_for_age(10),
            "older_child",
        )
        self.assertEqual(
            developmental_stage_for_age(15),
            "adolescent",
        )
        self.assertEqual(
            developmental_stage_for_age(18),
            "adult",
        )

    def test_exact_age_follows_campaign_clock(self):
        self.assertEqual(
            get_age_days(
                "character",
                self.child,
            ),
            0,
        )

        advance_campaign_time(
            days=40,
            reason="Forty fictional days pass.",
            source_type="test",
        )

        self.assertEqual(
            get_age_days(
                "character",
                self.child,
            ),
            40,
        )
        self.assertEqual(
            get_age_months(
                "character",
                self.child,
            ),
            1,
        )

    def test_grounding_explicitly_blocks_model_knowledge_leak(self):
        set_campaign_datetime(
            "1855-06-01 12:00:00",
            reason="Five years pass.",
            source_type="test",
        )

        grounding = build_developmental_grounding(
            self.child
        )

        self.assertIn(
            "Actual age: 5 years",
            grounding,
        )
        self.assertIn(
            "Developmental stage: Young Child",
            grounding,
        )
        self.assertIn(
            "merely because you as the model understand them",
            grounding,
        )
        self.assertIn(
            "concrete observable details",
            grounding,
        )

    def test_grounding_does_not_assign_personality_or_morality(self):
        set_campaign_datetime(
            "1855-06-01 12:00:00",
            reason="Five years pass.",
            source_type="test",
        )

        grounding = build_developmental_grounding(
            self.child
        )

        self.assertIn(
            "does not dictate personality, morality, emotions, loyalties, or choices",
            grounding,
        )

    def test_individual_development_can_modify_baseline_without_adultifying(self):
        set_campaign_datetime(
            "1855-06-01 12:00:00",
            reason="Five years pass.",
            source_type="test",
        )

        set_development_profile(
            self.child,
            developmental_notes=(
                "Unusually articulate for age, but sheltered and "
                "inexperienced with adult social relationships."
            ),
            ai_participation_mode="limited",
        )

        grounding = build_developmental_grounding(
            self.child
        )

        self.assertIn(
            "Unusually articulate for age",
            grounding,
        )
        self.assertIn(
            "Individual developmental context:",
            grounding,
        )
        self.assertIn(
            "Do not give the character adult interpretations",
            grounding,
        )

    def test_director_filter_requires_concrete_child_perception(self):
        set_campaign_datetime(
            "1855-06-01 12:00:00",
            reason="Five years pass.",
            source_type="test",
        )

        constraints = (
            get_director_perception_constraints(
                self.child
            )
        )

        self.assertTrue(
            constraints[
                "developmental_filter_required"
            ]
        )
        self.assertIn(
            "concrete details",
            constraints["directive"],
        )
        self.assertIn(
            "hidden motives",
            constraints["directive"],
        )

    def test_adult_does_not_receive_child_filter(self):
        set_campaign_datetime(
            "1868-06-01 12:00:00",
            reason="Eighteen years pass.",
            source_type="test",
        )

        constraints = (
            get_director_perception_constraints(
                self.child
            )
        )

        self.assertFalse(
            constraints[
                "developmental_filter_required"
            ]
        )

    def test_age_does_not_auto_activate_ai_brain(self):
        set_campaign_datetime(
            "1868-06-01 12:00:00",
            reason="Eighteen years pass.",
            source_type="test",
        )

        context = get_development_context(
            self.child
        )

        self.assertEqual(
            context["developmental_stage"],
            "adult",
        )
        self.assertEqual(
            context["ai_participation_mode"],
            "deferred",
        )
        self.assertFalse(
            context["may_invoke_ai_brain"]
        )

    def test_story_can_enable_brain_without_changing_identity(self):
        set_ai_participation_mode(
            self.child,
            "limited",
        )

        profile = get_development_profile(
            self.child
        )
        context = get_development_context(
            self.child
        )

        self.assertEqual(
            profile["ai_participation_mode"],
            "limited",
        )
        self.assertTrue(
            context["may_invoke_ai_brain"]
        )

        conn = database.get_connection()
        row = conn.execute(
            """
            SELECT personality, speech_style
            FROM characters
            WHERE id = ?
            """,
            (self.child,),
        ).fetchone()
        conn.close()

        self.assertEqual(
            row["personality"],
            "Curious, stubborn, affectionate.",
        )
        self.assertEqual(
            row["speech_style"],
            "Direct and expressive.",
        )

    def test_milestones_are_story_facts_not_age_assumptions(self):
        set_campaign_datetime(
            "1855-06-01 12:00:00",
            reason="Five years pass.",
            source_type="test",
        )

        self.assertEqual(
            get_milestones(
                self.child
            ),
            [],
        )

        record_milestone(
            self.child,
            "literacy_started",
            description=(
                "Mara begins recognizing written words."
            ),
        )

        milestones = get_milestones(
            self.child
        )

        self.assertEqual(
            len(milestones),
            1,
        )
        self.assertEqual(
            milestones[0]["milestone_type"],
            "literacy_started",
        )

    def test_deceased_character_brain_cannot_be_invoked(self):
        set_ai_participation_mode(
            self.child,
            "full",
        )

        record_death(
            "character",
            self.child,
            cause_of_death="test",
        )

        context = get_development_context(
            self.child
        )

        self.assertFalse(
            context["alive"]
        )
        self.assertFalse(
            context["may_invoke_ai_brain"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
