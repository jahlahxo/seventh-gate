from __future__ import annotations

import sys

from campaign import (
    get_campaign_setting,
    set_campaign_setting,
)
from character_creation import configure_character_models
from database import get_connection
from horde import get_ranked_text_model_names


DEFAULT_CHARACTER_MODEL_SETTING = "default_character_model"


def get_global_preferred_model():
    return get_campaign_setting(
        DEFAULT_CHARACTER_MODEL_SETTING
    )


def set_global_preferred_model(model_name):
    model_name = str(model_name or "").strip()

    if not model_name:
        raise ValueError(
            "Model name cannot be empty."
        )

    set_campaign_setting(
        DEFAULT_CHARACTER_MODEL_SETTING,
        model_name,
    )

    return model_name


def get_character_model_config(character_name):
    """Read an optional character-specific model override."""
    name = str(character_name or "").strip()

    if not name:
        raise ValueError(
            "Character name cannot be empty."
        )

    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT
                id,
                name,
                preferred_model,
                fallback_models
            FROM characters
            WHERE name = ?
              AND active = 1
            """,
            (name,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise ValueError(
            f"Active character not found: {name}"
        )

    return {
        "character_id": int(row["id"]),
        "name": row["name"],
        "preferred_model": row["preferred_model"],
        "fallback_models": row["fallback_models"],
    }


def set_character_preferred_model(
    character_name,
    model_name,
):
    """Set an explicit exception for one character."""
    model_name = str(model_name or "").strip()

    if not model_name:
        raise ValueError(
            "Model name cannot be empty."
        )

    config = get_character_model_config(
        character_name
    )

    configure_character_models(
        config["character_id"],
        preferred_model=model_name,
        fallback_models=config["fallback_models"],
    )

    return model_name


def resolve_model_selection(
    selection,
    live_models,
):
    selection = str(selection or "").strip()

    if not selection:
        return None

    if selection.lower() in {
        "q",
        "quit",
        "exit",
    }:
        return None

    if selection.isdigit():
        index = int(selection) - 1

        if 0 <= index < len(live_models):
            return live_models[index]

        raise ValueError(
            "That model number is not in the list."
        )

    for model in live_models:
        if model.casefold() == selection.casefold():
            return model

    raise ValueError(
        "That model is not in the current live Horde list."
    )


def _print_live_models(
    live_models,
    current,
):
    print()
    print(
        "Current live models "
        "(SillyTavern-style order):"
    )
    print()

    for index, model in enumerate(
        live_models,
        start=1,
    ):
        marker = (
            "  <-- CURRENT"
            if model == current
            else ""
        )

        print(
            f"{index:>2}. {model}{marker}"
        )

    if current and current not in live_models:
        print()
        print(
            "Current preferred model is "
            "not live right now:"
        )
        print(f"    {current}")


def _prompt_for_model(live_models):
    print()
    print(
        "Enter a model number, or type "
        "the exact model name."
    )
    print(
        "Enter Q to leave it unchanged."
    )
    print()

    while True:
        selection = input("Selection: ")

        try:
            return resolve_model_selection(
                selection,
                live_models,
            )
        except ValueError as exc:
            print(
                f"Invalid selection: {exc}"
            )


def choose_global_model():
    current = get_global_preferred_model()

    print()
    print(
        "SEVENTH GATE - GLOBAL MODEL SELECTOR"
    )
    print(
        "All AI characters use this model by default."
    )
    print(
        "Individual character overrides remain possible."
    )
    print()
    print(
        "Current global preferred model: "
        f"{current or '(automatic only)'}"
    )
    print()
    print(
        "Fetching current Horde models..."
    )

    live_models = get_ranked_text_model_names(
        force=True
    )

    if not live_models:
        raise RuntimeError(
            "Horde returned no active text models."
        )

    _print_live_models(
        live_models,
        current,
    )

    chosen = _prompt_for_model(
        live_models
    )

    if chosen is None:
        print("No change made.")
        return None

    set_global_preferred_model(
        chosen
    )

    print()
    print(
        "Global preferred model updated:"
    )
    print(f"    {chosen}")
    print()
    print(
        "All characters without an explicit override "
        "now prefer this model."
    )
    print(
        "Automatic live-model failover remains enabled."
    )

    return chosen


def choose_character_model(character_name):
    """Optional manual override for one specific character."""
    config = get_character_model_config(
        character_name
    )
    current = config["preferred_model"]

    print()
    print(
        "SEVENTH GATE - CHARACTER MODEL OVERRIDE"
    )
    print(f"Character: {config['name']}")
    print(
        "Current override: "
        f"{current or '(none - using global default)'}"
    )
    print()
    print(
        "Fetching current Horde models..."
    )

    live_models = get_ranked_text_model_names(
        force=True
    )

    if not live_models:
        raise RuntimeError(
            "Horde returned no active text models."
        )

    _print_live_models(
        live_models,
        current,
    )

    chosen = _prompt_for_model(
        live_models
    )

    if chosen is None:
        print("No change made.")
        return None

    set_character_preferred_model(
        config["name"],
        chosen,
    )

    print()
    print(
        "Character override updated:"
    )
    print(f"    {chosen}")
    print()
    print(
        "This character will try its override first, "
        "then the global model, then live automatic failover."
    )

    return chosen


def main():
    try:
        if len(sys.argv) == 1:
            choose_global_model()
            return 0

        if (
            len(sys.argv) >= 3
            and sys.argv[1] == "--character"
        ):
            character_name = " ".join(
                sys.argv[2:]
            ).strip()
            choose_character_model(
                character_name
            )
            return 0

        print(
            'Usage: python choose_model.py'
        )
        print(
            'Optional character override: '
            'python choose_model.py --character "Character Name"'
        )
        return 1

    except Exception as exc:
        print()
        print(
            f"ERROR: {type(exc).__name__}: {exc}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
