from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import datetime

from campaign_clock import get_campaign_datetime
from campaign_paths import resolve_campaign_resource


PROFILE_RELATIVE_PATH = "world/grounding.json"


def _clean_text(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def load_world_grounding_profile(
    *,
    campaign_dir=None,
):
    """
    Load the active campaign's data-only world grounding profile.

    The generic engine contains no Finland-specific assumptions. A campaign
    owns its own `world/grounding.json` beside its own database.

    If the active campaign has no grounding file, return None.
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
            "World grounding profile must contain one JSON object."
        )

    required = {
        "profile_id",
        "label",
        "facts",
    }

    missing = required - set(data)

    if missing:
        raise ValueError(
            "World grounding profile is missing required fields: "
            + ", ".join(
                sorted(missing)
            )
        )

    if not isinstance(
        data["facts"],
        list,
    ):
        raise ValueError(
            "World grounding profile 'facts' must be a list."
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
        "Grounding datetime must be a datetime or ISO-like "
        "'YYYY-MM-DD[ HH:MM:SS]' value."
    )


def _date_in_range(
    current_date,
    fact,
):
    valid_from = _clean_text(
        fact.get("valid_from")
    )
    valid_to = _clean_text(
        fact.get("valid_to")
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

    months = fact.get("months")

    if months is not None:
        allowed_months = {
            int(month)
            for month in months
        }

        if current_date.month not in allowed_months:
            return False

    return True


def _selected_facts(
    profile,
    at_datetime,
):
    selected = []

    for fact in profile["facts"]:
        if not isinstance(fact, dict):
            continue

        text = _clean_text(
            fact.get("text")
        )

        if text is None:
            continue

        if not _date_in_range(
            at_datetime.date(),
            fact,
        ):
            continue

        selected.append({
            "fact_id": _clean_text(
                fact.get("id")
            ),
            "category": _clean_text(
                fact.get("category")
            ),
            "scope": _clean_text(
                fact.get("scope")
            ),
            "text": text,
        })

    return selected


def _approx_daylight_hours(
    latitude_degrees,
    at_datetime,
):
    """
    Approximate geometric daylight with a standard sunrise/sunset correction.

    This is environmental grounding, not an exact historical clock-time claim.
    """
    latitude = math.radians(
        float(latitude_degrees)
    )

    day_number = (
        at_datetime
        .timetuple()
        .tm_yday
    )

    declination_degrees = (
        -23.44
        * math.cos(
            math.radians(
                360.0
                / 365.0
                * (day_number + 10)
            )
        )
    )

    declination = math.radians(
        declination_degrees
    )

    solar_altitude = math.radians(
        -0.833
    )

    numerator = (
        math.sin(solar_altitude)
        - math.sin(latitude)
        * math.sin(declination)
    )

    denominator = (
        math.cos(latitude)
        * math.cos(declination)
    )

    if denominator == 0:
        return None

    cosine_hour_angle = (
        numerator
        / denominator
    )

    if cosine_hour_angle >= 1:
        return 0.0

    if cosine_hour_angle <= -1:
        return 24.0

    hour_angle = math.acos(
        cosine_hour_angle
    )

    hours = (
        24.0
        * hour_angle
        / math.pi
    )

    return round(
        hours,
        1,
    )


def _weather_for_date(
    profile,
    at_datetime,
):
    weather = profile.get(
        "weather"
    )

    if not isinstance(
        weather,
        dict,
    ):
        return None

    months = weather.get(
        "months"
    )

    if not isinstance(
        months,
        dict,
    ):
        return None

    month_profile = months.get(
        str(at_datetime.month)
    )

    if not isinstance(
        month_profile,
        dict,
    ):
        return None

    states = month_profile.get(
        "states"
    )

    if not isinstance(
        states,
        list,
    ) or not states:
        return None

    usable_states = [
        state
        for state in states
        if (
            isinstance(state, dict)
            and _clean_text(
                state.get("name")
            )
            is not None
            and float(
                state.get(
                    "weight",
                    0,
                )
            ) > 0
        )
    ]

    if not usable_states:
        return None

    seed_text = (
        _clean_text(
            weather.get("seed")
        )
        or str(
            profile["profile_id"]
        )
    )

    date_key = (
        at_datetime
        .date()
        .isoformat()
    )

    digest = hashlib.sha256(
        (
            f"{profile['profile_id']}|"
            f"{date_key}|"
            f"{seed_text}"
        ).encode(
            "utf-8"
        )
    ).digest()

    rng = random.Random(
        int.from_bytes(
            digest[:8],
            "big",
        )
    )

    chosen = rng.choices(
        usable_states,
        weights=[
            float(
                state["weight"]
            )
            for state
            in usable_states
        ],
        k=1,
    )[0]

    temperature = None

    if (
        chosen.get(
            "temperature_c_min"
        )
        is not None
        and chosen.get(
            "temperature_c_max"
        )
        is not None
    ):
        temperature = round(
            rng.uniform(
                float(
                    chosen[
                        "temperature_c_min"
                    ]
                ),
                float(
                    chosen[
                        "temperature_c_max"
                    ]
                ),
            ),
            1,
        )

    winds = chosen.get(
        "winds"
    ) or month_profile.get(
        "winds"
    ) or []

    wind = None

    if winds:
        wind = rng.choice(
            list(winds)
        )

    return {
        "kind": str(
            chosen["name"]
        ),
        "temperature_c": temperature,
        "wind": wind,
        "ground": _clean_text(
            chosen.get("ground")
        ),
        "visibility": _clean_text(
            chosen.get(
                "visibility"
            )
        ),
        "travel_effect": _clean_text(
            chosen.get(
                "travel_effect"
            )
        ),
        "simulation_basis": (
            "Plausible deterministic daily weather derived from the "
            "profile's seasonal climate tendencies. It is world-state "
            "simulation, not a claim that this exact weather was observed "
            "on the historical date."
        ),
    }


def build_world_grounding(
    at_datetime=None,
    *,
    campaign_dir=None,
):
    """
    Build trusted date/place grounding for the Director.

    This packet is Engine background truth. It is NOT automatically character
    knowledge. If a campaign has no world grounding file, return None.
    """
    profile = (
        load_world_grounding_profile(
            campaign_dir=campaign_dir,
        )
    )

    if profile is None:
        return None

    at_datetime = _coerce_datetime(
        at_datetime
    )

    latitude = profile.get(
        "reference_latitude"
    )

    daylight_hours = None

    if latitude is not None:
        daylight_hours = (
            _approx_daylight_hours(
                latitude,
                at_datetime,
            )
        )

    return {
        "profile_id": str(
            profile["profile_id"]
        ),
        "label": str(
            profile["label"]
        ),
        "datetime": (
            at_datetime
            .strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        ),
        "region": _clean_text(
            profile.get("region")
        ),
        "polity": _clean_text(
            profile.get("polity")
        ),
        "reference_latitude": (
            None
            if latitude is None
            else float(latitude)
        ),
        "approx_daylight_hours": (
            daylight_hours
        ),
        "daily_weather": (
            _weather_for_date(
                profile,
                at_datetime,
            )
        ),
        "relevant_facts": (
            _selected_facts(
                profile,
                at_datetime,
            )
        ),
        "director_policy": {
            "world_consistency": (
                "Keep the historical/material world consistent even if a "
                "human player is modern, time-travelled, foreign, ignorant "
                "of local customs, or behaves anachronistically."
            ),
            "no_tutorialization": (
                "Do not turn ordinary life into a history lesson. Let facts "
                "surface through objects, routines, constraints, customs and "
                "natural dialogue when context makes them relevant."
            ),
            "individuality": (
                "Social norms and historical pressures describe the world, "
                "not every individual's beliefs or choices. Characters remain "
                "individual actors."
            ),
            "knowledge_boundary": (
                "This grounding is not automatically known by the current "
                "character. Reveal only perceivable manifestations; character "
                "knowledge remains separately controlled."
            ),
        },
    }


def get_world_grounding_sources(
    *,
    campaign_dir=None,
):
    """
    Return source metadata for authoring/audit tools.

    Source metadata is intentionally not inserted into Director prompts.
    """
    profile = (
        load_world_grounding_profile(
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
