from __future__ import annotations

import os
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
CAMPAIGN_DIR = HERE.parent
PROJECT_ROOT = CAMPAIGN_DIR.parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from campaign import (  # noqa: E402
    configure_campaign,
    get_campaign_identity,
    get_campaign_setting,
    set_campaign_setting,
)
from campaign_clock import (  # noqa: E402
    get_campaign_clock,
)
from database import (  # noqa: E402
    initialize_database,
)


CAMPAIGN_NAME = "Finland 1878"
SETTING_NAME = (
    "Rural Southern Ostrobothnia, Finland"
)
CAMPAIGN_START = (
    "1878-11-10 18:30:00"
)

CAMPAIGN_SETTINGS = {
    "recent_scene_token_budget":
        "7000",
    "private_thought_token_budget":
        "1200",
    "scene_summary_char_budget":
        "2400",
    "rp_public_style":
        "compact_natural_story",
    "rp_public_soft_length":
        "usually 1-3 short lines; 4 is a normal upper bound",
    "thought_display":
        "discord_italics",
}


def _activate_campaign_database():
    os.environ[
        "SEVENTH_GATE_DB_PATH"
    ] = str(
        CAMPAIGN_DIR
        / "seventh_gate.db"
    )


def _clock_exists():
    try:
        return get_campaign_clock()
    except RuntimeError:
        return None


def configure_finland_campaign():
    """
    Configure the Finland campaign once without silently rewinding it later.
    """
    _activate_campaign_database()
    initialize_database()

    configured_start = (
        get_campaign_setting(
            "start_datetime"
        )
    )
    campaign_name = (
        get_campaign_setting(
            "campaign_name"
        )
    )
    clock = _clock_exists()

    if configured_start is None:
        configure_campaign(
            campaign_name=
                CAMPAIGN_NAME,
            setting_name=
                SETTING_NAME,
            start_datetime=
                CAMPAIGN_START,
            calendar_name=
                "gregorian",
        )
    else:
        if (
            configured_start
            != CAMPAIGN_START
            or (
                campaign_name
                is not None
                and campaign_name
                != CAMPAIGN_NAME
            )
        ):
            raise RuntimeError(
                "This database already contains a different campaign "
                "identity/start. Refusing to overwrite it."
            )

        # Rerunning the tool after play begins must not reset current_datetime.
        if clock is None:
            raise RuntimeError(
                "Campaign identity exists but its campaign clock is missing."
            )

    for (
        key,
        value,
    ) in CAMPAIGN_SETTINGS.items():
        set_campaign_setting(
            key,
            value,
        )

    global_model = (
        get_campaign_setting(
            "default_character_model"
        )
    )

    if (
        get_campaign_setting(
            "director_model"
        )
        is None
        and global_model
    ):
        set_campaign_setting(
            "director_model",
            global_model,
        )

    if (
        get_campaign_setting(
            "summary_model"
        )
        is None
        and global_model
    ):
        set_campaign_setting(
            "summary_model",
            global_model,
        )

    return (
        get_campaign_identity()
    )


def main():
    identity = (
        configure_finland_campaign()
    )

    print(
        "Finland campaign configured."
    )
    print(
        "Database: "
        + identity[
            "database_path"
        ]
    )
    print(
        "Campaign: "
        + str(
            identity[
                "campaign_name"
            ]
        )
    )
    print(
        "Setting: "
        + str(
            identity[
                "setting_name"
            ]
        )
    )
    print(
        "Current campaign time: "
        + str(
            identity[
                "current_datetime"
            ]
        )
    )
    print(
        "Recent perceived-history budget: "
        + get_campaign_setting(
            "recent_scene_token_budget"
        )
        + " estimated tokens per character"
    )
    print(
        "Antti participation mode was not changed."
    )


if __name__ == "__main__":
    main()
