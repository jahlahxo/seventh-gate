import tempfile
import unittest
from pathlib import Path

import database
from intimacy import (
    create_intimate_event,
    get_event_experiences,
    get_participant_experience,
    set_participant_experience,
)
from world import (
    create_location,
    map_channel_to_location,
    move_participant,
)


class IntimacyStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(
            self.temp_dir.name
        ) / "seventh_gate_intimacy_test.db"

        database.set_database_path(self.test_db)
        database.initialize_database()

        conn = database.get_connection()

        cursor = conn.execute(
            """
            INSERT INTO characters (
                name,
                preferred_model
            )
            VALUES (?, ?)
            """,
            ("NPC A", "test-model"),
        )
        self.npc_a = cursor.lastrowid

        cursor = conn.execute(
            """
            INSERT INTO characters (
                name,
                preferred_model
            )
            VALUES (?, ?)
            """,
            ("NPC B", "test-model"),
        )
        self.npc_b = cursor.lastrowid

        cursor = conn.execute(
            """
            INSERT INTO player_personas (
                discord_user_id,
                discord_name,
                rp_name
            )
            VALUES (?, ?, ?)
            """,
            (
                "900000000000000001",
                "test-player",
                "Player Persona",
            ),
        )
        self.player = cursor.lastrowid

        conn.commit()
        conn.close()

        self.room = create_location(
            "Private Test Room"
        )

        map_channel_to_location(
            self.room,
            "900000000000000900",
            private_location=True,
        )

        for participant_type, participant_id in (
            ("character", self.npc_a),
            ("character", self.npc_b),
            ("player_persona", self.player),
        ):
            move_participant(
                participant_type,
                participant_id,
                self.room,
                source_type="integration_test",
            )

    def tearDown(self):
        database.reset_database_path()
        self.temp_dir.cleanup()

    def test_two_participants_can_have_opposite_experiences(self):
        event_id = create_intimate_event(
            "character",
            self.npc_a,
            "character",
            self.npc_b,
            consent_context="nonconsensual",
        )

        set_participant_experience(
            event_id,
            "character",
            self.npc_a,
            source_type="character_self",
            source_id=self.npc_a,
            willingness="willing",
            desire_level=3,
            physical_arousal_level=3,
            enjoyment_level=4,
            pain_level=0,
            emotional_response="pleased",
        )

        set_participant_experience(
            event_id,
            "character",
            self.npc_b,
            source_type="character_self",
            source_id=self.npc_b,
            willingness="unwilling",
            desire_level=0,
            physical_arousal_level=1,
            enjoyment_level=0,
            pain_level=2,
            emotional_response="angry and distressed",
        )

        a = get_participant_experience(
            event_id,
            "character",
            self.npc_a,
        )

        b = get_participant_experience(
            event_id,
            "character",
            self.npc_b,
        )

        self.assertEqual(a["enjoyment_level"], 4)
        self.assertEqual(b["enjoyment_level"], 0)
        self.assertEqual(b["willingness"], "unwilling")

    def test_physical_response_does_not_infer_enjoyment_or_willingness(self):
        event_id = create_intimate_event(
            "character",
            self.npc_a,
            "character",
            self.npc_b,
            consent_context="unclear",
        )

        set_participant_experience(
            event_id,
            "character",
            self.npc_b,
            source_type="character_self",
            source_id=self.npc_b,
            physical_arousal_level=3,
        )

        experience = get_participant_experience(
            event_id,
            "character",
            self.npc_b,
        )

        self.assertEqual(
            experience["physical_arousal_level"],
            3,
        )
        self.assertIsNone(
            experience["enjoyment_level"]
        )
        self.assertIsNone(
            experience["willingness"]
        )
        self.assertIsNone(
            experience["desire_level"]
        )

    def test_event_context_does_not_auto_create_internal_states(self):
        event_id = create_intimate_event(
            "character",
            self.npc_a,
            "character",
            self.npc_b,
            consent_context="nonconsensual",
        )

        self.assertEqual(
            get_event_experiences(event_id),
            [],
        )

    def test_npc_cannot_write_another_npc_internal_state(self):
        event_id = create_intimate_event(
            "character",
            self.npc_a,
            "character",
            self.npc_b,
        )

        with self.assertRaises(PermissionError):
            set_participant_experience(
                event_id,
                "character",
                self.npc_b,
                source_type="character_self",
                source_id=self.npc_a,
                enjoyment_level=4,
            )

    def test_bot_cannot_write_human_internal_state(self):
        event_id = create_intimate_event(
            "character",
            self.npc_a,
            "player_persona",
            self.player,
        )

        with self.assertRaises(PermissionError):
            set_participant_experience(
                event_id,
                "player_persona",
                self.player,
                source_type="character_self",
                source_id=self.npc_a,
                enjoyment_level=4,
            )

    def test_human_can_establish_only_own_internal_state(self):
        event_id = create_intimate_event(
            "character",
            self.npc_a,
            "player_persona",
            self.player,
        )

        experience = set_participant_experience(
            event_id,
            "player_persona",
            self.player,
            source_type="player_self",
            source_id=self.player,
            willingness="unwilling",
            desire_level=0,
            enjoyment_level=0,
            emotional_response="furious",
        )

        self.assertEqual(
            experience["willingness"],
            "unwilling",
        )
        self.assertEqual(
            experience["enjoyment_level"],
            0,
        )

    def test_current_event_requires_shared_location(self):
        second_room = create_location(
            "Other Room"
        )

        map_channel_to_location(
            second_room,
            "900000000000000901",
        )

        move_participant(
            "character",
            self.npc_b,
            second_room,
            source_type="integration_test",
            force=True,
        )

        with self.assertRaises(ValueError):
            create_intimate_event(
                "character",
                self.npc_a,
                "character",
                self.npc_b,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
