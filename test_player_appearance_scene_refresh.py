import tempfile
import unittest
from pathlib import Path

import database
from campaign_clock import (
    initialize_campaign_clock,
)
from scene_refresh import (
    build_scene_refresh,
)
from world import (
    create_location,
    map_channel_to_location,
    move_participant,
)


class PlayerAppearanceSceneRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = (
            tempfile.TemporaryDirectory()
        )
        database.set_database_path(
            Path(self.tmp.name)
            / "appearance.db"
        )
        database.initialize_database()
        initialize_campaign_clock(
            "1878-11-10 18:30:00"
        )

        conn = database.get_connection()

        cursor = conn.execute(
            "INSERT INTO characters (name) VALUES ('Antti')"
        )
        self.antti = (
            cursor.lastrowid
        )

        cursor = conn.execute(
            """
            INSERT INTO player_personas (
                discord_user_id,
                rp_name,
                appearance
            )
            VALUES (?, ?, ?)
            """,
            (
                "123",
                "Anna",
                (
                    "A modern black rain jacket and "
                    "unfamiliar synthetic shoes."
                ),
            ),
        )
        self.player = (
            cursor.lastrowid
        )

        conn.commit()
        conn.close()

        self.room = create_location(
            "Tupa"
        )
        map_channel_to_location(
            self.room,
            "999",
        )
        move_participant(
            "character",
            self.antti,
            self.room,
            source_type="test",
        )
        move_participant(
            "player_persona",
            self.player,
            self.room,
            source_type="test",
        )

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_visible_player_appearance_reaches_director_scene_packet(self):
        result = build_scene_refresh(
            self.antti
        )

        player = next(
            person
            for person
            in result.objective_scene[
                "people"
            ]
            if person[
                "entity_type"
            ] == "player_persona"
        )

        self.assertIn(
            "modern black rain jacket",
            player[
                "appearance"
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
