import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from campaign_clock import initialize_campaign_clock
from character_context import (
    MAX_RENDERED_CONTEXT_CHARS,
    build_character_context,
    render_character_context,
)
from characters import (
    add_trait,
    set_attribute,
    set_skill,
)
from development import set_development_profile
from world import (
    create_location,
    map_channel_to_location,
    move_participant,
)


class CharacterContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

        database.set_database_path(
            Path(self.tmp.name)
            / "character_context.db"
        )
        database.initialize_database()

        initialize_campaign_clock(
            "2001-01-01 12:00:00"
        )

        conn = database.get_connection()

        cursor = conn.execute(
            """
            INSERT INTO characters (
                name,
                description,
                personality,
                background,
                appearance,
                speech_style,
                goals,
                fears,
                values_beliefs,
                habits_mannerisms,
                private_character_notes,
                preferred_model,
                fallback_models
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Mara",
                "A young traveler.",
                "Curious and stubborn.",
                "Raised near the coast.",
                "Dark hair.",
                "Plainspoken.",
                "Find her brother.",
                "Being abandoned.",
                "Loyalty matters.",
                "Taps her fingers when impatient.",
                "AUTHOR SECRET: Mara is unknowingly the lost heir.",
                "brain-model",
                "fallback-a,fallback-b",
            ),
        )
        self.mara = cursor.lastrowid

        cursor = conn.execute(
            """
            INSERT INTO characters (
                name,
                personality,
                private_character_notes,
                preferred_model
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "Elias",
                "Secretly terrified and jealous.",
                "PRIVATE: plans to betray Mara tonight.",
                "other-model",
            ),
        )
        self.elias = cursor.lastrowid

        conn.commit()
        conn.close()

        self.room = create_location(
            "Common Room",
            description="A warm public room with a long wooden table.",
            private_notes="SECRET PASSAGE behind the hearth.",
        )

        map_channel_to_location(
            self.room,
            "123456",
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

        set_attribute(
            "character",
            self.mara,
            "Perception",
            3,
        )

        set_skill(
            "character",
            self.mara,
            "Observation",
            3,
        )

        add_trait(
            "character",
            self.mara,
            "Patient Listener",
            description="Usually listens before speaking.",
        )

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def _build(
        self,
        *,
        perception=None,
        retrieval=None,
    ):
        if perception is None:
            perception = {
                "current": "Lina asks what Mara thinks.",
            }

        if retrieval is None:
            retrieval = {
                "memories": [],
                "knowledge": [],
            }

        with patch(
            "character_context.retrieve_for_character",
            return_value=retrieval,
        ):
            return build_character_context(
                self.mara,
                perception,
            )

    def test_identity_is_whitelisted_and_private_notes_do_not_leak(self):
        context = self._build()
        rendered = render_character_context(
            context
        )

        self.assertIn(
            "Curious and stubborn.",
            rendered,
        )
        self.assertNotIn(
            "AUTHOR SECRET",
            rendered,
        )
        self.assertNotIn(
            "private_character_notes",
            rendered,
        )

    def test_runtime_model_metadata_is_not_rendered_to_character(self):
        context = self._build()

        self.assertEqual(
            context["runtime"][
                "preferred_model"
            ],
            "brain-model",
        )

        rendered = render_character_context(
            context
        )

        self.assertNotIn(
            "brain-model",
            rendered,
        )
        self.assertNotIn(
            "fallback-a",
            rendered,
        )

    def test_colocation_does_not_automatically_become_perception(self):
        context = self._build()
        rendered = render_character_context(
            context
        )

        # Elias is physically co-located, but the context assembler must not
        # decide that Mara perceives him. That belongs to Director/perception.
        self.assertNotIn(
            "Elias",
            rendered,
        )
        self.assertFalse(
            context["access_boundary"][
                "automatic_colocation_perception_included"
            ]
        )

    def test_only_explicitly_filtered_perception_is_rendered(self):
        context = self._build(
            perception={
                "current": "Elias says hello.",
                "people": [
                    {
                        "name": "Elias",
                        "observable": "standing by the table",
                    }
                ],
                "environment": "Rain taps against the windows.",
            }
        )

        rendered = render_character_context(
            context
        )

        self.assertIn(
            "Elias",
            rendered,
        )
        self.assertIn(
            "Rain taps against the windows.",
            rendered,
        )

    def test_raw_rp_history_is_never_loaded(self):
        conn = database.get_connection()

        conn.execute(
            """
            INSERT INTO rp_messages (
                discord_message_id,
                discord_channel_id,
                author_type,
                author_id,
                author_name,
                character_id,
                content
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "msg-secret",
                "123456",
                "character",
                str(self.elias),
                "Elias",
                self.elias,
                "*Elias privately decides to murder Mara tonight.*",
            ),
        )

        conn.commit()
        conn.close()

        context = self._build()
        rendered = render_character_context(
            context
        )

        self.assertNotIn(
            "murder Mara tonight",
            rendered,
        )
        self.assertFalse(
            context["access_boundary"][
                "raw_rp_history_included"
            ]
        )

    def test_location_private_notes_do_not_leak(self):
        context = self._build()

        self.assertEqual(
            context["situation"][
                "location"
            ]["name"],
            "Common Room",
        )

        rendered = render_character_context(
            context
        )

        self.assertIn(
            "warm public room",
            rendered,
        )
        self.assertNotIn(
            "SECRET PASSAGE",
            rendered,
        )

    def test_unconfigured_attributes_are_not_misrepresented_as_weaknesses(self):
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
                "Unconfigured",
                "test-model",
            ),
        )
        other = cursor.lastrowid
        conn.commit()
        conn.close()

        with patch(
            "character_context.retrieve_for_character",
            return_value={
                "memories": [],
                "knowledge": [],
            },
        ):
            context = build_character_context(
                other,
                {"current": "Hello."},
            )

        self.assertEqual(
            context["self"][
                "capabilities"
            ]["attributes"],
            {},
        )

    def test_capabilities_are_character_facing_without_game_numbers(self):
        context = self._build()
        rendered = render_character_context(
            context
        )

        self.assertIn(
            "Perception=strong",
            rendered,
        )
        self.assertIn(
            "Observation=skilled",
            rendered,
        )
        self.assertIn(
            "Patient Listener",
            rendered,
        )

        self.assertNotIn(
            "Perception=3",
            rendered,
        )

    def test_only_this_characters_subjective_relationship_rows_are_loaded(self):
        conn = database.get_connection()

        conn.execute(
            """
            INSERT INTO relationships (
                character_id,
                target_type,
                target_id,
                relationship_label,
                summary,
                affection,
                trust
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.mara,
                "character",
                str(self.elias),
                "friend",
                "Mara currently trusts Elias.",
                2,
                3,
            ),
        )

        conn.execute(
            """
            INSERT INTO relationships (
                character_id,
                target_type,
                target_id,
                relationship_label,
                summary
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                self.elias,
                "character",
                str(self.mara),
                "rival",
                "Elias privately resents Mara.",
            ),
        )

        conn.commit()
        conn.close()

        context = self._build()
        rendered = render_character_context(
            context
        )

        self.assertIn(
            "Mara currently trusts Elias.",
            rendered,
        )
        self.assertNotIn(
            "Elias privately resents Mara.",
            rendered,
        )

    def test_semantic_retrieval_is_limited_to_character_memory_and_knowledge(self):
        class Row(dict):
            pass

        retrieval = {
            "memories": [
                {
                    "row": Row(
                        content="Mara remembers sharing bread with Lina.",
                        memory_type="event",
                        emotional_context="warm",
                        importance=6,
                        confidence=1.0,
                    ),
                    "similarity": 0.9,
                }
            ],
            "knowledge": [
                {
                    "row": Row(
                        content="Mara believes the north road is flooded.",
                        knowledge_type="belief",
                        subject_type="location",
                        subject_id="9",
                        confidence=0.7,
                        importance=5,
                        is_secret=0,
                    ),
                    "similarity": 0.8,
                }
            ],
        }

        context = self._build(
            retrieval=retrieval
        )

        rendered = render_character_context(
            context
        )

        self.assertIn(
            "Mara remembers sharing bread with Lina.",
            rendered,
        )
        self.assertIn(
            "Mara believes the north road is flooded.",
            rendered,
        )

    def test_developmental_grounding_is_included_without_objective_family_links(self):
        conn = database.get_connection()

        conn.execute(
            """
            INSERT INTO entity_life_profiles (
                owner_type,
                owner_id,
                birth_date
            )
            VALUES (?, ?, ?)
            """,
            (
                "character",
                str(self.mara),
                "1996-01-01",
            ),
        )

        conn.commit()
        conn.close()

        set_development_profile(
            self.mara,
            developmental_notes=(
                "Bright for her age, but sheltered from adult politics."
            ),
            ai_participation_mode="full",
        )

        context = self._build()
        rendered = render_character_context(
            context
        )

        self.assertIn(
            "DEVELOPMENTAL GROUNDING",
            rendered,
        )
        self.assertIn(
            "Bright for her age",
            rendered,
        )
        self.assertNotIn(
            "care_relationships",
            str(context),
        )

        self.assertFalse(
            context["access_boundary"][
                "objective_family_links_included"
            ]
        )

    def test_private_character_addressed_sensory_notices_can_be_supplied_without_hidden_truth(self):
        context = self._build(
            perception={
                "current": "Mara wakes.",
                "private": [
                    "You feel unusually nauseated this morning.",
                ],
            }
        )

        rendered = render_character_context(
            context
        )

        self.assertIn(
            "unusually nauseated",
            rendered,
        )
        self.assertNotIn(
            "pregnant",
            rendered.lower(),
        )

    def test_context_contains_no_global_truth_lore_events_or_hidden_reproduction(self):
        context = self._build()

        self.assertNotIn(
            "canonical_facts",
            context,
        )
        self.assertNotIn(
            "world_lore",
            context,
        )
        self.assertNotIn(
            "world_events",
            context,
        )
        self.assertNotIn(
            "pregnancies",
            context,
        )

        for value in context[
            "access_boundary"
        ].values():
            self.assertFalse(value)

    def test_deceased_character_cannot_be_invoked_even_if_mode_is_full(self):
        set_development_profile(
            self.mara,
            ai_participation_mode="full",
        )

        conn = database.get_connection()
        conn.execute(
            """
            INSERT INTO entity_mortality (
                owner_type,
                owner_id,
                status,
                death_datetime
            )
            VALUES (?, ?, 'deceased', ?)
            """,
            (
                "character",
                str(self.mara),
                "2001-01-01 11:00:00",
            ),
        )
        conn.commit()
        conn.close()

        context = self._build()

        self.assertFalse(
            context["runtime"][
                "may_invoke_ai_brain"
            ]
        )

    def test_rendered_context_has_hard_size_guard(self):
        huge = "x" * 50000

        context = self._build(
            perception={
                "current": huge,
                "environment": huge,
                "recent": [huge] * 30,
            }
        )

        rendered = render_character_context(
            context
        )

        self.assertLessEqual(
            len(rendered),
            MAX_RENDERED_CONTEXT_CHARS + 100,
        )
        self.assertIn(
            "Context truncated",
            rendered,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
