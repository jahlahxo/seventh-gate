import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import database
from campaign import set_campaign_setting
from scene_memory import (
    build_continuity_context,
    commit_character_turn,
    compact_public_history,
    estimate_tokens,
    get_open_threads,
    get_recent_public_turns,
    open_thread,
    record_human_story_post_for_characters,
    record_perceived_public_turn,
    resolve_thread,
)


class SceneMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.set_database_path(
            Path(self.tmp.name)
            / "memory.db"
        )
        database.initialize_database()

        conn = database.get_connection()
        cursor = conn.execute(
            "INSERT INTO characters (name) VALUES ('Antti')"
        )
        self.antti = cursor.lastrowid
        cursor = conn.execute(
            "INSERT INTO characters (name) VALUES ('Kaisa')"
        )
        self.kaisa = cursor.lastrowid
        cursor = conn.execute(
            "INSERT INTO locations (name) VALUES ('Inside')"
        )
        self.inside = cursor.lastrowid
        cursor = conn.execute(
            "INSERT INTO locations (name) VALUES ('Outside')"
        )
        self.outside = cursor.lastrowid

        conn.commit()
        conn.close()

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_human_italic_thought_never_enters_ai_history(self):
        parsed, _ = record_human_story_post_for_characters(
            'Anna smiles. "Fine." *I hate this.*',
            [
                self.antti,
                self.kaisa,
            ],
            speaker_id=4,
            speaker_name="Anna",
        )

        self.assertEqual(
            parsed.thoughts,
            ("I hate this.",),
        )

        for character_id in (
            self.antti,
            self.kaisa,
        ):
            rendered = repr(
                build_continuity_context(
                    character_id
                )
            )
            self.assertNotIn(
                "I hate this.",
                rendered,
            )
            self.assertIn(
                'Anna smiles. "Fine."',
                rendered,
            )

    def test_ai_private_thought_is_owner_only(self):
        turn = SimpleNamespace(
            public='Antti says, "Fine."',
            thought="I do not trust her.",
            open_threads=(),
            resolve_thread_ids=(),
        )

        commit_character_turn(
            self.antti,
            turn,
            [
                self.kaisa,
            ],
            speaker_name="Antti",
        )

        ant = repr(
            build_continuity_context(
                self.antti
            )
        )
        kai = repr(
            build_continuity_context(
                self.kaisa
            )
        )

        self.assertIn(
            "I do not trust her.",
            ant,
        )
        self.assertNotIn(
            "I do not trust her.",
            kai,
        )

    def test_public_history_is_character_scoped_by_perception(self):
        record_perceived_public_turn(
            self.antti,
            "A whispered secret Antti heard.",
            speaker_name="Elias",
        )

        self.assertIn(
            "whispered secret",
            repr(
                build_continuity_context(
                    self.antti
                )
            ),
        )
        self.assertNotIn(
            "whispered secret",
            repr(
                build_continuity_context(
                    self.kaisa
                )
            ),
        )

    def test_budget_keeps_newest_perceived_turns(self):
        set_campaign_setting(
            "recent_scene_token_budget",
            "500",
        )

        for number in range(10):
            record_perceived_public_turn(
                self.antti,
                f"turn-{number} "
                + ("x" * 300),
                speaker_name="Elias",
            )

        rows = get_recent_public_turns(
            self.antti,
            token_budget=120,
        )

        self.assertTrue(
            rows
        )
        self.assertIn(
            "turn-9",
            rows[-1][
                "content"
            ],
        )
        self.assertNotIn(
            "turn-0",
            " ".join(
                row["content"]
                for row in rows
            ),
        )

    def test_recent_continuity_can_cross_location_change(self):
        record_perceived_public_turn(
            self.antti,
            "I am going outside to find Elina.",
            location_id=self.inside,
            speaker_name="Antti",
        )
        record_perceived_public_turn(
            self.antti,
            "Cold air hits his face.",
            location_id=self.outside,
            speaker_name="World",
        )

        text = repr(
            build_continuity_context(
                self.antti
            )[
                "recent_public"
            ]
        )

        self.assertIn(
            "going outside",
            text,
        )
        self.assertIn(
            "Cold air",
            text,
        )

    def test_compaction_creates_rolling_summary(self):
        for number in range(5):
            record_perceived_public_turn(
                self.antti,
                f"Old detail {number}. "
                + ("x" * 50),
                scene_id=None,
                speaker_name="Elias",
            )

        compacted = compact_public_history(
            self.antti,
            token_budget=25,
        )

        continuity = build_continuity_context(
            self.antti
        )

        self.assertGreater(
            compacted,
            0,
        )
        self.assertTrue(
            continuity[
                "scene_summaries"
            ]
        )
        self.assertIn(
            "Old detail",
            continuity[
                "scene_summaries"
            ][0]["summary"],
        )

    def test_open_thread_survives_as_character_bound_business(self):
        thread_id = open_thread(
            self.antti,
            "Find Elina outside.",
        )
        threads = get_open_threads(
            self.antti
        )

        self.assertEqual(
            len(threads),
            1,
        )
        self.assertEqual(
            int(
                threads[0][
                    "id"
                ]
            ),
            thread_id,
        )

    def test_thread_can_be_resolved(self):
        thread_id = open_thread(
            self.antti,
            "Answer Kaisa's question.",
        )

        self.assertTrue(
            resolve_thread(
                self.antti,
                thread_id,
            )
        )
        self.assertEqual(
            get_open_threads(
                self.antti
            ),
            [],
        )

    def test_duplicate_open_thread_is_not_duplicated(self):
        first = open_thread(
            self.antti,
            "Bring the coat.",
        )
        second = open_thread(
            self.antti,
            "bring the coat.",
        )

        self.assertEqual(
            first,
            second,
        )
        self.assertEqual(
            len(
                get_open_threads(
                    self.antti
                )
            ),
            1,
        )

    def test_token_estimate_scales_with_content_length(self):
        self.assertGreater(
            estimate_tokens(
                "hello " * 100
            ),
            estimate_tokens(
                "hello"
            ),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
