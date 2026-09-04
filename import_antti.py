from pathlib import Path
from character_creation import create_ai_character

HERE=Path(__file__).resolve().parent
PROFILE_PATH=HERE/"antti_prompt.txt"

def import_antti(*,preferred_model=None,fallback_models=None,discord_bot_user_id=None):
    if not PROFILE_PATH.is_file():
        raise FileNotFoundError("Put antti_prompt.txt beside this script before running it.")
    return create_ai_character(
        "Antti Rautio",
        profile_text=PROFILE_PATH.read_text(encoding="utf-8"),
        discord_bot_user_id=discord_bot_user_id,
        preferred_model=preferred_model,
        fallback_models=fallback_models,
        ai_participation_mode="deferred",
        description="27-year-old local farmhand in rural 19th-century Southern Ostrobothnia, Finland."
    )

if __name__=="__main__":
    c=import_antti()
    print(f"Antti imported as character {c.character_id}. AI participation remains DEFERRED until model, Discord identity, location, and campaign are configured.")
