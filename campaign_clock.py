from datetime import datetime, timedelta

from database import get_connection


CLOCK_ID = 1
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse(value):
    if isinstance(value, datetime):
        return value.replace(microsecond=0)

    try:
        return datetime.strptime(
            str(value).strip(),
            DATETIME_FORMAT,
        )
    except ValueError as exc:
        raise ValueError(
            "Campaign datetime must use YYYY-MM-DD HH:MM:SS."
        ) from exc


def _format(value):
    return value.strftime(DATETIME_FORMAT)


def initialize_campaign_clock(
    start_datetime=None,
    calendar_name="gregorian",
):
    """
    Initialize fictional time exactly once for the active campaign database.

    The engine deliberately has NO historical default date. A new campaign
    must supply its own starting datetime, normally through campaign.py.
    """
    conn = get_connection()

    existing = conn.execute(
        "SELECT * FROM campaign_clock WHERE id = ?",
        (CLOCK_ID,),
    ).fetchone()

    if existing is not None:
        conn.close()
        return existing

    if start_datetime is None:
        conn.close()
        raise RuntimeError(
            "Campaign clock is not initialized. "
            "Configure the campaign with an explicit start datetime."
        )

    start = _format(_parse(start_datetime))
    calendar_name = str(calendar_name).strip()

    if not calendar_name:
        conn.close()
        raise ValueError("calendar_name cannot be empty.")

    conn.execute(
        """
        INSERT INTO campaign_clock (
            id,
            current_datetime,
            calendar_name
        )
        VALUES (?, ?, ?)
        """,
        (CLOCK_ID, start, calendar_name),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM campaign_clock WHERE id = ?",
        (CLOCK_ID,),
    ).fetchone()
    conn.close()
    return row


def get_campaign_clock():
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM campaign_clock WHERE id = ?",
        (CLOCK_ID,),
    ).fetchone()
    conn.close()

    if row is None:
        raise RuntimeError(
            "Campaign clock is not initialized. "
            "Configure the campaign before using fictional time."
        )

    return row


def get_campaign_datetime():
    return _parse(get_campaign_clock()["current_datetime"])


def set_campaign_datetime(
    new_datetime,
    *,
    reason,
    source_type,
    source_id=None,
    allow_backward=False,
):
    if not str(reason).strip():
        raise ValueError("A reason is required.")
    if not str(source_type).strip():
        raise ValueError("source_type is required.")

    old = get_campaign_datetime()
    new = _parse(new_datetime)
    seconds = int((new - old).total_seconds())

    if seconds < 0 and not allow_backward:
        raise ValueError(
            "Campaign time cannot move backward unless explicitly overridden."
        )

    conn = get_connection()
    conn.execute(
        """
        UPDATE campaign_clock
        SET current_datetime = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (_format(new), CLOCK_ID),
    )
    conn.execute(
        """
        INSERT INTO campaign_clock_events (
            old_datetime, new_datetime, seconds_advanced,
            reason, source_type, source_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            _format(old), _format(new), seconds, str(reason), str(source_type),
            None if source_id is None else str(source_id),
        ),
    )
    conn.commit()
    conn.close()
    return get_campaign_clock()


def advance_campaign_time(
    *,
    days=0,
    hours=0,
    minutes=0,
    seconds=0,
    reason,
    source_type,
    source_id=None,
):
    values = (days, hours, minutes, seconds)
    if any(int(value) != value for value in values):
        raise ValueError("Time advances must use whole numbers.")

    delta = timedelta(
        days=int(days),
        hours=int(hours),
        minutes=int(minutes),
        seconds=int(seconds),
    )
    if delta.total_seconds() <= 0:
        raise ValueError("Campaign time advance must be greater than zero.")

    return set_campaign_datetime(
        get_campaign_datetime() + delta,
        reason=reason,
        source_type=source_type,
        source_id=source_id,
    )


def set_clock_paused(paused):
    get_campaign_clock()
    conn = get_connection()
    conn.execute(
        """
        UPDATE campaign_clock
        SET paused = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (int(bool(paused)), CLOCK_ID),
    )
    conn.commit()
    conn.close()
    return get_campaign_clock()


def set_time_scale(time_scale):
    time_scale = float(time_scale)
    if time_scale <= 0:
        raise ValueError("time_scale must be greater than zero.")

    get_campaign_clock()
    conn = get_connection()
    conn.execute(
        """
        UPDATE campaign_clock
        SET time_scale = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (time_scale, CLOCK_ID),
    )
    conn.commit()
    conn.close()
    return get_campaign_clock()


def get_clock_history(limit=100):
    limit = int(limit)
    if limit < 1:
        raise ValueError("limit must be at least 1.")

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM campaign_clock_events
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return rows
