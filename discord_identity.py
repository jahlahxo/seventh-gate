from __future__ import annotations

from dataclasses import dataclass

from database import get_connection


@dataclass(frozen=True)
class DiscordBindingResult:
    character_id: int
    character_name: str
    discord_bot_user_id: str
    status: str


def _clean_discord_user_id(value):
    value = str(value or "").strip()

    if not value:
        raise ValueError(
            "discord_bot_user_id cannot be empty."
        )

    return value


def _get_active_character(character_id):
    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT
                id,
                name,
                active,
                discord_bot_user_id
            FROM characters
            WHERE id = ?
            """,
            (int(character_id),),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise ValueError(
            f"Character {character_id} does not exist."
        )

    if not int(row["active"]):
        raise ValueError(
            f"Character {character_id} is inactive."
        )

    return row


def ensure_character_discord_binding(
    character_id,
    discord_bot_user_id,
):
    """
    Safely bind or verify one Discord bot account against one character.

    Rules:
    - if the character has no Discord bot ID yet, bind it once;
    - if the stored ID already matches, verify and continue;
    - if the stored ID differs, refuse to overwrite it.

    The mismatch refusal prevents an accidentally swapped bot token from
    silently taking over another character's identity.
    """
    character_id = int(character_id)
    discord_bot_user_id = _clean_discord_user_id(
        discord_bot_user_id
    )

    row = _get_active_character(character_id)

    existing = str(
        row["discord_bot_user_id"] or ""
    ).strip()

    if existing:
        if existing != discord_bot_user_id:
            raise RuntimeError(
                "Discord identity mismatch for "
                f"{row['name']} (character {character_id}). "
                f"Database expects bot user ID {existing}, "
                f"but the logged-in bot is {discord_bot_user_id}. "
                "Refusing to overwrite the existing binding."
            )

        return DiscordBindingResult(
            character_id=character_id,
            character_name=str(row["name"]),
            discord_bot_user_id=existing,
            status="verified",
        )

    conn = get_connection()

    try:
        cursor = conn.execute(
            """
            UPDATE characters
            SET
                discord_bot_user_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND active = 1
              AND (
                    discord_bot_user_id IS NULL
                    OR TRIM(discord_bot_user_id) = ''
                  )
            """,
            (
                discord_bot_user_id,
                character_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    if cursor.rowcount == 1:
        return DiscordBindingResult(
            character_id=character_id,
            character_name=str(row["name"]),
            discord_bot_user_id=discord_bot_user_id,
            status="bound",
        )

    row = _get_active_character(character_id)
    existing = str(
        row["discord_bot_user_id"] or ""
    ).strip()

    if existing == discord_bot_user_id:
        return DiscordBindingResult(
            character_id=character_id,
            character_name=str(row["name"]),
            discord_bot_user_id=existing,
            status="verified",
        )

    raise RuntimeError(
        "Discord identity changed while binding "
        f"{row['name']} (character {character_id}). "
        "Refusing to overwrite the current binding."
    )
