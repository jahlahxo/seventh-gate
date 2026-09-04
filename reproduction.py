import random
from datetime import timedelta

from campaign_clock import get_campaign_datetime
from database import get_connection
from life import get_age_years


VALID_OWNER_TYPES = {
    "character",
    "player_persona",
}

VALID_FERTILITY_STATUS = {
    "normal",
    "reduced",
    "very_low",
    "infertile",
    "unknown",
}

VALID_PREGNANCY_STATUS = {
    "ongoing",
    "ended",
}

DEFAULT_GESTATION_DAYS = 280


def _validate_owner(owner_type, owner_id):
    owner_type = str(owner_type)

    if owner_type not in VALID_OWNER_TYPES:
        raise ValueError(
            f"Invalid owner type: {owner_type}"
        )

    table = (
        "characters"
        if owner_type == "character"
        else "player_personas"
    )

    conn = get_connection()

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


def set_reproductive_profile(
    owner_type,
    owner_id,
    *,
    can_conceive=False,
    can_impregnate=False,
    fertility_status="normal",
    fertility_modifier=1.0,
    cycle_length_days=None,
    cycle_day=None,
    notes=None,
):
    owner_type, owner_id = _validate_owner(
        owner_type,
        owner_id,
    )

    fertility_status = str(
        fertility_status
    ).lower().strip()

    if fertility_status not in VALID_FERTILITY_STATUS:
        raise ValueError(
            "Unknown fertility_status."
        )

    fertility_modifier = float(
        fertility_modifier
    )

    if fertility_modifier < 0:
        raise ValueError(
            "fertility_modifier cannot be negative."
        )

    if cycle_length_days is not None:
        cycle_length_days = int(
            cycle_length_days
        )

        if cycle_length_days < 1:
            raise ValueError(
                "cycle_length_days must be positive."
            )

    if cycle_day is not None:
        cycle_day = int(
            cycle_day
        )

        if cycle_day < 1:
            raise ValueError(
                "cycle_day must be positive."
            )

        if (
            cycle_length_days is not None
            and cycle_day > cycle_length_days
        ):
            raise ValueError(
                "cycle_day cannot exceed cycle_length_days."
            )

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO reproductive_profiles (
            owner_type,
            owner_id,
            can_conceive,
            can_impregnate,
            fertility_status,
            fertility_modifier,
            cycle_length_days,
            cycle_day,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(owner_type, owner_id)
        DO UPDATE SET
            can_conceive = excluded.can_conceive,
            can_impregnate = excluded.can_impregnate,
            fertility_status = excluded.fertility_status,
            fertility_modifier = excluded.fertility_modifier,
            cycle_length_days = excluded.cycle_length_days,
            cycle_day = excluded.cycle_day,
            notes = excluded.notes,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            owner_type,
            owner_id,
            int(bool(can_conceive)),
            int(bool(can_impregnate)),
            fertility_status,
            fertility_modifier,
            cycle_length_days,
            cycle_day,
            notes,
        ),
    )

    conn.commit()
    conn.close()

    return get_reproductive_profile(
        owner_type,
        owner_id,
    )


def get_reproductive_profile(
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
        FROM reproductive_profiles
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


def age_fertility_factor(age):
    """
    Story-oriented default age factor for biological conception.

    This is deliberately a broad simulation curve rather than
    a medical calculator. It supports the author's chosen
    reproductive age window of 11 through 55 while keeping the
    extremes very unlikely by default.

    Pregnancy state itself is NOT restricted by this function.
    """
    if age is None:
        return 1.0

    age = int(age)

    if age < 11 or age > 55:
        return 0.0

    if age <= 12:
        return 0.05
    if age <= 14:
        return 0.20
    if age <= 17:
        return 0.60
    if age <= 24:
        return 1.00
    if age <= 29:
        return 0.95
    if age <= 34:
        return 0.80
    if age <= 39:
        return 0.55
    if age <= 44:
        return 0.25
    if age <= 49:
        return 0.08

    return 0.01


def fertility_status_factor(status):
    status = str(
        status
    ).lower().strip()

    return {
        "normal": 1.0,
        "reduced": 0.5,
        "very_low": 0.15,
        "infertile": 0.0,
        "unknown": 1.0,
    }[status]


def get_ongoing_pregnancy(
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
        FROM pregnancies
        WHERE gestational_parent_type = ?
          AND gestational_parent_id = ?
          AND status = 'ongoing'
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            owner_type,
            owner_id,
        ),
    ).fetchone()

    conn.close()
    return row


def create_pregnancy(
    gestational_parent_type,
    gestational_parent_id,
    *,
    other_parent_type=None,
    other_parent_id=None,
    conceived_at=None,
    gestational_age_days=None,
    gestation_days=DEFAULT_GESTATION_DAYS,
    origin_type="unknown",
    origin_source_type=None,
    origin_source_id=None,
    conception_check_id=None,
    certainty="known",
    origin_description=None,
    notes=None,
    allow_existing=False,
):
    """
    Create objective pregnancy state independently of how it
    originated.

    This supports biological, assisted, magical, supernatural,
    imported, unknown, or any setting-defined origin.
    """
    gestational_parent_type, gestational_parent_id = _validate_owner(
        gestational_parent_type,
        gestational_parent_id,
    )

    if other_parent_type is not None:
        other_parent_type, other_parent_id = _validate_owner(
            other_parent_type,
            other_parent_id,
        )

    existing = get_ongoing_pregnancy(
        gestational_parent_type,
        gestational_parent_id,
    )

    if existing is not None and not allow_existing:
        raise ValueError(
            "This character already has an ongoing pregnancy."
        )

    now = get_campaign_datetime()

    if conceived_at is not None and gestational_age_days is not None:
        raise ValueError(
            "Specify conceived_at or gestational_age_days, not both."
        )

    if gestational_age_days is not None:
        gestational_age_days = int(
            gestational_age_days
        )

        if gestational_age_days < 0:
            raise ValueError(
                "gestational_age_days cannot be negative."
            )

        conceived = (
            now
            - timedelta(
                days=gestational_age_days
            )
        )
    elif conceived_at is None:
        conceived = now
    else:
        if hasattr(
            conceived_at,
            "strftime",
        ):
            conceived = conceived_at
        else:
            from datetime import datetime
            conceived = datetime.strptime(
                str(conceived_at),
                "%Y-%m-%d %H:%M:%S",
            )

    due = (
        conceived
        + timedelta(
            days=int(gestation_days)
        )
    )

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO pregnancies (
            gestational_parent_type,
            gestational_parent_id,
            other_parent_type,
            other_parent_id,
            conceived_at,
            estimated_due_at,
            status,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, 'ongoing', ?)
        """,
        (
            gestational_parent_type,
            gestational_parent_id,
            other_parent_type,
            other_parent_id,
            conceived.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            due.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            notes,
        ),
    )

    pregnancy_id = cursor.lastrowid

    conn.execute(
        """
        INSERT INTO pregnancy_origins (
            pregnancy_id,
            origin_type,
            origin_source_type,
            origin_source_id,
            conception_check_id,
            certainty,
            description
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pregnancy_id,
            str(origin_type),
            origin_source_type,
            None if origin_source_id is None else str(origin_source_id),
            conception_check_id,
            str(certainty),
            origin_description,
        ),
    )

    conn.commit()
    conn.close()

    return get_pregnancy(
        pregnancy_id
    )


def get_pregnancy(pregnancy_id):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            pregnancies.*,
            pregnancy_origins.origin_type,
            pregnancy_origins.origin_source_type,
            pregnancy_origins.origin_source_id,
            pregnancy_origins.conception_check_id,
            pregnancy_origins.certainty,
            pregnancy_origins.description AS origin_description
        FROM pregnancies
        LEFT JOIN pregnancy_origins
          ON pregnancy_origins.pregnancy_id = pregnancies.id
        WHERE pregnancies.id = ?
        """,
        (int(pregnancy_id),),
    ).fetchone()

    conn.close()

    if row is None:
        raise ValueError(
            "Pregnancy does not exist."
        )

    return row


def gestational_age_days(pregnancy_id):
    pregnancy = get_pregnancy(
        pregnancy_id
    )

    from datetime import datetime

    conceived = datetime.strptime(
        pregnancy["conceived_at"],
        "%Y-%m-%d %H:%M:%S",
    )

    delta = (
        get_campaign_datetime()
        - conceived
    )

    return max(
        0,
        delta.days,
    )


def resolve_conception(
    gestational_parent_type,
    gestational_parent_id,
    *,
    base_chance,
    source_type,
    source_id=None,
    other_parent_type=None,
    other_parent_id=None,
    apply_age_factor=True,
    apply_fertility_factor=True,
    roll=None,
    create_pregnancy_on_success=True,
    origin_type="biological",
    notes=None,
):
    """
    General conception check.

    It is not tied to sexual content or intimate_events.
    source_type/source_id can refer to any story mechanism.
    """
    gestational_parent_type, gestational_parent_id = _validate_owner(
        gestational_parent_type,
        gestational_parent_id,
    )

    if other_parent_type is not None:
        other_parent_type, other_parent_id = _validate_owner(
            other_parent_type,
            other_parent_id,
        )

    base_chance = float(
        base_chance
    )

    if not 0.0 <= base_chance <= 1.0:
        raise ValueError(
            "base_chance must be between 0 and 1."
        )

    profile = get_reproductive_profile(
        gestational_parent_type,
        gestational_parent_id,
    )

    if profile is None:
        raise ValueError(
            "Gestational parent has no reproductive profile."
        )

    if not profile["can_conceive"]:
        final_chance = 0.0
        age_factor = 0.0 if apply_age_factor else 1.0
        fertility_factor = 0.0
    else:
        age = get_age_years(
            gestational_parent_type,
            gestational_parent_id,
        )

        age_factor = (
            age_fertility_factor(age)
            if apply_age_factor
            else 1.0
        )

        fertility_factor = 1.0

        if apply_fertility_factor:
            fertility_factor = (
                fertility_status_factor(
                    profile["fertility_status"]
                )
                * float(
                    profile["fertility_modifier"]
                )
            )

        final_chance = (
            base_chance
            * age_factor
            * fertility_factor
        )

        final_chance = max(
            0.0,
            min(
                1.0,
                final_chance,
            ),
        )

    if roll is None:
        roll = random.random()
    else:
        roll = float(
            roll
        )

        if not 0.0 <= roll <= 1.0:
            raise ValueError(
                "roll must be between 0 and 1."
            )

    conceived = (
        final_chance > 0
        and roll < final_chance
    )

    now = get_campaign_datetime()

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO conception_checks (
            gestational_parent_type,
            gestational_parent_id,
            other_parent_type,
            other_parent_id,
            source_type,
            source_id,
            base_chance,
            age_factor,
            fertility_factor,
            final_chance,
            roll,
            conceived,
            campaign_datetime,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gestational_parent_type,
            gestational_parent_id,
            other_parent_type,
            other_parent_id,
            str(source_type),
            None if source_id is None else str(source_id),
            base_chance,
            age_factor,
            fertility_factor,
            final_chance,
            roll,
            int(conceived),
            now.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            notes,
        ),
    )

    check_id = cursor.lastrowid

    conn.commit()
    conn.close()

    pregnancy = None

    if (
        conceived
        and create_pregnancy_on_success
    ):
        pregnancy = create_pregnancy(
            gestational_parent_type,
            gestational_parent_id,
            other_parent_type=other_parent_type,
            other_parent_id=other_parent_id,
            conceived_at=now,
            origin_type=origin_type,
            origin_source_type=source_type,
            origin_source_id=source_id,
            conception_check_id=check_id,
            certainty="known",
            notes=notes,
        )

    return {
        "check_id": check_id,
        "base_chance": base_chance,
        "age_factor": age_factor,
        "fertility_factor": fertility_factor,
        "final_chance": final_chance,
        "roll": roll,
        "conceived": conceived,
        "pregnancy": pregnancy,
    }


def end_pregnancy(
    pregnancy_id,
    *,
    outcome,
    description=None,
    world_event_id=None,
):
    pregnancy = get_pregnancy(
        pregnancy_id
    )

    if pregnancy["status"] != "ongoing":
        raise ValueError(
            "Pregnancy is already ended."
        )

    age_days = gestational_age_days(
        pregnancy_id
    )

    now = get_campaign_datetime()

    conn = get_connection()

    conn.execute(
        """
        UPDATE pregnancies
        SET
            status = 'ended',
            ended_at = ?,
            outcome = ?
        WHERE id = ?
        """,
        (
            now.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            str(outcome),
            int(pregnancy_id),
        ),
    )

    conn.execute(
        """
        INSERT INTO pregnancy_events (
            pregnancy_id,
            world_event_id,
            event_type,
            gestational_age_days,
            description
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(pregnancy_id),
            world_event_id,
            str(outcome),
            age_days,
            description,
        ),
    )

    conn.commit()
    conn.close()

    return get_pregnancy(
        pregnancy_id
    )
