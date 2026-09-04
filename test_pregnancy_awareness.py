import tempfile
import unittest
from pathlib import Path

import database
from campaign_clock import initialize_campaign_clock
from pregnancy_awareness import (
    generate_plausible_signs,
    get_awareness,
    get_pending_private_signs,
    mark_sign_noticed,
    set_awareness,
)
from reproduction import create_pregnancy


class AlwaysZero:
    def random(self):
        return 0.0


class PregnancyAwarenessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.set_database_path(
            Path(self.tmp.name) / "awareness.db"
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
            ("Test Character", "test-model"),
        )
        self.character_id = cursor.lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def make_pregnancy(self, days=40):
        return create_pregnancy(
            "character",
            self.character_id,
            gestational_age_days=days,
            origin_type="biological",
        )

    def test_new_pregnancy_does_not_grant_awareness(self):
        pregnancy = self.make_pregnancy()

        awareness = get_awareness(
            pregnancy["id"]
        )

        self.assertEqual(
            awareness["awareness_state"],
            "unaware",
        )

    def test_sign_generation_does_not_change_awareness(self):
        pregnancy = self.make_pregnancy(40)

        signs = generate_plausible_signs(
            pregnancy["id"],
            rng=AlwaysZero(),
        )

        self.assertGreater(len(signs), 0)

        awareness = get_awareness(
            pregnancy["id"]
        )

        self.assertEqual(
            awareness["awareness_state"],
            "unaware",
        )

    def test_private_signs_are_addressed_only_to_gestational_owner(self):
        pregnancy = self.make_pregnancy(40)

        generate_plausible_signs(
            pregnancy["id"],
            rng=AlwaysZero(),
        )

        pending = get_pending_private_signs(
            pregnancy["id"]
        )

        self.assertEqual(
            pending["owner_type"],
            "character",
        )
        self.assertEqual(
            pending["owner_id"],
            str(self.character_id),
        )
        self.assertGreater(
            len(pending["signs"]),
            0,
        )

    def test_character_interpretation_is_separate_from_sign(self):
        pregnancy = self.make_pregnancy(40)

        signs = generate_plausible_signs(
            pregnancy["id"],
            rng=AlwaysZero(),
        )

        mark_sign_noticed(signs[0]["id"])

        self.assertEqual(
            get_awareness(
                pregnancy["id"]
            )["awareness_state"],
            "unaware",
        )

        set_awareness(
            pregnancy["id"],
            "suspected",
            source_type="character_self",
            source_id=self.character_id,
            confidence=0.6,
        )

        self.assertEqual(
            get_awareness(
                pregnancy["id"]
            )["awareness_state"],
            "suspected",
        )

    def test_confirmation_can_be_recorded_later(self):
        pregnancy = self.make_pregnancy(70)

        result = set_awareness(
            pregnancy["id"],
            "confirmed",
            source_type="story_confirmation",
            source_id="midwife-visit",
            confidence=1.0,
        )

        self.assertEqual(
            result["awareness_state"],
            "confirmed",
        )
        self.assertEqual(
            result["confidence"],
            1.0,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
