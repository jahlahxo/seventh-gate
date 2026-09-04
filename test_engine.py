import tempfile
import unittest
from pathlib import Path

import database
from actions import ActionType, make_action, make_entity
from executor import execute_resolved_action
from resolver import resolve_action
from world import (
    connect_locations,
    create_location,
    get_participant_location,
    map_channel_to_location,
    move_participant,
)


class EngineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(self.temp_dir.name) / "seventh_gate_test.db"

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
            (
                "Test Matti",
                "test-model",
            ),
        )

        self.character_id = cursor.lastrowid

        conn.commit()
        conn.close()

        self.tavern_id = create_location(
            "Test Tavern",
            description="A disposable test location.",
        )

        self.barn_id = create_location(
            "Test Barn",
            description="Another disposable test location.",
        )

        self.cellar_id = create_location(
            "Test Cellar",
            description="An intentionally unconnected location.",
        )

        map_channel_to_location(
            self.tavern_id,
            "900000000000000001",
        )

        map_channel_to_location(
            self.barn_id,
            "900000000000000002",
        )

        map_channel_to_location(
            self.cellar_id,
            "900000000000000003",
        )

        connect_locations(
            self.tavern_id,
            self.barn_id,
            bidirectional=True,
        )

        # Initial placement is done through the real world engine.
        move_participant(
            participant_type="character",
            participant_id=self.character_id,
            destination_location_id=self.tavern_id,
            source_type="integration_test",
        )

    def tearDown(self):
        database.reset_database_path()
        self.temp_dir.cleanup()

    def test_human_social_target_retains_internal_agency(self):
        conn = database.get_connection()

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
                "900000000000009999",
                "test-human",
                "Test Human",
            ),
        )

        human_id = cursor.lastrowid
        conn.commit()
        conn.close()

        move_participant(
            participant_type="player_persona",
            participant_id=human_id,
            destination_location_id=self.tavern_id,
            source_type="integration_test",
        )

        actor = make_entity(
            "character",
            self.character_id,
            name="Test Matti",
        )

        human = make_entity(
            "player_persona",
            human_id,
            name="Test Human",
        )

        intent = make_action(
            ActionType.PERSUADE,
            actor=actor,
            target=human,
            description="Test Matti tries to persuade Test Human.",
            source_type="integration_test",
            metadata={
                "difficulty": -100,
            },
        )

        resolved = resolve_action(intent)

        self.assertTrue(
            resolved.success
        )
        self.assertTrue(
            resolved.metadata.get(
                "preserves_human_agency"
            )
        )

        execution = execute_resolved_action(
            resolved
        )

        self.assertTrue(
            execution.executed
        )
        self.assertIn(
            "No internal state or voluntary choice is assigned",
            execution.description,
        )

        conn = database.get_connection()

        player_state_changes = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM state_changes
            WHERE world_event_id = ?
              AND entity_type = 'player_persona'
              AND entity_id = ?
            """,
            (
                execution.world_event_id,
                str(human_id),
            ),
        ).fetchone()

        conn.close()

        self.assertEqual(
            player_state_changes["count"],
            0,
        )

    def test_connected_movement_updates_reality_and_audit_log(self):
        actor = make_entity(
            "character",
            self.character_id,
            name="Test Matti",
        )

        destination = make_entity(
            "location",
            self.barn_id,
            name="Test Barn",
        )

        intent = make_action(
            ActionType.MOVE,
            actor=actor,
            destination=destination,
            description="Test Matti walks from the tavern to the barn.",
            source_type="integration_test",
        )

        resolved = resolve_action(intent)

        self.assertTrue(resolved.success)

        execution = execute_resolved_action(resolved)

        self.assertTrue(execution.executed)
        self.assertIsNotNone(execution.world_event_id)

        current = get_participant_location(
            "character",
            self.character_id,
        )

        self.assertEqual(
            current["location_id"],
            self.barn_id,
        )

        conn = database.get_connection()

        event = conn.execute(
            """
            SELECT *
            FROM world_events
            WHERE id = ?
            """,
            (execution.world_event_id,),
        ).fetchone()

        state_change = conn.execute(
            """
            SELECT *
            FROM state_changes
            WHERE world_event_id = ?
              AND entity_type = 'character'
              AND entity_id = ?
              AND field_name = 'location_id'
            """,
            (
                execution.world_event_id,
                str(self.character_id),
            ),
        ).fetchone()

        conn.close()

        self.assertIsNotNone(event)
        self.assertEqual(event["event_type"], "movement")
        self.assertEqual(event["outcome"], "moved")

        # Embedding must not be required for authoritative reality.
        self.assertIsNone(event["embedding"])

        self.assertIsNotNone(state_change)
        self.assertEqual(
            state_change["old_value"],
            str(self.tavern_id),
        )
        self.assertEqual(
            state_change["new_value"],
            str(self.barn_id),
        )

    def test_unconnected_movement_is_rejected_without_changing_reality(self):
        actor = make_entity(
            "character",
            self.character_id,
            name="Test Matti",
        )

        destination = make_entity(
            "location",
            self.cellar_id,
            name="Test Cellar",
        )

        before = get_participant_location(
            "character",
            self.character_id,
        )

        conn = database.get_connection()
        event_count_before = conn.execute(
            "SELECT COUNT(*) AS count FROM world_events"
        ).fetchone()["count"]
        conn.close()

        intent = make_action(
            ActionType.MOVE,
            actor=actor,
            destination=destination,
            description="Test Matti walks directly into the unconnected cellar.",
            source_type="integration_test",
        )

        resolved = resolve_action(intent)

        self.assertFalse(resolved.success)

        execution = execute_resolved_action(resolved)

        self.assertFalse(execution.executed)

        after = get_participant_location(
            "character",
            self.character_id,
        )

        self.assertEqual(
            before["location_id"],
            after["location_id"],
        )

        conn = database.get_connection()
        event_count_after = conn.execute(
            "SELECT COUNT(*) AS count FROM world_events"
        ).fetchone()["count"]
        conn.close()

        self.assertEqual(
            event_count_before,
            event_count_after,
        )

        self.assertFalse(self.test_db.exists() is False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
