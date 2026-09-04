import tempfile
import unittest
from pathlib import Path

import database
from campaign_clock import (
    initialize_campaign_clock,
)
from entities import (
    create_object,
    get_object_placement,
)
from scene_refresh import (
    SceneRefreshResult,
    build_scene_refresh,
)
from world import (
    connect_locations,
    create_location,
    map_channel_to_location,
    move_participant,
    record_world_event,
)


class FakeExecution:
    def __init__(
        self,
        *,
        executed=True,
        world_event_id=None,
        description=None,
        reason=None,
    ):
        self.executed = executed
        self.world_event_id = (
            world_event_id
        )
        self.description = description
        self.reason = reason


class SceneRefreshTests(
    unittest.TestCase
):
    def setUp(self):
        self.tmp = (
            tempfile.TemporaryDirectory()
        )

        database.set_database_path(
            Path(self.tmp.name)
            / "scene_refresh.db"
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
                appearance,
                personality,
                private_character_notes,
                preferred_model
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "Mara",
                "Dark hair and a red coat.",
                "Curious.",
                "SECRET: hidden heir.",
                "test-model",
            ),
        )
        self.mara = cursor.lastrowid

        cursor = conn.execute(
            """
            INSERT INTO characters (
                name,
                appearance,
                personality,
                private_character_notes,
                preferred_model
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "Elias",
                "Tall, wearing a grey coat.",
                "Jealous.",
                "SECRET: plans betrayal.",
                "test-model",
            ),
        )
        self.elias = cursor.lastrowid

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
                "becca",
                "Elina",
            ),
        )
        self.player = cursor.lastrowid

        conn.commit()
        conn.close()

        self.room = create_location(
            "Common Room",
            description=(
                "A warm room with a long table."
            ),
            private_notes=(
                "SECRET PASSAGE behind hearth."
            ),
        )

        self.hall = create_location(
            "Hall",
            description="A narrow hall.",
        )

        map_channel_to_location(
            self.room,
            "1001",
        )
        map_channel_to_location(
            self.hall,
            "1002",
        )

        connect_locations(
            self.room,
            self.hall,
            bidirectional=True,
        )

        move_participant(
            "character",
            self.mara,
            self.room,
            source_type="test",
        )

        move_participant(
            "character",
            self.elias,
            self.room,
            source_type="test",
        )

        move_participant(
            "player_persona",
            self.player,
            self.room,
            source_type="test",
        )

        self.chest = create_object(
            "Oak Chest",
            object_type="container",
            description=(
                "A heavy oak chest."
            ),
            portable=False,
            is_container=True,
            is_openable=True,
            is_lockable=True,
            starts_open=False,
            starts_locked=True,
            lock_code="TOP-SECRET-LOCK",
            notes="SECRET OBJECT NOTES",
            initial_holder_type=
                "location",
            initial_holder_id=
                self.room,
            initial_relation="at",
        )

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_refresh_rebuilds_public_location_without_private_notes(
        self
    ):
        result = build_scene_refresh(
            self.mara
        )

        self.assertIsInstance(
            result,
            SceneRefreshResult,
        )

        location = (
            result.objective_scene[
                "location"
            ]
        )

        self.assertEqual(
            location["name"],
            "Common Room",
        )

        rendered = repr(
            result.objective_scene
        )

        self.assertNotIn(
            "SECRET PASSAGE",
            rendered,
        )

    def test_people_are_current_colocated_public_identities_only(
        self
    ):
        result = build_scene_refresh(
            self.mara
        )

        people = (
            result.objective_scene[
                "people"
            ]
        )

        names = {
            person["name"]
            for person in people
        }

        self.assertEqual(
            names,
            {
                "Elias",
                "Elina",
            },
        )

        rendered = repr(people)

        self.assertNotIn(
            "plans betrayal",
            rendered,
        )
        self.assertNotIn(
            "hidden heir",
            rendered,
        )

    def test_object_packet_excludes_secret_lock_material(
        self
    ):
        result = build_scene_refresh(
            self.mara
        )

        objects = (
            result.objective_scene[
                "objects"
            ]
        )

        self.assertEqual(
            len(objects),
            1,
        )
        self.assertEqual(
            objects[0]["name"],
            "Oak Chest",
        )
        self.assertFalse(
            objects[0]["is_open"]
        )

        rendered = repr(objects)

        self.assertNotIn(
            "TOP-SECRET-LOCK",
            rendered,
        )
        self.assertNotIn(
            "SECRET OBJECT NOTES",
            rendered,
        )
        self.assertNotIn(
            "is_locked",
            rendered,
        )

    def test_permitted_entities_are_derived_from_engine_state(
        self
    ):
        result = build_scene_refresh(
            self.mara
        )

        refs = {
            (
                ref.entity_type,
                ref.entity_id,
            )
            for ref
            in result.permitted_entities
        }

        self.assertIn(
            (
                "character",
                str(self.elias),
            ),
            refs,
        )
        self.assertIn(
            (
                "player_persona",
                str(self.player),
            ),
            refs,
        )
        self.assertIn(
            (
                "object",
                str(self.chest),
            ),
            refs,
        )
        self.assertIn(
            (
                "location",
                str(self.hall),
            ),
            refs,
        )

        self.assertNotIn(
            (
                "character",
                str(self.mara),
            ),
            refs,
        )

    def test_execution_world_event_is_included_when_relevant(
        self
    ):
        event_id = record_world_event(
            event_type="test_event",
            content=(
                "The oak chest makes a loud click."
            ),
            source_type="test",
            location_id=self.room,
            actor_type="character",
            actor_id=self.mara,
            outcome="clicked",
        )

        execution = FakeExecution(
            executed=True,
            world_event_id=event_id,
            description=(
                "Mara touches the chest."
            ),
        )

        result = build_scene_refresh(
            self.mara,
            execution=execution,
        )

        recent = (
            result.objective_scene[
                "recent_event"
            ]
        )

        self.assertEqual(
            recent["world_event_id"],
            event_id,
        )
        self.assertEqual(
            recent["outcome"],
            "clicked",
        )
        self.assertEqual(
            result.source_world_event_id,
            event_id,
        )

    def test_unrelated_event_is_not_leaked(
        self
    ):
        other = create_location(
            "Far Room"
        )
        map_channel_to_location(
            other,
            "1003",
        )

        event_id = record_world_event(
            event_type="secret_elsewhere",
            content=(
                "Something happens far away."
            ),
            source_type="test",
            location_id=other,
            actor_type="character",
            actor_id=self.elias,
        )

        execution = FakeExecution(
            executed=True,
            world_event_id=event_id,
        )

        result = build_scene_refresh(
            self.mara,
            execution=execution,
        )

        self.assertIsNone(
            result.objective_scene[
                "recent_event"
            ]
        )

    def test_refresh_reads_post_change_location_state(
        self
    ):
        move_participant(
            "character",
            self.mara,
            self.hall,
            source_type="test",
        )

        result = build_scene_refresh(
            self.mara
        )

        self.assertEqual(
            result.location_id,
            self.hall,
        )
        self.assertEqual(
            result.objective_scene[
                "location"
            ]["name"],
            "Hall",
        )

        refs = {
            (
                ref.entity_type,
                ref.entity_id,
            )
            for ref
            in result.permitted_entities
        }

        self.assertIn(
            (
                "location",
                str(self.room),
            ),
            refs,
        )

    def test_character_without_location_cannot_refresh_scene(
        self
    ):
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
                "Nowhere NPC",
                "test-model",
            ),
        )

        nowhere = cursor.lastrowid

        conn.commit()
        conn.close()

        with self.assertRaises(
            RuntimeError
        ):
            build_scene_refresh(
                nowhere
            )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
