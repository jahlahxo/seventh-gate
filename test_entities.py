import tempfile
import unittest
from pathlib import Path

import database
from entities import (
    add_condition,
    create_object,
    end_condition,
    get_active_conditions,
    get_inventory,
    get_object_placement,
    get_object_state,
    get_objects_held_by,
    place_object,
    set_object_locked,
    set_object_open,
)
from world import create_location


class EntityStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(self.temp_dir.name) / "seventh_gate_entities_test.db"

        database.set_database_path(self.test_db)
        database.initialize_database()

        conn = database.get_connection()

        cursor = conn.execute(
            """
            INSERT INTO characters (name, preferred_model)
            VALUES (?, ?)
            """,
            ("Test Matti", "test-model"),
        )
        self.character_id = cursor.lastrowid

        conn.commit()
        conn.close()

        self.room_id = create_location("Test Room")

    def tearDown(self):
        database.reset_database_path()
        self.temp_dir.cleanup()

    def test_object_moves_from_room_to_inventory(self):
        knife_id = create_object(
            "Test Knife",
            initial_holder_type="location",
            initial_holder_id=self.room_id,
            initial_relation="at",
        )

        place_object(
            knife_id,
            "character",
            self.character_id,
            "held",
        )

        placement = get_object_placement(knife_id)

        self.assertEqual(placement["holder_type"], "character")
        self.assertEqual(placement["holder_id"], str(self.character_id))
        self.assertEqual(placement["relation"], "held")

        inventory = get_inventory("character", self.character_id)
        self.assertEqual(len(inventory), 1)
        self.assertEqual(inventory[0]["name"], "Test Knife")

    def test_closed_container_rejects_inside_placement(self):
        chest_id = create_object(
            "Test Chest",
            portable=False,
            is_container=True,
            is_openable=True,
            is_lockable=True,
            initial_holder_type="location",
            initial_holder_id=self.room_id,
            initial_relation="at",
            starts_open=False,
            starts_locked=False,
        )

        letter_id = create_object(
            "Test Letter",
            initial_holder_type="location",
            initial_holder_id=self.room_id,
            initial_relation="at",
        )

        with self.assertRaises(PermissionError):
            place_object(
                letter_id,
                "object",
                chest_id,
                "inside",
            )

        set_object_open(chest_id, True)

        place_object(
            letter_id,
            "object",
            chest_id,
            "inside",
        )

        contents = get_objects_held_by("object", chest_id, "inside")
        self.assertEqual(len(contents), 1)
        self.assertEqual(contents[0]["id"], letter_id)

    def test_locked_container_cannot_be_opened(self):
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

        with self.assertRaises(PermissionError):
            set_object_open(chest_id, True)

        set_object_locked(chest_id, False)
        state = set_object_open(chest_id, True)

        self.assertEqual(state["is_open"], 1)
        self.assertEqual(state["is_locked"], 0)

    def test_container_cycle_is_rejected(self):
        box_a = create_object(
            "Box A",
            is_container=True,
            is_openable=True,
            starts_open=True,
            initial_holder_type="location",
            initial_holder_id=self.room_id,
        )

        box_b = create_object(
            "Box B",
            is_container=True,
            is_openable=True,
            starts_open=True,
            initial_holder_type="location",
            initial_holder_id=self.room_id,
        )

        place_object(box_b, "object", box_a, "inside")

        with self.assertRaises(ValueError):
            place_object(box_a, "object", box_b, "inside")

    def test_character_condition_can_start_and_end(self):
        condition_id = add_condition(
            "character",
            self.character_id,
            condition_type="injury",
            name="Bruised Hand",
            severity=2,
            description="A painful bruise across the knuckles.",
        )

        active = get_active_conditions(
            "character",
            self.character_id,
        )

        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["name"], "Bruised Hand")
        self.assertEqual(active[0]["severity"], 2)

        end_condition(condition_id)

        active_after = get_active_conditions(
            "character",
            self.character_id,
        )

        self.assertEqual(active_after, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
