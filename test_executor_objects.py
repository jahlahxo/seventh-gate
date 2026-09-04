import tempfile
import unittest
from pathlib import Path

import database
from actions import (
    ActionType,
    OutcomeDegree,
    ResolutionClass,
    ResolvedAction,
    make_action,
    make_entity,
)
from entities import (
    create_object,
    get_object_placement,
    get_object_state,
)
from executor import execute_resolved_action
from resolver import resolve_action
from world import (
    create_location,
    map_channel_to_location,
    move_participant,
)


class ObjectExecutorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(
            self.temp_dir.name
        ) / "seventh_gate_object_executor_test.db"

        database.set_database_path(
            self.test_db
        )
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
        self.matti_id = cursor.lastrowid

        cursor = conn.execute(
            """
            INSERT INTO characters (
                name,
                preferred_model
            )
            VALUES (?, ?)
            """,
            (
                "Test Pekka",
                "test-model",
            ),
        )
        self.pekka_id = cursor.lastrowid

        conn.commit()
        conn.close()

        self.room_id = create_location(
            "Test Tavern"
        )

        map_channel_to_location(
            self.room_id,
            "900000000000000100",
        )

        move_participant(
            "character",
            self.matti_id,
            self.room_id,
            source_type="integration_test",
        )

        move_participant(
            "character",
            self.pekka_id,
            self.room_id,
            source_type="integration_test",
        )

        self.matti = make_entity(
            "character",
            self.matti_id,
            "Test Matti",
        )

        self.pekka = make_entity(
            "character",
            self.pekka_id,
            "Test Pekka",
        )

    def tearDown(self):
        database.reset_database_path()
        self.temp_dir.cleanup()

    def _resolve_automatic(
        self,
        action_type,
        description,
        target=None,
        instrument=None,
    ):
        intent = make_action(
            action_type,
            actor=self.matti,
            description=description,
            target=target,
            instrument=instrument,
            source_type="integration_test",
        )

        return resolve_action(
            intent
        )

    def _successful_contested(
        self,
        action_type,
        description,
        target,
        instrument=None,
    ):
        intent = make_action(
            action_type,
            actor=self.matti,
            description=description,
            target=target,
            instrument=instrument,
            source_type="integration_test",
        )

        return ResolvedAction(
            intent=intent,
            resolution_class=ResolutionClass.CONTESTED,
            degree=OutcomeDegree.SUCCESS,
            success=True,
            outcome="Forced deterministic success for executor integration test.",
        )

    def test_take_moves_unattended_object_to_actor(self):
        knife_id = create_object(
            "Test Knife",
            initial_holder_type="location",
            initial_holder_id=self.room_id,
            initial_relation="at",
        )

        knife = make_entity(
            "object",
            knife_id,
            "Test Knife",
        )

        resolved = self._resolve_automatic(
            ActionType.TAKE,
            "Matti picks up the knife.",
            target=knife,
        )

        self.assertTrue(
            resolved.success
        )

        execution = execute_resolved_action(
            resolved
        )

        self.assertTrue(
            execution.executed
        )

        placement = get_object_placement(
            knife_id
        )

        self.assertEqual(
            placement["holder_type"],
            "character",
        )
        self.assertEqual(
            placement["holder_id"],
            str(self.matti_id),
        )

    def test_give_moves_owned_object_to_recipient(self):
        letter_id = create_object(
            "Test Letter",
            initial_holder_type="character",
            initial_holder_id=self.matti_id,
            initial_relation="carried",
        )

        letter = make_entity(
            "object",
            letter_id,
            "Test Letter",
        )

        resolved = self._resolve_automatic(
            ActionType.GIVE,
            "Matti gives Pekka the letter.",
            target=self.pekka,
            instrument=letter,
        )

        execution = execute_resolved_action(
            resolved
        )

        self.assertTrue(
            execution.executed
        )

        placement = get_object_placement(
            letter_id
        )

        self.assertEqual(
            placement["holder_type"],
            "character",
        )
        self.assertEqual(
            placement["holder_id"],
            str(self.pekka_id),
        )

    def test_drop_moves_owned_object_to_current_location(self):
        cup_id = create_object(
            "Test Cup",
            initial_holder_type="character",
            initial_holder_id=self.matti_id,
            initial_relation="held",
        )

        cup = make_entity(
            "object",
            cup_id,
            "Test Cup",
        )

        resolved = self._resolve_automatic(
            ActionType.DROP,
            "Matti puts the cup down.",
            target=cup,
        )

        execution = execute_resolved_action(
            resolved
        )

        self.assertTrue(
            execution.executed
        )

        placement = get_object_placement(
            cup_id
        )

        self.assertEqual(
            placement["holder_type"],
            "location",
        )
        self.assertEqual(
            placement["holder_id"],
            str(self.room_id),
        )

    def test_open_and_close_change_object_state(self):
        chest_id = create_object(
            "Test Chest",
            portable=False,
            is_container=True,
            is_openable=True,
            is_lockable=True,
            initial_holder_type="location",
            initial_holder_id=self.room_id,
            starts_open=False,
            starts_locked=False,
        )

        chest = make_entity(
            "object",
            chest_id,
            "Test Chest",
        )

        opened = execute_resolved_action(
            self._resolve_automatic(
                ActionType.OPEN,
                "Matti opens the chest.",
                target=chest,
            )
        )

        self.assertTrue(
            opened.executed
        )
        self.assertEqual(
            get_object_state(
                chest_id
            )["is_open"],
            1,
        )

        closed = execute_resolved_action(
            self._resolve_automatic(
                ActionType.CLOSE,
                "Matti closes the chest.",
                target=chest,
            )
        )

        self.assertTrue(
            closed.executed
        )
        self.assertEqual(
            get_object_state(
                chest_id
            )["is_open"],
            0,
        )

    def test_locked_object_rejects_open_without_state_change(self):
        chest_id = create_object(
            "Locked Chest",
            portable=False,
            is_container=True,
            is_openable=True,
            is_lockable=True,
            initial_holder_type="location",
            initial_holder_id=self.room_id,
            starts_open=False,
            starts_locked=True,
        )

        chest = make_entity(
            "object",
            chest_id,
            "Locked Chest",
        )

        result = execute_resolved_action(
            self._resolve_automatic(
                ActionType.OPEN,
                "Matti tries to open the locked chest.",
                target=chest,
            )
        )

        self.assertFalse(
            result.executed
        )

        state = get_object_state(
            chest_id
        )

        self.assertEqual(
            state["is_open"],
            0,
        )
        self.assertEqual(
            state["is_locked"],
            1,
        )

    def test_disarm_transfers_weapon_from_target_to_actor(self):
        knife_id = create_object(
            "Pekka's Knife",
            initial_holder_type="character",
            initial_holder_id=self.pekka_id,
            initial_relation="held",
        )

        knife = make_entity(
            "object",
            knife_id,
            "Pekka's Knife",
        )

        resolved = self._successful_contested(
            ActionType.DISARM,
            "Matti knocks the knife from Pekka's grip and takes it.",
            target=self.pekka,
            instrument=knife,
        )

        execution = execute_resolved_action(
            resolved
        )

        self.assertTrue(
            execution.executed
        )

        placement = get_object_placement(
            knife_id
        )

        self.assertEqual(
            placement["holder_type"],
            "character",
        )
        self.assertEqual(
            placement["holder_id"],
            str(self.matti_id),
        )
        self.assertEqual(
            placement["relation"],
            "held",
        )

        conn = database.get_connection()

        event = conn.execute(
            """
            SELECT *
            FROM world_events
            WHERE id = ?
            """,
            (
                execution.world_event_id,
            ),
        ).fetchone()

        change = conn.execute(
            """
            SELECT *
            FROM state_changes
            WHERE world_event_id = ?
              AND entity_type = 'object'
              AND entity_id = ?
              AND field_name = 'placement'
            """,
            (
                execution.world_event_id,
                str(knife_id),
            ),
        ).fetchone()

        conn.close()

        self.assertIsNotNone(
            event
        )
        self.assertEqual(
            event["event_type"],
            "disarm",
        )
        self.assertIsNotNone(
            change
        )
        self.assertIn(
            f"character:{self.pekka_id}:held",
            change["old_value"],
        )
        self.assertIn(
            f"character:{self.matti_id}:held",
            change["new_value"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
