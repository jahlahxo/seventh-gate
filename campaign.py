from __future__ import annotations

from database import get_connection, get_db_path
from campaign_clock import get_campaign_clock, initialize_campaign_clock


CORE_SETTING_KEYS = {
    "campaign_name",
    "setting_name",
    "discord_guild_id",
    "start_datetime",
    "calendar_name",
}


def set_campaign_setting(key, value):
    key = str(key).strip()
    if not key:
        raise ValueError("Campaign setting key cannot be empty.")
    if value is None:
        raise ValueError("Campaign setting value cannot be None.")

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO campaign_settings (setting_key, setting_value)
        VALUES (?, ?)
        ON CONFLICT(setting_key)
        DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def get_campaign_setting(key, default=None):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT setting_value
        FROM campaign_settings
        WHERE setting_key = ?
        """,
        (str(key),),
    ).fetchone()
    conn.close()
    return default if row is None else row["setting_value"]


def get_campaign_settings():
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT setting_key, setting_value
        FROM campaign_settings
        ORDER BY setting_key
        """
    ).fetchall()
    conn.close()
    return {row["setting_key"]: row["setting_value"] for row in rows}


def configure_campaign(
    *,
    campaign_name,
    setting_name,
    start_datetime,
    calendar_name="gregorian",
    discord_guild_id=None,
):
    """
    Configure the ONE campaign represented by the active database.

    Seventh Gate intentionally uses one database per campaign/world.
    Different Discord RP servers should use separate database files
    and, at this stage, separate running processes/configurations.
    """
    campaign_name = str(campaign_name).strip()
    setting_name = str(setting_name).strip()
    start_datetime = str(start_datetime).strip()
    calendar_name = str(calendar_name).strip()

    if not campaign_name:
        raise ValueError("campaign_name cannot be empty.")
    if not setting_name:
        raise ValueError("setting_name cannot be empty.")
    if not start_datetime:
        raise ValueError("start_datetime cannot be empty.")
    if not calendar_name:
        raise ValueError("calendar_name cannot be empty.")

    set_campaign_setting("campaign_name", campaign_name)
    set_campaign_setting("setting_name", setting_name)
    set_campaign_setting("start_datetime", start_datetime)
    set_campaign_setting("calendar_name", calendar_name)

    if discord_guild_id is not None:
        set_campaign_setting("discord_guild_id", str(discord_guild_id))

    initialize_campaign_clock(
        start_datetime=start_datetime,
        calendar_name=calendar_name,
    )
    return get_campaign_identity()


def get_campaign_identity():
    settings = get_campaign_settings()
    try:
        clock = get_campaign_clock()
    except RuntimeError:
        clock = None

    return {
        "campaign_name": settings.get("campaign_name"),
        "setting_name": settings.get("setting_name"),
        "discord_guild_id": settings.get("discord_guild_id"),
        "configured_start_datetime": settings.get("start_datetime"),
        "calendar_name": (
            clock["calendar_name"] if clock is not None
            else settings.get("calendar_name")
        ),
        "current_datetime": (
            clock["current_datetime"] if clock is not None else None
        ),
        "database_path": str(get_db_path()),
    }


def assert_discord_guild_matches(discord_guild_id):
    """Guard against pointing one Discord server at another campaign DB."""
    configured = get_campaign_setting("discord_guild_id")
    if configured is None:
        return True

    if str(discord_guild_id) != configured:
        raise RuntimeError(
            "Discord guild does not match the campaign database binding."
        )
    return True
