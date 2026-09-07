from database import get_connection


ATTRIBUTE_NAMES = (
    "Strength",
    "Agility",
    "Endurance",
    "Perception",
)

SKILL_NAMES = (
    "Athletics",
    "Fighting",
    "Marksmanship",
    "Stealth",
    "Observation",
    "Investigation",
    "Survival",
    "Medicine",
    "Craft",
    "Animals",
    "Persuasion",
    "Deception",
    "Intimidation",
    "Insight",
)

ATTRIBUTE_MIN = 0
ATTRIBUTE_MAX = 4
SKILL_MIN = 0
SKILL_MAX = 4

OWNER_TYPES = {
    "character",
    "player_persona",
}


def validate_owner_type(owner_type):
    if owner_type not in OWNER_TYPES:
        raise ValueError(
            f"Invalid owner type: {owner_type}"
        )


def validate_attribute_name(name):
    if name not in ATTRIBUTE_NAMES:
        raise ValueError(
            f"Unknown attribute: {name}"
        )


def validate_attribute_value(value):
    value = int(value)

    if not ATTRIBUTE_MIN <= value <= ATTRIBUTE_MAX:
        raise ValueError(
            f"Attribute must be between "
            f"{ATTRIBUTE_MIN} and {ATTRIBUTE_MAX}."
        )

    return value


def validate_skill_value(value):
    value = int(value)

    if not SKILL_MIN <= value <= SKILL_MAX:
        raise ValueError(
            f"Skill must be between "
            f"{SKILL_MIN} and {SKILL_MAX}."
        )

    return value


def set_attribute(
    owner_type,
    owner_id,
    attribute_name,
    value,
):
    validate_owner_type(owner_type)
    validate_attribute_name(attribute_name)
    value = validate_attribute_value(value)

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO character_stats (
            owner_type,
            owner_id,
            stat_name,
            stat_value
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(owner_type, owner_id, stat_name)
        DO UPDATE SET stat_value = excluded.stat_value
        """,
        (
            owner_type,
            int(owner_id),
            attribute_name,
            value,
        ),
    )
    conn.commit()
    conn.close()


def get_attribute(
    owner_type,
    owner_id,
    attribute_name,
):
    validate_owner_type(owner_type)
    validate_attribute_name(attribute_name)

    conn = get_connection()
    row = conn.execute(
        """
        SELECT stat_value
        FROM character_stats
        WHERE owner_type = ?
          AND owner_id = ?
          AND stat_name = ?
        """,
        (
            owner_type,
            int(owner_id),
            attribute_name,
        ),
    ).fetchone()
    conn.close()

    if row is None:
        return 0

    return row["stat_value"]


def get_attributes(
    owner_type,
    owner_id,
):
    validate_owner_type(owner_type)

    result = {
        name: 0
        for name in ATTRIBUTE_NAMES
    }

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT stat_name, stat_value
        FROM character_stats
        WHERE owner_type = ?
          AND owner_id = ?
        """,
        (
            owner_type,
            int(owner_id),
        ),
    ).fetchall()
    conn.close()

    for row in rows:
        if row["stat_name"] in result:
            result[row["stat_name"]] = row["stat_value"]

    return result


def set_skill(
    owner_type,
    owner_id,
    skill_name,
    value,
    notes=None,
):
    validate_owner_type(owner_type)

    skill_name = skill_name.strip()

    if not skill_name:
        raise ValueError(
            "Skill name cannot be empty."
        )

    value = validate_skill_value(value)

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO character_skills (
            owner_type,
            owner_id,
            skill_name,
            skill_value,
            notes
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(owner_type, owner_id, skill_name)
        DO UPDATE SET
            skill_value = excluded.skill_value,
            notes = excluded.notes
        """,
        (
            owner_type,
            int(owner_id),
            skill_name,
            value,
            notes,
        ),
    )
    conn.commit()
    conn.close()


def get_skill(
    owner_type,
    owner_id,
    skill_name,
):
    validate_owner_type(owner_type)

    conn = get_connection()
    row = conn.execute(
        """
        SELECT skill_value
        FROM character_skills
        WHERE owner_type = ?
          AND owner_id = ?
          AND skill_name = ?
        """,
        (
            owner_type,
            int(owner_id),
            skill_name,
        ),
    ).fetchone()
    conn.close()

    if row is None:
        return 0

    return row["skill_value"]


def get_skills(
    owner_type,
    owner_id,
):
    validate_owner_type(owner_type)

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            skill_name,
            skill_value,
            notes
        FROM character_skills
        WHERE owner_type = ?
          AND owner_id = ?
        ORDER BY skill_name
        """,
        (
            owner_type,
            int(owner_id),
        ),
    ).fetchall()
    conn.close()

    return {
        row["skill_name"]: {
            "value": row["skill_value"],
            "notes": row["notes"],
        }
        for row in rows
    }


def add_trait(
    owner_type,
    owner_id,
    trait_name,
    description=None,
    mechanical_effect=None,
):
    validate_owner_type(owner_type)

    trait_name = trait_name.strip()

    if not trait_name:
        raise ValueError(
            "Trait name cannot be empty."
        )

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO character_traits (
            owner_type,
            owner_id,
            trait_name,
            description,
            mechanical_effect
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(owner_type, owner_id, trait_name)
        DO UPDATE SET
            description = excluded.description,
            mechanical_effect = excluded.mechanical_effect
        """,
        (
            owner_type,
            int(owner_id),
            trait_name,
            description,
            mechanical_effect,
        ),
    )
    conn.commit()
    conn.close()


def remove_trait(
    owner_type,
    owner_id,
    trait_name,
):
    validate_owner_type(owner_type)

    conn = get_connection()
    conn.execute(
        """
        DELETE FROM character_traits
        WHERE owner_type = ?
          AND owner_id = ?
          AND trait_name = ?
        """,
        (
            owner_type,
            int(owner_id),
            trait_name,
        ),
    )
    conn.commit()
    conn.close()


def get_traits(
    owner_type,
    owner_id,
):
    validate_owner_type(owner_type)

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT
            trait_name,
            description,
            mechanical_effect
        FROM character_traits
        WHERE owner_type = ?
          AND owner_id = ?
        ORDER BY trait_name
        """,
        (
            owner_type,
            int(owner_id),
        ),
    ).fetchall()
    conn.close()

    return [
        {
            "name": row["trait_name"],
            "description": row["description"],
            "mechanical_effect":
                row["mechanical_effect"],
        }
        for row in rows
    ]


def get_character_sheet(
    owner_type,
    owner_id,
):
    return {
        "owner_type": owner_type,
        "owner_id": int(owner_id),
        "attributes": get_attributes(
            owner_type,
            owner_id,
        ),
        "skills": get_skills(
            owner_type,
            owner_id,
        ),
        "traits": get_traits(
            owner_type,
            owner_id,
        ),
    }


def create_default_attributes(
    owner_type,
    owner_id,
):
    """
    Optional helper for authored characters.

    Human registration deliberately does NOT call this.
    """
    validate_owner_type(owner_type)

    for attribute_name in ATTRIBUTE_NAMES:
        set_attribute(
            owner_type,
            owner_id,
            attribute_name,
            2,
        )


def validate_character_sheet(
    attributes,
    skills=None,
):
    if skills is None:
        skills = {}

    errors = []

    for attribute_name in ATTRIBUTE_NAMES:
        if attribute_name not in attributes:
            errors.append(
                f"Missing attribute: {attribute_name}"
            )
            continue

        try:
            validate_attribute_value(
                attributes[attribute_name]
            )
        except ValueError as exc:
            errors.append(str(exc))

    for skill_name, value in skills.items():
        try:
            validate_skill_value(value)
        except ValueError:
            errors.append(
                f"{skill_name}: skill must be between "
                f"{SKILL_MIN} and {SKILL_MAX}."
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
    }
