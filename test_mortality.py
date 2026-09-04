import tempfile
import unittest
from pathlib import Path

import database
from actions import (
    ActionType,
    ResolutionClass,
    make_action,
    make_entity,
)
from campaign_clock import initialize_campaign_clock
from executor import execute_resolved_action
from mortality import (
    get_mortality,
    is_alive,
    record_death,
)
from resolver import resolve_action
from world import (
    create_location,
    get_participant_location,
    map_channel_to_location,
    move_participant,
)


class MortalityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

        database.set_database_path(
            Path(self.tmp.name)
            / "mortality.db"
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
            (
                "Mortality Test NPC",
                "test-model",
            ),
        )
        self.npc = cursor.lastrowid

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
                "900000000000000777",
                "mortality-human",
                "Mortality Human",
            ),
        )
        self.human = cursor.lastrowid

        conn.commit()
        conn.close()

        self.room = create_location(
            "Mortality Test Room"
        )

        map_channel_to_location(
            self.room,
            "900000000000000778",
        )

        move_participant(
            "character",
            self.npc,
            self.room,
            source_type="test",
        )

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_entity_is_living_until_death_is_recorded(self):
        self.assertTrue(
            is_alive(
                "character",
                self.npc,
            )
        )

        self.assertEqual(
            get_mortality(
                "character",
                self.npc,
            )["status"],
            "living",
        )

    def test_record_death_preserves_entity_and_location(self):
        record_death(
            "character",
            self.npc,
            cause_of_death="test cause",
            manner_of_death="test",
        )

        self.assertFalse(
            is_alive(
                "character",
                self.npc,
            )
        )

        location = get_participant_location(
            "character",
            self.npc,
        )

        self.assertEqual(
            location["location_id"],
            self.room,
        )

        conn = database.get_connection()

        row = conn.execute(
            """
            SELECT active
            FROM characters
            WHERE id = ?
            """,
            (self.npc,),
        ).fetchone()

        conn.close()

        self.assertEqual(
            row["active"],
            1,
        )

    def test_deceased_character_cannot_act(self):
        record_death(
            "character",
            self.npc,
            cause_of_death="test",
        )

        actor = make_entity(
            "character",
            self.npc,
            "Mortality Test NPC",
        )

        intent = make_action(
            ActionType.OTHER,
            actor=actor,
            description=(
                "The deceased character attempts to act."
            ),
            source_type="test",
            metadata={
                "automatic": True,
            },
        )

        resolved = resolve_action(
            intent
        )

        self.assertFalse(
            resolved.success
        )
        self.assertEqual(
            resolved.resolution_class,
            ResolutionClass.IMPOSSIBLE,
        )

        executed = execute_resolved_action(
            resolved
        )

        self.assertFalse(
            executed.executed
        )

    def test_human_persona_can_also_have_objective_death_state(self):
        record_death(
            "player_persona",
            self.human,
            cause_of_death="story event",
        )

        self.assertFalse(
            is_alive(
                "player_persona",
                self.human,
            )
        )

    def test_second_death_record_is_rejected(self):
        record_death(
            "character",
            self.npc,
            cause_of_death="first",
        )

        with self.assertRaises(
            ValueError
        ):
            record_death(
                "character",
                self.npc,
                cause_of_death="second",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
