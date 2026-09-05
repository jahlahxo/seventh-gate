from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import database
from database import get_connection, initialize_database
from discord_identity import ensure_character_discord_binding


class DiscordIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.set_database_path(
            Path(self.tmp.name) / "test.db"
        )
        initialize_database()

        conn = get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO characters(
                    name,
                    discord_bot_user_id
                )
                VALUES (?, ?)
                """,
                ("Antti Rautio", None),
            )
            self.character_id = int(cursor.lastrowid)
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def _stored_bot_id(self):
        conn = get_connection()
        try:
            row = conn.execute(
                """
                SELECT discord_bot_user_id
                FROM characters
                WHERE id = ?
                """,
                (self.character_id,),
            ).fetchone()
        finally:
            conn.close()

        return row["discord_bot_user_id"]

    def test_unbound_character_binds_once(self):
        result = ensure_character_discord_binding(
            self.character_id,
            "111111",
        )

        self.assertEqual(result.status, "bound")
        self.assertEqual(
            self._stored_bot_id(),
            "111111",
        )

    def test_matching_existing_binding_is_verified(self):
        ensure_character_discord_binding(
            self.character_id,
            "111111",
        )

        result = ensure_character_discord_binding(
            self.character_id,
            "111111",
        )

        self.assertEqual(result.status, "verified")
        self.assertEqual(
            self._stored_bot_id(),
            "111111",
        )

    def test_mismatch_is_refused_and_preserves_original_binding(self):
        ensure_character_discord_binding(
            self.character_id,
            "111111",
        )

        with self.assertRaises(RuntimeError):
            ensure_character_discord_binding(
                self.character_id,
                "222222",
            )

        self.assertEqual(
            self._stored_bot_id(),
            "111111",
        )

    def test_inactive_character_cannot_bind(self):
        conn = get_connection()
        try:
            conn.execute(
                """
                UPDATE characters
                SET active = 0
                WHERE id = ?
                """,
                (self.character_id,),
            )
            conn.commit()
        finally:
            conn.close()

        with self.assertRaises(ValueError):
            ensure_character_discord_binding(
                self.character_id,
                "111111",
            )

        self.assertIsNone(
            self._stored_bot_id()
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
