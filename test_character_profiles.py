import tempfile
import unittest
from pathlib import Path

import database
from database import get_connection, initialize_database
from character_creation import (
    bind_character_discord_bot,
    configure_character_models,
    create_ai_character,
)
from character_profiles import (
    get_character_profile,
    import_character_profile_file,
)


class CharacterProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.set_database_path(
            Path(self.tmp.name) / "test.db"
        )
        initialize_database()

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_rich_profile_preserved(self):
        text = "# TEST\n\nKeep every meaningful instruction."
        character = create_ai_character(
            "Test",
            profile_text=text,
        )
        self.assertEqual(
            get_character_profile(
                character.character_id
            ).profile_text,
            text,
        )

    def test_defaults_deferred(self):
        character = create_ai_character(
            "Deferred",
            profile_text="Profile.",
        )
        conn = get_connection()
        row = conn.execute(
            """
            SELECT ai_participation_mode
            FROM character_lifecycle_profiles
            WHERE character_id = ?
            """,
            (character.character_id,),
        ).fetchone()
        conn.close()

        self.assertEqual(
            row["ai_participation_mode"],
            "deferred",
        )

    def test_attributes_and_custom_skills(self):
        character = create_ai_character(
            "Capable",
            profile_text="Profile.",
            attributes={
                "Strength": 3,
                "Perception": 4,
            },
            skills={
                "Fighting": 3,
                "Farming": {
                    "value": 4,
                    "notes": "Farm labour.",
                },
            },
        )

        conn = get_connection()
        stats = conn.execute(
            """
            SELECT stat_name, stat_value
            FROM character_stats
            WHERE owner_type = 'character'
              AND owner_id = ?
            """,
            (character.character_id,),
        ).fetchall()

        skills = conn.execute(
            """
            SELECT skill_name, skill_value
            FROM character_skills
            WHERE owner_type = 'character'
              AND owner_id = ?
            """,
            (character.character_id,),
        ).fetchall()
        conn.close()

        self.assertEqual(
            {
                row["stat_name"]: row["stat_value"]
                for row in stats
            },
            {
                "Strength": 3,
                "Perception": 4,
            },
        )

        self.assertEqual(
            {
                row["skill_name"]: row["skill_value"]
                for row in skills
            },
            {
                "Fighting": 3,
                "Farming": 4,
            },
        )

    def test_models_configure_without_profile_loss(self):
        character = create_ai_character(
            "Model",
            profile_text="Do not lose me.",
        )
        configure_character_models(
            character.character_id,
            preferred_model="a",
            fallback_models=["b", "c"],
        )

        conn = get_connection()
        row = conn.execute(
            """
            SELECT preferred_model, fallback_models
            FROM characters
            WHERE id = ?
            """,
            (character.character_id,),
        ).fetchone()
        conn.close()

        self.assertEqual(
            (
                row["preferred_model"],
                row["fallback_models"],
            ),
            ("a", "b,c"),
        )
        self.assertEqual(
            get_character_profile(
                character.character_id
            ).profile_text,
            "Do not lose me.",
        )

    def test_discord_binding(self):
        character = create_ai_character(
            "Discord",
            profile_text="Profile.",
        )
        bind_character_discord_bot(
            character.character_id,
            "123",
        )

        conn = get_connection()
        row = conn.execute(
            """
            SELECT discord_bot_user_id
            FROM characters
            WHERE id = ?
            """,
            (character.character_id,),
        ).fetchone()
        conn.close()

        self.assertEqual(
            row["discord_bot_user_id"],
            "123",
        )

    def test_utf8_file_import(self):
        character = create_ai_character(
            "Finn",
            profile_text="Temporary.",
        )

        path = Path(self.tmp.name) / "profile.txt"
        path.write_text(
            "Perkele. Tämä säilyy.",
            encoding="utf-8",
        )

        imported = import_character_profile_file(
            character.character_id,
            path,
        )

        self.assertEqual(
            imported.profile_text,
            "Perkele. Tämä säilyy.",
        )
        self.assertEqual(
            imported.source_name,
            "profile.txt",
        )


if __name__ == "__main__":
    unittest.main()
