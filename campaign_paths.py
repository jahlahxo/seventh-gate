from __future__ import annotations

from pathlib import Path

from database import get_db_path


ENGINE_ROOT = Path(__file__).resolve().parent


def get_campaign_directory():
    """
    Return the folder belonging to the currently active campaign database.

    Seventh Gate uses one database per campaign/world. Campaign-specific files
    live beside that database, while the Python engine remains shared.

    Example:

        campaigns/finland_1878/
            seventh_gate.db
            world/
                grounding.json
                social.json
    """
    return get_db_path().resolve().parent


def resolve_campaign_resource(
    relative_path,
    *,
    campaign_dir=None,
    must_exist=False,
):
    """
    Resolve a file inside one campaign folder without permitting path escape.

    `campaign_dir` is mainly useful for tests and authoring tools. Production
    normally derives the campaign folder from the active database path.
    """
    if campaign_dir is None:
        base = get_campaign_directory()
    else:
        base = Path(
            campaign_dir
        ).expanduser().resolve()

    relative = Path(
        str(relative_path)
    )

    if relative.is_absolute():
        raise ValueError(
            "Campaign resource paths must be relative."
        )

    candidate = (
        base
        / relative
    ).resolve()

    try:
        candidate.relative_to(
            base
        )
    except ValueError as exc:
        raise ValueError(
            "Campaign resource path cannot escape the campaign directory."
        ) from exc

    if (
        must_exist
        and not candidate.is_file()
    ):
        raise FileNotFoundError(
            f"Campaign resource not found: {candidate}"
        )

    return candidate
