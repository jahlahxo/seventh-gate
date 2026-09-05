from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path


HERE = Path(__file__).resolve().parent
CAMPAIGN_DIR = HERE.parent
PROJECT_ROOT = CAMPAIGN_DIR.parents[1]

SOURCE_DB = PROJECT_ROOT / "seventh_gate.db"
TARGET_DB = CAMPAIGN_DIR / "seventh_gate.db"
BACKUP_DB = PROJECT_ROOT / "seventh_gate.pre_campaign_backup.db"

SOURCE_BOT_DIR = PROJECT_ROOT / "Bots" / "Antti"
TARGET_BOT_DIR = CAMPAIGN_DIR / "Bots" / "Antti"

MOVE_FILES = {
    PROJECT_ROOT / "import_antti.py":
        CAMPAIGN_DIR / "tools" / "import_antti.py",
    PROJECT_ROOT / "test_import_antti.py":
        CAMPAIGN_DIR / "tests" / "test_import_antti.py",
    PROJECT_ROOT / "test_world_grounding.py":
        CAMPAIGN_DIR / "tests" / "test_world_grounding.py",
    PROJECT_ROOT / "test_social_grounding.py":
        CAMPAIGN_DIR / "tests" / "test_social_grounding.py",
}


def _integrity_check(path):
    conn = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
    )

    try:
        row = conn.execute(
            "PRAGMA integrity_check"
        ).fetchone()
    finally:
        conn.close()

    return (
        row is not None
        and str(row[0]).strip().lower()
        == "ok"
    )


def _table_counts(path):
    conn = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
    )

    try:
        tables = [
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]

        return {
            table: conn.execute(
                f'SELECT COUNT(*) FROM "{table}"'
            ).fetchone()[0]
            for table in tables
        }
    finally:
        conn.close()


def _critical_state(path):
    conn = sqlite3.connect(
        f"file:{path}?mode=ro",
        uri=True,
    )
    conn.row_factory = sqlite3.Row

    try:
        character = conn.execute(
            """
            SELECT
                id,
                name,
                discord_bot_user_id,
                preferred_model,
                fallback_models,
                active
            FROM characters
            WHERE id = 1
            """
        ).fetchone()

        model = conn.execute(
            """
            SELECT setting_value
            FROM campaign_settings
            WHERE setting_key =
                'default_character_model'
            """
        ).fetchone()

        lifecycle = conn.execute(
            """
            SELECT
                ai_participation_mode
            FROM character_lifecycle_profiles
            WHERE character_id = 1
            """
        ).fetchone()
    finally:
        conn.close()

    return {
        "character": (
            None
            if character is None
            else tuple(character)
        ),
        "global_model": (
            None
            if model is None
            else model["setting_value"]
        ),
        "participation": (
            None
            if lifecycle is None
            else lifecycle[
                "ai_participation_mode"
            ]
        ),
    }


def _copy_database():
    if TARGET_DB.exists():
        if not _integrity_check(
            TARGET_DB
        ):
            raise RuntimeError(
                "Campaign database already exists but failed "
                "SQLite integrity_check."
            )

        print(
            "Campaign database already exists and passed "
            "integrity_check."
        )
        return

    if not SOURCE_DB.is_file():
        raise FileNotFoundError(
            f"Legacy database not found: {SOURCE_DB}"
        )

    if not _integrity_check(
        SOURCE_DB
    ):
        raise RuntimeError(
            "Legacy database failed SQLite integrity_check. "
            "Nothing was moved."
        )

    CAMPAIGN_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = (
        CAMPAIGN_DIR
        / "seventh_gate.migrating.db"
    )

    if temporary.exists():
        temporary.unlink()

    source = sqlite3.connect(
        str(SOURCE_DB)
    )
    destination = sqlite3.connect(
        str(temporary)
    )

    try:
        source.backup(
            destination
        )
    finally:
        destination.close()
        source.close()

    if not _integrity_check(
        temporary
    ):
        temporary.unlink(
            missing_ok=True
        )
        raise RuntimeError(
            "Copied campaign database failed SQLite "
            "integrity_check. Legacy database was left untouched."
        )

    if _table_counts(
        SOURCE_DB
    ) != _table_counts(
        temporary
    ):
        temporary.unlink(
            missing_ok=True
        )
        raise RuntimeError(
            "Copied campaign database did not preserve table counts. "
            "Legacy database was left untouched."
        )

    if _critical_state(
        SOURCE_DB
    ) != _critical_state(
        temporary
    ):
        temporary.unlink(
            missing_ok=True
        )
        raise RuntimeError(
            "Copied campaign database did not preserve Antti/model "
            "runtime state. Legacy database was left untouched."
        )

    temporary.replace(
        TARGET_DB
    )

    print(
        f"Campaign database created: {TARGET_DB}"
    )


def _archive_legacy_database():
    if not SOURCE_DB.exists():
        if BACKUP_DB.exists():
            print(
                "Legacy database is already archived."
            )
            return

        print(
            "No root legacy database remains to archive."
        )
        return

    if not TARGET_DB.is_file():
        raise RuntimeError(
            "Refusing to archive the legacy database before "
            "the campaign database exists."
        )

    if _table_counts(
        SOURCE_DB
    ) != _table_counts(
        TARGET_DB
    ):
        raise RuntimeError(
            "Campaign database does not match the legacy database. "
            "Refusing to archive the legacy copy."
        )

    if _critical_state(
        SOURCE_DB
    ) != _critical_state(
        TARGET_DB
    ):
        raise RuntimeError(
            "Critical runtime state differs between databases. "
            "Refusing to archive the legacy copy."
        )

    if BACKUP_DB.exists():
        raise RuntimeError(
            f"Backup path already exists: {BACKUP_DB}\n"
            "Refusing to overwrite it."
        )

    SOURCE_DB.replace(
        BACKUP_DB
    )

    print(
        f"Legacy database archived safely: {BACKUP_DB}"
    )


def _move_antti_folder():
    if TARGET_BOT_DIR.exists():
        # The migration package itself does not create this directory
        # on the user's machine. If it exists there already, refuse
        # to merge secret/config files blindly.
        if SOURCE_BOT_DIR.exists():
            raise RuntimeError(
                "Both old and new Antti bot folders exist. "
                "Refusing to merge them automatically."
            )

        print(
            "Antti bot folder is already inside the campaign."
        )
        return

    if not SOURCE_BOT_DIR.is_dir():
        raise FileNotFoundError(
            f"Antti bot folder not found: {SOURCE_BOT_DIR}"
        )

    TARGET_BOT_DIR.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.move(
        str(SOURCE_BOT_DIR),
        str(TARGET_BOT_DIR),
    )

    old_bots = (
        PROJECT_ROOT
        / "Bots"
    )

    try:
        old_bots.rmdir()
    except OSError:
        pass

    print(
        f"Antti bot folder moved: {TARGET_BOT_DIR}"
    )


def _move_campaign_specific_files():
    for source, target in MOVE_FILES.items():
        if target.exists():
            if source.exists():
                raise RuntimeError(
                    "Both old and new copies exist for "
                    f"{source.name}. Refusing to choose between them."
                )

            print(
                f"Already moved: {target}"
            )
            continue

        if not source.exists():
            raise FileNotFoundError(
                f"Campaign-specific file not found: {source}"
            )

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.move(
            str(source),
            str(target),
        )

        print(
            f"Moved: {target}"
        )


def _print_preserved_state():
    state = _critical_state(
        TARGET_DB
    )

    character = state[
        "character"
    ]

    print()
    print(
        "Preserved production state:"
    )

    if character is None:
        print(
            "  Character 1: MISSING"
        )
    else:
        print(
            f"  Character 1: {character[1]}"
        )
        print(
            "  Discord binding: "
            f"{character[2]}"
        )

    print(
        "  Global character model: "
        f"{state['global_model']}"
    )
    print(
        "  AI participation: "
        f"{state['participation']}"
    )


def main():
    print(
        "SEVENTH GATE — FINLAND CAMPAIGN REORGANIZATION"
    )
    print(
        f"Project:  {PROJECT_ROOT}"
    )
    print(
        f"Campaign: {CAMPAIGN_DIR}"
    )
    print()

    required_world_files = [
        CAMPAIGN_DIR
        / "world"
        / "grounding.json",
        CAMPAIGN_DIR
        / "world"
        / "social.json",
    ]

    missing = [
        path
        for path
        in required_world_files
        if not path.is_file()
    ]

    if missing:
        raise FileNotFoundError(
            "Campaign world files are missing:\n"
            + "\n".join(
                f"  - {path}"
                for path in missing
            )
        )

    _copy_database()
    _move_antti_folder()
    _move_campaign_specific_files()
    _archive_legacy_database()
    _print_preserved_state()

    print()
    print(
        "Reorganization complete."
    )
    print(
        "Your .env moved with Antti and was not read, printed, "
        "or rewritten."
    )


if __name__ == "__main__":
    main()
