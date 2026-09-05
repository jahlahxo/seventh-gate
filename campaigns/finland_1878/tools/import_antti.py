from __future__ import annotations

import os
import re
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
CAMPAIGN_DIR = HERE.parent
PROJECT_ROOT = CAMPAIGN_DIR.parents[1]
PROFILE_PATH = (
    CAMPAIGN_DIR
    / "Bots"
    / "Antti"
    / "antti_prompt.txt"
)
ANTTI_NAME = "Antti Rautio"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from character_creation import (  # noqa: E402
    CreatedCharacter,
    bind_character_discord_bot,
    configure_character_models,
    create_ai_character,
)
from character_profiles import (  # noqa: E402
    set_character_profile,
)
from database import (  # noqa: E402
    get_connection,
    initialize_database,
)


_CONTENT_REFERENCE_RE = re.compile(
    r"\s*:contentReference\[[^\]]+\]\{[^}]*\}"
)


def _activate_own_campaign_database():
    os.environ[
        "SEVENTH_GATE_DB_PATH"
    ] = str(
        CAMPAIGN_DIR
        / "seventh_gate.db"
    )


def _read_antti_profile() -> str:
    if not PROFILE_PATH.is_file():
        raise FileNotFoundError(
            f"Antti profile not found: {PROFILE_PATH}"
        )

    text = PROFILE_PATH.read_text(
        encoding="utf-8"
    )

    text = _CONTENT_REFERENCE_RE.sub(
        "",
        text,
    ).strip()

    if not text:
        raise ValueError(
            "Antti profile is empty after cleanup."
        )

    return text


def _get_existing_antti():
    conn = get_connection()

    try:
        return conn.execute(
            """
            SELECT
                id,
                name,
                active,
                discord_bot_user_id,
                preferred_model,
                fallback_models
            FROM characters
            WHERE name = ?
            """,
            (ANTTI_NAME,),
        ).fetchone()
    finally:
        conn.close()


def import_antti(
    *,
    preferred_model=None,
    fallback_models=None,
    discord_bot_user_id=None,
):
    """
    Register or refresh Antti in the currently selected database.

    When this file is executed directly, it selects its own Finland campaign
    database first. When imported by tests/tools, normal database overrides
    remain in control.
    """
    initialize_database()

    profile_text = _read_antti_profile()
    existing = _get_existing_antti()

    if existing is None:
        created = create_ai_character(
            ANTTI_NAME,
            profile_text=profile_text,
            discord_bot_user_id=discord_bot_user_id,
            preferred_model=preferred_model,
            fallback_models=fallback_models,
            ai_participation_mode="deferred",
            description=(
                "27-year-old local farmhand in rural "
                "19th-century Southern Ostrobothnia, Finland."
            ),
        )

        set_character_profile(
            created.character_id,
            profile_text,
            source_name=PROFILE_PATH.name,
        )

        return created

    character_id = int(
        existing["id"]
    )

    if not int(
        existing["active"]
    ):
        raise RuntimeError(
            "Antti Rautio already exists but is inactive. "
            "Refusing to silently reactivate or duplicate him."
        )

    set_character_profile(
        character_id,
        profile_text,
        source_name=PROFILE_PATH.name,
    )

    if discord_bot_user_id is not None:
        bind_character_discord_bot(
            character_id,
            discord_bot_user_id,
        )

    if (
        preferred_model is not None
        or fallback_models is not None
    ):
        effective_preferred = (
            existing["preferred_model"]
            if preferred_model is None
            else preferred_model
        )

        effective_fallbacks = (
            existing["fallback_models"]
            if fallback_models is None
            else fallback_models
        )

        configure_character_models(
            character_id,
            preferred_model=effective_preferred,
            fallback_models=effective_fallbacks,
        )

    return CreatedCharacter(
        character_id=character_id,
        name=ANTTI_NAME,
    )


if __name__ == "__main__":
    _activate_own_campaign_database()

    character = import_antti()

    print(
        f"Antti registered as character "
        f"{character.character_id}."
    )
    print(
        "A newly created Antti starts with AI participation "
        "DEFERRED. Rerunning this importer does not duplicate him."
    )
