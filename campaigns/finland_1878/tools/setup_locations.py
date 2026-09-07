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

os.environ[
    "SEVENTH_GATE_DB_PATH"
] = str(
    CAMPAIGN_DIR
    / "seventh_gate.db"
)

from database import (  # noqa: E402
    get_connection,
    initialize_database,
)
from world import (  # noqa: E402
    connect_locations,
    create_location,
    get_location_by_name,
    get_participant_location,
    map_channel_to_location,
    move_participant,
)


ANTTI_NAME = "Antti Rautio"

LOCATIONS = {
    "tupa": {
        "name": "Tupa — Main Room",
        "channel_id": "1545393129023086632",
    },
    "guest_room_1": {
        "name": "Guest Room 1",
        "channel_id": "1545402783019175966",
    },
    "guest_room_2": {
        "name": "Guest Room 2",
        "channel_id": "1545402904309927936",
    },
    "yard": {
        "name": "Yard",
        "channel_id": "1545402983179620473",
    },
    "stable": {
        "name": "Stable",
        "channel_id": "1545402949499494463",
    },
}

# Physical topology:
#   Guest Room 1 \
#                  -> Tupa <-> Yard <-> Stable
#   Guest Room 2 /
CONNECTIONS = (
    ("tupa", "guest_room_1", "door"),
    ("tupa", "guest_room_2", "door"),
    ("tupa", "yard", "door"),
    ("yard", "stable", "path"),
)


def _get_or_create_location(name):
    row = get_location_by_name(
        name
    )

    if row is not None:
        return int(
            row["id"]
        )

    return int(
        create_location(
            name
        )
    )


def _get_antti():
    conn = get_connection()

    row = conn.execute(
        """
        SELECT id, name
        FROM characters
        WHERE name = ?
          AND active = 1
        LIMIT 1
        """,
        (
            ANTTI_NAME,
        ),
    ).fetchone()

    conn.close()

    if row is None:
        raise RuntimeError(
            f"Active character {ANTTI_NAME!r} was not found."
        )

    return row


def setup_locations():
    initialize_database()

    ids = {}

    for key, info in (
        LOCATIONS.items()
    ):
        location_id = (
            _get_or_create_location(
                info["name"]
            )
        )

        ids[key] = (
            location_id
        )

        map_channel_to_location(
            location_id,
            info[
                "channel_id"
            ],
            private_location=False,
        )

    for (
        left,
        right,
        connection_type,
    ) in CONNECTIONS:
        connect_locations(
            ids[left],
            ids[right],
            connection_type=
                connection_type,
            bidirectional=True,
        )

    antti = _get_antti()

    current = (
        get_participant_location(
            "character",
            antti["id"],
        )
    )

    if current is None:
        move_participant(
            "character",
            antti["id"],
            ids["tupa"],
            source_type=
                "campaign_setup",
        )
        placement_status = (
            "Antti placed in Tupa — Main Room."
        )
    elif int(
        current[
            "location_id"
        ]
    ) == ids["tupa"]:
        placement_status = (
            "Antti was already in Tupa — Main Room."
        )
    else:
        raise RuntimeError(
            "Antti already has a different physical location. "
            "Refusing to move him silently."
        )

    return (
        ids,
        placement_status,
    )


def main():
    (
        ids,
        placement_status,
    ) = setup_locations()

    print(
        "Finland location setup complete."
    )

    for key, info in (
        LOCATIONS.items()
    ):
        print(
            f"- {info['name']}: "
            f"location ID {ids[key]} -> "
            f"Discord {info['channel_id']}"
        )

    print(
        "Connections:"
    )
    print(
        "- Tupa — Main Room <-> Guest Room 1"
    )
    print(
        "- Tupa — Main Room <-> Guest Room 2"
    )
    print(
        "- Tupa — Main Room <-> Yard"
    )
    print(
        "- Yard <-> Stable"
    )
    print(
        placement_status
    )
    print(
        "Antti participation mode was not changed."
    )


if __name__ == "__main__":
    main()
