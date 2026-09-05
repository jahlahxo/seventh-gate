from __future__ import annotations

import json
from datetime import datetime

from campaign_clock import get_campaign_datetime
from campaign_paths import resolve_campaign_resource


PROFILE_RELATIVE_PATH = "world/social.json"


def _clean_text(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def load_social_grounding_profile(
    *,
    campaign_dir=None,
):
    """
    Load the active campaign's data-only social-history profile.

    Social expectations belong to campaign data, not generic engine code.
    If the active campaign has no social profile, return None.
    """
    path = resolve_campaign_resource(
        PROFILE_RELATIVE_PATH,
        campaign_dir=campaign_dir,
    )

    if not path.is_file():
        return None

    data = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(data, dict):
        raise ValueError(
            "Social grounding profile must contain one JSON object."
        )

    required = {
        "profile_id",
        "label",
        "status_structure",
        "norms",
    }

    missing = required - set(data)

    if missing:
        raise ValueError(
            "Social grounding profile is missing required fields: "
            + ", ".join(
                sorted(missing)
            )
        )

    if not isinstance(
        data["status_structure"],
        list,
    ):
        raise ValueError(
            "Social grounding profile 'status_structure' must be a list."
        )

    if not isinstance(
        data["norms"],
        list,
    ):
        raise ValueError(
            "Social grounding profile 'norms' must be a list."
        )

    return data


def _coerce_datetime(value):
    if value is None:
        return get_campaign_datetime()

    if isinstance(value, datetime):
        return value

    text = str(value).strip()

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(
                text,
                fmt,
            )
        except ValueError:
            continue

    raise ValueError(
        "Social grounding datetime must be a datetime or ISO-like "
        "'YYYY-MM-DD[ HH:MM:SS]' value."
    )


def _date_applies(
    current_date,
    item,
):
    valid_from = _clean_text(
        item.get("valid_from")
    )
    valid_to = _clean_text(
        item.get("valid_to")
    )

    if valid_from:
        if current_date < datetime.strptime(
            valid_from,
            "%Y-%m-%d",
        ).date():
            return False

    if valid_to:
        if current_date > datetime.strptime(
            valid_to,
            "%Y-%m-%d",
        ).date():
            return False

    return True


def _normalized_status_structure(
    profile,
    at_datetime,
):
    result = []

    for item in profile[
        "status_structure"
    ]:
        if not isinstance(
            item,
            dict,
        ):
            continue

        if not _date_applies(
            at_datetime.date(),
            item,
        ):
            continue

        name = _clean_text(
            item.get("name")
        )
        description = _clean_text(
            item.get("description")
        )

        if (
            name is None
            or description is None
        ):
            continue

        result.append({
            "status_id": _clean_text(
                item.get("id")
            ),
            "name": name,
            "description": description,
            "examples": list(
                item.get("examples")
                or []
            ),
            "notes": _clean_text(
                item.get("notes")
            ),
        })

    return result


def _normalized_norms(
    profile,
    at_datetime,
):
    result = []

    for item in profile["norms"]:
        if not isinstance(
            item,
            dict,
        ):
            continue

        if not _date_applies(
            at_datetime.date(),
            item,
        ):
            continue

        expectation = _clean_text(
            item.get("expectation")
        )

        if expectation is None:
            continue

        result.append({
            "norm_id": _clean_text(
                item.get("id")
            ),
            "category": _clean_text(
                item.get("category")
            ),
            "scope": _clean_text(
                item.get("scope")
            ),
            "applies_to": list(
                item.get("applies_to")
                or []
            ),
            "contexts": list(
                item.get("contexts")
                or []
            ),
            "strength": _clean_text(
                item.get("strength")
            ),
            "expectation": expectation,
            "important_nuance": _clean_text(
                item.get(
                    "important_nuance"
                )
            ),
        })

    return result


def build_social_grounding(
    at_datetime=None,
    *,
    campaign_dir=None,
):
    """
    Build trusted social-history grounding for the Director.

    Norms are expectations and pressures, not automatic reactions. They do not
    assign beliefs, morality or feelings and are not automatically character
    knowledge.
    """
    profile = (
        load_social_grounding_profile(
            campaign_dir=campaign_dir,
        )
    )

    if profile is None:
        return None

    at_datetime = _coerce_datetime(
        at_datetime
    )

    return {
        "profile_id": str(
            profile["profile_id"]
        ),
        "label": str(
            profile["label"]
        ),
        "datetime": (
            at_datetime.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ),
        "region": _clean_text(
            profile.get("region")
        ),
        "status_structure": (
            _normalized_status_structure(
                profile,
                at_datetime,
            )
        ),
        "norms": (
            _normalized_norms(
                profile,
                at_datetime,
            )
        ),
        "director_policy": {
            "expectation_not_mind_control": (
                "Treat social rules as expectations, pressures and common "
                "arrangements. Never use them to decide an individual's "
                "beliefs, feelings, morality or voluntary choices."
            ),
            "relative_status_matters": (
                "When supported by scene evidence, consider relative social "
                "standing, age, marital status, household position, occupation "
                "and gendered expectations rather than flattening everyone "
                "into modern social equality."
            ),
            "outsider_does_not_rewrite_world": (
                "A modern time traveller, foreigner or culturally unfamiliar "
                "human player encounters the same local expectations. Their "
                "ignorance may itself become socially relevant, but the world "
                "does not silently accommodate it."
            ),
            "no_stereotype_machine": (
                "Do not assume all men, women, servants, landowners, widows, "
                "young people or labourers think or act alike."
            ),
            "no_tutorialization": (
                "Do not lecture the player about etiquette. Let expectations "
                "appear through space, work, address, invitations, refusals, "
                "gossip, correction, deference, offence or other naturally "
                "motivated behaviour only when supported by the actors."
            ),
            "knowledge_boundary": (
                "This packet is Engine grounding, not automatic character "
                "knowledge. A character may apply only what their own context, "
                "upbringing, memories or current perception support."
            ),
        },
    }


def get_social_grounding_sources(
    *,
    campaign_dir=None,
):
    """
    Return source metadata for authoring/audit tools.

    Source metadata is deliberately kept out of character and Director prompts.
    """
    profile = (
        load_social_grounding_profile(
            campaign_dir=campaign_dir,
        )
    )

    if profile is None:
        return {}

    sources = profile.get(
        "sources"
    )

    if not isinstance(
        sources,
        dict,
    ):
        return {}

    return dict(sources)
