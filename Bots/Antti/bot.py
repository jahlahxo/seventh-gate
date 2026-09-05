from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


BOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BOT_DIR.parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from discord_adapter import run_character_bot  # noqa: E402


CHARACTER_ID = 1

load_dotenv(BOT_DIR / ".env")

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing from "
        f"{BOT_DIR / '.env'}"
    )


if __name__ == "__main__":
    run_character_bot(
        token=TOKEN,
        character_id=CHARACTER_ID,
        diagnostic_trigger="antti ping",
        diagnostic_response="Perkele. I’m here.",
    )
