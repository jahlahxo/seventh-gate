import tempfile
import unittest
from pathlib import Path

import database
from characters import (
    ATTRIBUTE_NAMES,
    SKILL_NAMES,
    get_attributes,
    get_skills,
)
from player_registration import (
    ATTRIBUTE_POINT_BUDGET,
    SKILL_POINT_BUDGET,
    RegistrationError,
    activate_player_registration,
    cancel_player_registration,
    create_pending_player_registration,
    get_active_player_persona_for_discord,
    get_player_registration_details,
    parse_registration_message,
    register_player_immediately,
    render_registration_template,
)


def valid_registration_text(
    *,
    character_name="Aino",
):
    attribute_values = {
        "Strength": 2,
        "Agility": 2,
        "Endurance": 2,
        "Perception": 2,
    }

    skill_values = {
        "Athletics": 2,
        "Fighting": 1,
        "Marksmanship": 0,
        "Stealth": 1,
        "Observation": 2,
        "Investigation": 1,
        "Survival": 1,
        "Medicine": 0,
        "Craft": 1,
        "Animals": 1,
        "Persuasion": 0,
        "Deception": 0,
        "Intimidation": 0,
        "Insight": 0,
    }

    lines = [
        f"CHARACTER NAME: {character_name}",
        "AGE: 24",
        "GENDER: Woman",
        "ORIGIN: Vaasa",
        "OCCUPATION: Seamstress",
        "",
        "APPEARANCE:",
        "Dark hair braided at the nape.",
        "A practical wool dress and worn boots.",
        "",
        "BRIEF BACKGROUND:",
        "Raised near Vaasa and learned sewing from family.",
        "",
        "ATTRIBUTES — 8 POINTS",
    ]

    for name in ATTRIBUTE_NAMES:
        lines.append(
            f"{name}: "
            f"{attribute_values[name]}"
        )

    lines.append(
        "SKILLS — 10 POINTS"
    )

    for name in SKILL_NAMES:
        lines.append(
            f"{name}: "
            f"{skill_values[name]}"
        )

    return "\n".join(lines)


class PlayerRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = (
            tempfile.TemporaryDirectory()
        )

        database.set_database_path(
            Path(self.tmp.name)
            / "registration.db"
        )

        database.initialize_database()

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_template_has_blank_player_allocations_and_no_retired_fields(self):
        template = render_registration_template()

        self.assertIn(
            "Strength:",
            template,
        )
        self.assertIn(
            "Perception:",
            template,
        )
        self.assertNotIn(
            "Strength: 2",
            template,
        )
        self.assertNotIn(
            "Wits:",
            template,
        )
        self.assertNotIn(
            "Presence:",
            template,
        )
        self.assertNotIn(
            "MARITAL",
            template.upper(),
        )

    def test_valid_form_parses_exact_budgets(self):
        draft = parse_registration_message(
            valid_registration_text()
        )

        self.assertEqual(
            sum(
                draft.attributes.values()
            ),
            ATTRIBUTE_POINT_BUDGET,
        )
        self.assertEqual(
            sum(
                draft.skills.values()
            ),
            SKILL_POINT_BUDGET,
        )
        self.assertEqual(
            draft.character_name,
            "Aino",
        )
        self.assertIn(
            "wool dress",
            draft.appearance,
        )

    def test_attribute_over_budget_is_rejected(self):
        text = (
            valid_registration_text()
            .replace(
                "Strength: 2",
                "Strength: 3",
            )
        )

        with self.assertRaises(
            RegistrationError
        ) as ctx:
            parse_registration_message(
                text
            )

        self.assertIn(
            "Attribute budget exceeded",
            str(ctx.exception),
        )

    def test_attribute_under_budget_is_rejected(self):
        text = (
            valid_registration_text()
            .replace(
                "Strength: 2",
                "Strength: 1",
            )
        )

        with self.assertRaises(
            RegistrationError
        ) as ctx:
            parse_registration_message(
                text
            )

        self.assertIn(
            "Attribute points remaining",
            str(ctx.exception),
        )

    def test_attribute_max_is_enforced(self):
        text = (
            valid_registration_text()
            .replace(
                "Strength: 2",
                "Strength: 5",
            )
            .replace(
                "Agility: 2",
                "Agility: 0",
            )
            .replace(
                "Endurance: 2",
                "Endurance: 1",
            )
        )

        with self.assertRaises(
            RegistrationError
        ) as ctx:
            parse_registration_message(
                text
            )

        self.assertIn(
            "Strength must be between 0 and 4",
            str(ctx.exception),
        )

    def test_skill_over_budget_is_rejected(self):
        text = (
            valid_registration_text()
            .replace(
                "Athletics: 2",
                "Athletics: 3",
            )
        )

        with self.assertRaises(
            RegistrationError
        ) as ctx:
            parse_registration_message(
                text
            )

        self.assertIn(
            "Skill budget exceeded",
            str(ctx.exception),
        )

    def test_skill_creation_cap_is_enforced(self):
        text = (
            valid_registration_text()
            .replace(
                "Athletics: 2",
                "Athletics: 4",
            )
            .replace(
                "Observation: 2",
                "Observation: 0",
            )
        )

        with self.assertRaises(
            RegistrationError
        ) as ctx:
            parse_registration_message(
                text
            )

        self.assertIn(
            "Athletics must be between 0 and 3",
            str(ctx.exception),
        )

    def test_missing_stat_is_rejected(self):
        text = (
            valid_registration_text()
            .replace(
                "Perception: 2\n",
                "",
            )
        )

        with self.assertRaises(
            RegistrationError
        ) as ctx:
            parse_registration_message(
                text
            )

        self.assertIn(
            "Perception needs a number",
            str(ctx.exception),
        )

    def test_pending_registration_stores_exact_sheet_then_activates(self):
        draft = parse_registration_message(
            valid_registration_text()
        )

        pending = (
            create_pending_player_registration(
                "111",
                "discord-user",
                draft,
            )
        )

        self.assertIsNone(
            get_active_player_persona_for_discord(
                "111"
            )
        )

        activate_player_registration(
            pending.persona_id
        )

        active = (
            get_active_player_persona_for_discord(
                "111"
            )
        )

        self.assertIsNotNone(active)
        self.assertEqual(
            active["rp_name"],
            "Aino",
        )

        attrs = get_attributes(
            "player_persona",
            pending.persona_id,
        )

        self.assertEqual(
            set(attrs),
            set(ATTRIBUTE_NAMES),
        )
        self.assertEqual(
            sum(attrs.values()),
            ATTRIBUTE_POINT_BUDGET,
        )

        skills = get_skills(
            "player_persona",
            pending.persona_id,
        )

        self.assertEqual(
            set(skills),
            set(SKILL_NAMES),
        )
        self.assertEqual(
            sum(
                item["value"]
                for item
                in skills.values()
            ),
            SKILL_POINT_BUDGET,
        )

        details = (
            get_player_registration_details(
                pending.persona_id
            )
        )

        self.assertEqual(
            details["declared_age"],
            24,
        )
        self.assertEqual(
            details["origin"],
            "Vaasa",
        )

    def test_duplicate_discord_account_is_rejected(self):
        first = parse_registration_message(
            valid_registration_text(
                character_name="Aino",
            )
        )

        register_player_immediately(
            "111",
            "first",
            first,
        )

        second = parse_registration_message(
            valid_registration_text(
                character_name="Liina",
            )
        )

        with self.assertRaises(
            RegistrationError
        ):
            register_player_immediately(
                "111",
                "same-user",
                second,
            )

    def test_duplicate_character_name_is_rejected_case_insensitively(self):
        first = parse_registration_message(
            valid_registration_text(
                character_name="Aino",
            )
        )

        register_player_immediately(
            "111",
            "first",
            first,
        )

        second = parse_registration_message(
            valid_registration_text(
                character_name="aino",
            )
        )

        with self.assertRaises(
            RegistrationError
        ):
            register_player_immediately(
                "222",
                "second",
                second,
            )

    def test_cancel_pending_removes_unfinished_registration(self):
        draft = parse_registration_message(
            valid_registration_text()
        )

        pending = (
            create_pending_player_registration(
                "111",
                "discord-user",
                draft,
            )
        )

        self.assertTrue(
            cancel_player_registration(
                pending.persona_id
            )
        )

        conn = database.get_connection()

        row = conn.execute(
            """
            SELECT id
            FROM player_personas
            WHERE id = ?
            """,
            (
                pending.persona_id,
            ),
        ).fetchone()

        stat_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM character_stats
            WHERE owner_type = 'player_persona'
              AND owner_id = ?
            """,
            (
                pending.persona_id,
            ),
        ).fetchone()[
            "count"
        ]

        conn.close()

        self.assertIsNone(row)
        self.assertEqual(
            stat_count,
            0,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
