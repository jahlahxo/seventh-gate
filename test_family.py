import tempfile
import unittest
from pathlib import Path

import database
from campaign_clock import (
    advance_campaign_time,
    initialize_campaign_clock,
)
from family import (
    add_family_link,
    create_birth,
    get_birth_children,
    get_family_links,
    name_child,
)
from life import get_age_years
from reproduction import create_pregnancy


class FamilyBirthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

        database.set_database_path(
            Path(self.tmp.name)
            / "family_birth.db"
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
                "Parent A",
                "test-model",
            ),
        )
        self.parent_a = cursor.lastrowid

        cursor = conn.execute(
            """
            INSERT INTO characters (
                name,
                preferred_model
            )
            VALUES (?, ?)
            """,
            (
                "Parent B",
                "test-model",
            ),
        )
        self.parent_b = cursor.lastrowid

        conn.commit()
        conn.close()

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_birth_ends_pregnancy_and_creates_child(self):
        pregnancy = create_pregnancy(
            "character",
            self.parent_a,
            other_parent_type="character",
            other_parent_id=self.parent_b,
            gestational_age_days=280,
            origin_type="biological",
        )

        result = create_birth(
            pregnancy["id"],
            [
                {
                    "name": "Elina",
                }
            ],
        )

        self.assertEqual(
            result["birth"]["pregnancy_id"],
            pregnancy["id"],
        )

        self.assertEqual(
            len(result["children"]),
            1,
        )

        conn = database.get_connection()

        ended = conn.execute(
            """
            SELECT status, outcome
            FROM pregnancies
            WHERE id = ?
            """,
            (pregnancy["id"],),
        ).fetchone()

        conn.close()

        self.assertEqual(
            ended["status"],
            "ended",
        )
        self.assertEqual(
            ended["outcome"],
            "birth",
        )

    def test_born_child_age_uses_campaign_clock(self):
        pregnancy = create_pregnancy(
            "character",
            self.parent_a,
            gestational_age_days=280,
            origin_type="unknown",
        )

        result = create_birth(
            pregnancy["id"],
            [
                {
                    "name": "Mika",
                }
            ],
        )

        child_id = result[
            "children"
        ][0]["child_character_id"]

        self.assertEqual(
            get_age_years(
                "character",
                child_id,
            ),
            0,
        )

        advance_campaign_time(
            days=365,
            reason="A year passes.",
            source_type="test",
        )

        self.assertEqual(
            get_age_years(
                "character",
                child_id,
            ),
            1,
        )

    def test_biological_birth_creates_parent_links(self):
        pregnancy = create_pregnancy(
            "character",
            self.parent_a,
            other_parent_type="character",
            other_parent_id=self.parent_b,
            gestational_age_days=280,
            origin_type="biological",
        )

        result = create_birth(
            pregnancy["id"],
            [
                {
                    "name": "Aino",
                }
            ],
        )

        child_id = result[
            "children"
        ][0]["child_character_id"]

        parents = get_family_links(
            "character",
            child_id,
            relation_type="biological_parent",
        )

        parent_ids = {
            row["relative_id"]
            for row in parents
        }

        self.assertEqual(
            parent_ids,
            {
                str(self.parent_a),
                str(self.parent_b),
            },
        )

        gestational = get_family_links(
            "character",
            child_id,
            relation_type="gestational_parent",
        )

        self.assertEqual(
            gestational[0]["relative_id"],
            str(self.parent_a),
        )

    def test_nonbiological_origin_does_not_invent_biological_parentage(self):
        pregnancy = create_pregnancy(
            "character",
            self.parent_a,
            other_parent_type="character",
            other_parent_id=self.parent_b,
            gestational_age_days=280,
            origin_type="magical",
        )

        result = create_birth(
            pregnancy["id"],
            [
                {
                    "name": "Sora",
                }
            ],
        )

        child_id = result[
            "children"
        ][0]["child_character_id"]

        biological = get_family_links(
            "character",
            child_id,
            relation_type="biological_parent",
        )

        self.assertEqual(
            biological,
            [],
        )

        gestational = get_family_links(
            "character",
            child_id,
            relation_type="gestational_parent",
        )

        self.assertEqual(
            len(gestational),
            1,
        )

    def test_twins_are_distinct_persistent_characters_and_siblings(self):
        pregnancy = create_pregnancy(
            "character",
            self.parent_a,
            gestational_age_days=280,
            origin_type="unknown",
        )

        result = create_birth(
            pregnancy["id"],
            [
                {"name": "Twin One"},
                {"name": "Twin Two"},
            ],
        )

        children = result["children"]

        self.assertEqual(
            len(children),
            2,
        )

        first = children[0][
            "child_character_id"
        ]
        second = children[1][
            "child_character_id"
        ]

        siblings = get_family_links(
            "character",
            first,
            relation_type="sibling",
        )

        self.assertEqual(
            siblings[0]["relative_id"],
            str(second),
        )

    def test_child_can_be_born_unnamed_then_named_later(self):
        pregnancy = create_pregnancy(
            "character",
            self.parent_a,
            gestational_age_days=280,
            origin_type="unknown",
        )

        result = create_birth(
            pregnancy["id"],
            [
                {},
            ],
        )

        child = result[
            "children"
        ][0]

        self.assertIsNone(
            child["given_name"]
        )

        name_child(
            child["child_character_id"],
            "Leena",
        )

        children = get_birth_children(
            result["birth"]["id"]
        )

        self.assertEqual(
            children[0]["given_name"],
            "Leena",
        )
        self.assertEqual(
            children[0]["character_name"],
            "Leena",
        )

    def test_caregiver_is_objective_relation_not_biological_parent(self):
        pregnancy = create_pregnancy(
            "character",
            self.parent_a,
            gestational_age_days=280,
            origin_type="unknown",
        )

        result = create_birth(
            pregnancy["id"],
            [
                {
                    "name": "Olli",
                }
            ],
        )

        child_id = result[
            "children"
        ][0]["child_character_id"]

        add_family_link(
            "character",
            child_id,
            "character",
            self.parent_b,
            "caregiver",
            source_type="story",
            source_id="placement-1",
        )

        caregivers = get_family_links(
            "character",
            child_id,
            relation_type="caregiver",
        )

        biological = get_family_links(
            "character",
            child_id,
            relation_type="biological_parent",
        )

        self.assertEqual(
            len(caregivers),
            1,
        )
        self.assertEqual(
            biological,
            [],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
