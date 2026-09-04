import tempfile
import unittest
from pathlib import Path

import database
from campaign_clock import (
    advance_campaign_time,
    initialize_campaign_clock,
)
from life import (
    get_age_years,
    set_birth_date,
)
from reproduction import (
    age_fertility_factor,
    create_pregnancy,
    end_pregnancy,
    gestational_age_days,
    get_ongoing_pregnancy,
    resolve_conception,
    set_reproductive_profile,
)


class ReproductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.set_database_path(
            Path(self.tmp.name) / "reproduction.db"
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
                preferred_model
            )
            VALUES (?, ?)
            """,
            ("Test Character A", "test-model"),
        )
        self.a = cursor.lastrowid

        cursor = conn.execute(
            """
            INSERT INTO characters (
                name,
                preferred_model
            )
            VALUES (?, ?)
            """,
            ("Test Character B", "test-model"),
        )
        self.b = cursor.lastrowid

        conn.commit()
        conn.close()

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_fresh_schema_uses_single_generalized_conception_path(self):
        conn = database.get_connection()

        tables = {
            row["name"]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

        pregnancy_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(pregnancies)"
            ).fetchall()
        }

        conn.close()

        self.assertIn(
            "conception_checks",
            tables,
        )
        self.assertIn(
            "pregnancy_origins",
            tables,
        )
        self.assertNotIn(
            "conception_results",
            tables,
        )
        self.assertNotIn(
            "conception_result_id",
            pregnancy_columns,
        )
        self.assertNotIn(
            "conception_world_event_id",
            pregnancy_columns,
        )

    def test_age_is_derived_from_campaign_clock(self):
        set_birth_date(
            "character",
            self.a,
            "1820-06-02",
        )

        self.assertEqual(
            get_age_years(
                "character",
                self.a,
            ),
            29,
        )

        advance_campaign_time(
            days=1,
            reason="Birthday arrives.",
            source_type="test",
        )

        self.assertEqual(
            get_age_years(
                "character",
                self.a,
            ),
            30,
        )

    def test_default_age_curve_uses_author_defined_11_to_55_window(self):
        self.assertEqual(
            age_fertility_factor(10),
            0.0,
        )
        self.assertGreater(
            age_fertility_factor(11),
            0.0,
        )
        self.assertGreater(
            age_fertility_factor(55),
            0.0,
        )
        self.assertEqual(
            age_fertility_factor(56),
            0.0,
        )

    def test_imported_pregnancy_does_not_require_conception_event(self):
        pregnancy = create_pregnancy(
            "character",
            self.a,
            gestational_age_days=120,
            origin_type="imported",
            certainty="known",
            origin_description=(
                "Pregnancy established when the character entered the story."
            ),
        )

        self.assertEqual(
            pregnancy["origin_type"],
            "imported",
        )
        self.assertIsNone(
            pregnancy["conception_check_id"]
        )
        self.assertEqual(
            gestational_age_days(
                pregnancy["id"]
            ),
            120,
        )

    def test_magical_pregnancy_can_be_created_directly(self):
        pregnancy = create_pregnancy(
            "character",
            self.a,
            origin_type="magical",
            origin_description="Established by story magic.",
        )

        self.assertEqual(
            pregnancy["origin_type"],
            "magical",
        )

    def test_conception_check_is_not_tied_to_intimate_event(self):
        set_birth_date(
            "character",
            self.a,
            "1825-01-01",
        )

        set_reproductive_profile(
            "character",
            self.a,
            can_conceive=True,
            fertility_status="normal",
        )

        result = resolve_conception(
            "character",
            self.a,
            base_chance=0.5,
            source_type="assisted_reproduction",
            source_id="procedure-7",
            roll=0.0,
            origin_type="assisted",
        )

        self.assertTrue(
            result["conceived"]
        )
        self.assertIsNotNone(
            result["pregnancy"]
        )
        self.assertEqual(
            result["pregnancy"]["conception_check_id"],
            result["check_id"],
        )

    def test_extreme_age_factor_lowers_biological_probability(self):
        set_birth_date(
            "character",
            self.a,
            "1795-01-01",
        )

        set_reproductive_profile(
            "character",
            self.a,
            can_conceive=True,
        )

        result = resolve_conception(
            "character",
            self.a,
            base_chance=1.0,
            source_type="biological",
            roll=0.02,
            create_pregnancy_on_success=False,
        )

        self.assertEqual(
            result["age_factor"],
            0.01,
        )
        self.assertFalse(
            result["conceived"]
        )

    def test_pregnancy_progresses_only_when_campaign_time_advances(self):
        pregnancy = create_pregnancy(
            "character",
            self.a,
            gestational_age_days=40,
            origin_type="unknown",
        )

        self.assertEqual(
            gestational_age_days(
                pregnancy["id"]
            ),
            40,
        )

        advance_campaign_time(
            days=10,
            reason="Ten fictional days pass.",
            source_type="test",
        )

        self.assertEqual(
            gestational_age_days(
                pregnancy["id"]
            ),
            50,
        )

    def test_duplicate_ongoing_pregnancy_is_blocked_by_default(self):
        create_pregnancy(
            "character",
            self.a,
            origin_type="unknown",
        )

        with self.assertRaises(ValueError):
            create_pregnancy(
                "character",
                self.a,
                origin_type="unknown",
            )

    def test_pregnancy_can_end_with_recorded_outcome(self):
        pregnancy = create_pregnancy(
            "character",
            self.a,
            gestational_age_days=280,
            origin_type="imported",
        )

        ended = end_pregnancy(
            pregnancy["id"],
            outcome="birth",
            description="Pregnancy ended in birth.",
        )

        self.assertEqual(
            ended["status"],
            "ended",
        )
        self.assertEqual(
            ended["outcome"],
            "birth",
        )
        self.assertIsNone(
            get_ongoing_pregnancy(
                "character",
                self.a,
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
