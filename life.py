from datetime import date, datetime

from campaign_clock import get_campaign_datetime
from database import get_connection


VALID_OWNER_TYPES = {
    "character",
    "player_persona",
}

DATE_FORMAT = "%Y-%m-%d"


def _validate_owner(owner_type, owner_id):
    owner_type = str(owner_type)

    if owner_type not in VALID_OWNER_TYPES:
        raise ValueError(
            f"Invalid owner type: {owner_type}"
        )

    conn = get_connection()

    table = (
        "characters"
        if owner_type == "character"
        else "player_personas"
    )

    row = conn.execute(
        f"""
        SELECT id
        FROM {table}
        WHERE id = ?
          AND active = 1
        """,
        (int(owner_id),),
    ).fetchone()

    conn.close()

    if row is None:
        raise ValueError(
            f"{owner_type} {owner_id} does not exist or is inactive."
        )

    return owner_type, str(owner_id)


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    try:
        return datetime.strptime(
            str(value).strip(),
            DATE_FORMAT,
        ).date()
    except ValueError as exc:
        raise ValueError(
            "Birth date must use YYYY-MM-DD."
        ) from exc


def set_birth_date(
    owner_type,
    owner_id,
    birth_date,
    notes=None,
):
    owner_type, owner_id = _validate_owner(
        owner_type,
        owner_id,
    )

    birth_date = _parse_date(
        birth_date
    )

    if birth_date > get_campaign_datetime().date():
        raise ValueError(
            "Birth date cannot be after the current campaign date."
        )

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO entity_life_profiles (
            owner_type,
            owner_id,
            birth_date,
            notes
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(owner_type, owner_id)
        DO UPDATE SET
            birth_date = excluded.birth_date,
            notes = excluded.notes,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            owner_type,
            owner_id,
            birth_date.isoformat(),
            notes,
        ),
    )

    conn.commit()
    conn.close()


def get_life_profile(
    owner_type,
    owner_id,
):
    owner_type, owner_id = _validate_owner(
        owner_type,
        owner_id,
    )

    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM entity_life_profiles
        WHERE owner_type = ?
          AND owner_id = ?
        """,
        (
            owner_type,
            owner_id,
        ),
    ).fetchone()

    conn.close()
    return row


def get_age_years(
    owner_type,
    owner_id,
    at_datetime=None,
):
    profile = get_life_profile(
        owner_type,
        owner_id,
    )

    if (
        profile is None
        or profile["birth_date"] is None
    ):
        return None

    born = _parse_date(
        profile["birth_date"]
    )

    when = (
        get_campaign_datetime()
        if at_datetime is None
        else at_datetime
    )

    if isinstance(when, datetime):
        when = when.date()
    else:
        when = _parse_date(when)

    years = when.year - born.year

    if (
        when.month,
        when.day,
    ) < (
        born.month,
        born.day,
    ):
        years -= 1

    return years


def get_age_days(
    owner_type,
    owner_id,
    at_datetime=None,
):
    profile = get_life_profile(
        owner_type,
        owner_id,
    )

    if (
        profile is None
        or profile["birth_date"] is None
    ):
        return None

    born = _parse_date(
        profile["birth_date"]
    )

    when = (
        get_campaign_datetime()
        if at_datetime is None
        else at_datetime
    )

    if isinstance(when, datetime):
        when = when.date()
    else:
        when = _parse_date(when)

    if when < born:
        raise ValueError(
            "Age cannot be calculated before the birth date."
        )

    return (when - born).days


def get_age_months(
    owner_type,
    owner_id,
    at_datetime=None,
):
    profile = get_life_profile(
        owner_type,
        owner_id,
    )

    if (
        profile is None
        or profile["birth_date"] is None
    ):
        return None

    born = _parse_date(
        profile["birth_date"]
    )

    when = (
        get_campaign_datetime()
        if at_datetime is None
        else at_datetime
    )

    if isinstance(when, datetime):
        when = when.date()
    else:
        when = _parse_date(when)

    if when < born:
        raise ValueError(
            "Age cannot be calculated before the birth date."
        )

    months = (
        (when.year - born.year) * 12
        + when.month
        - born.month
    )

    if when.day < born.day:
        months -= 1

    return months
