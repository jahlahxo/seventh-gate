import tempfile
import unittest
from pathlib import Path

import database
from character_creation import configure_character_models
from character_profiles import get_character_profile
from database import get_connection, initialize_database
from import_antti import import_antti


class AnttiImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.set_database_path(
            Path(self.tmp.name) / "test.db"
        )
        initialize_database()

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_import_uses_real_profile_and_cleans_artifacts(self):
        created = import_antti()

        profile = get_character_profile(
            created.character_id
        )

        self.assertIsNotNone(profile)
        self.assertEqual(
            profile.source_name,
            "antti_prompt.txt",
        )
        self.assertIn(
            "# ANTTI RAUTIO",
            profile.profile_text,
        )
        self.assertNotIn(
            ":contentReference[",
            profile.profile_text,
        )

    def test_import_is_idempotent(self):
        first = import_antti()
        second = import_antti()

        self.assertEqual(
            first.character_id,
            second.character_id,
        )

        conn = get_connection()

        try:
            count = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM characters
                WHERE name = 'Antti Rautio'
                """
            ).fetchone()["n"]
        finally:
            conn.close()

        self.assertEqual(count, 1)

    def test_rerun_preserves_existing_model_configuration(self):
        created = import_antti()

        configure_character_models(
            created.character_id,
            preferred_model="preferred-model",
            fallback_models=[
                "fallback-a",
                "fallback-b",
            ],
        )

        import_antti()

        conn = get_connection()

        try:
            row = conn.execute(
                """
                SELECT
                    preferred_model,
                    fallback_models
                FROM characters
                WHERE id = ?
                """,
                (created.character_id,),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(
            row["preferred_model"],
            "preferred-model",
        )
        self.assertEqual(
            row["fallback_models"],
            "fallback-a,fallback-b",
        )


if __name__ == "__main__":
    unittest.main()
