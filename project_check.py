from __future__ import annotations

import importlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent

PRODUCTION_FILES = [
    "database.py",
    "actions.py",
    "characters.py",
    "world.py",
    "memory.py",
    "horde.py",
    "resolver.py",
    "executor.py",
    "entities.py",
    "intimacy.py",
    "campaign_clock.py",
    "campaign.py",
    "life.py",
    "reproduction.py",
    "pregnancy_awareness.py",
    "mortality.py",
    "family.py",
    "development.py",
    "character_context.py",
    "character_profiles.py",
    "character_creation.py",
    "character_brain.py",
    "director.py",
    "rp_loop.py",
    "action_interpreter.py",
    "scene_refresh.py",
    "simulation_cycle.py",
    "import_antti.py",
]

PRODUCTION_MODULES = [
    "database",
    "actions",
    "characters",
    "world",
    "memory",
    "horde",
    "resolver",
    "executor",
    "entities",
    "intimacy",
    "campaign_clock",
    "campaign",
    "life",
    "reproduction",
    "pregnancy_awareness",
    "mortality",
    "family",
    "development",
    "character_context",
    "character_profiles",
    "character_creation",
    "character_brain",
    "director",
    "rp_loop",
    "action_interpreter",
    "scene_refresh",
    "simulation_cycle",
    "import_antti",
]

TEST_FILES = [
    "test_engine.py",
    "test_entities.py",
    "test_executor_objects.py",
    "test_intimacy.py",
    "test_campaign_clock.py",
    "test_campaign.py",
    "test_reproduction.py",
    "test_pregnancy_awareness.py",
    "test_mortality.py",
    "test_family.py",
    "test_development.py",
    "test_character_context.py",
    "test_character_brain.py",
    "test_character_profiles.py",
    "test_character_profile_brain.py",
    "test_director.py",
    "test_rp_loop.py",
    "test_action_interpreter.py",
    "test_simulation_cycle.py",
    "test_scene_refresh.py",
    "test_import_antti.py",
]

LEGACY_WARNINGS = {
    "bot.py": (
        "Legacy test bot filename detected. It should remain renamed "
        "to bot_legacy.py so it is not accidentally run as production."
    ),
    "Resolver.py": (
        "Old capitalized Resolver.py detected. Keep only lowercase "
        "resolver.py as the production module."
    ),
}


def print_heading(title: str) -> None:
    print()
    print("=" * 68)
    print(title)
    print("=" * 68)


def check_files() -> bool:
    print_heading("1. REQUIRED FILE CHECK")

    ok = True

    for name in PRODUCTION_FILES + TEST_FILES:
        path = ROOT / name

        if path.is_file():
            print(f"[OK]      {name}")
        else:
            print(f"[MISSING] {name}")
            ok = False

    actual_names = {
        entry.name
        for entry in ROOT.iterdir()
    }

    for name, warning in LEGACY_WARNINGS.items():
        if name in actual_names:
            print(
                f"[WARNING] {name}: "
                f"{warning}"
            )

    if (ROOT / "bot_legacy.py").is_file():
        print(
            "[OK]      bot_legacy.py is "
            "quarantined as legacy code."
        )

    return ok


def check_imports() -> bool:
    print_heading(
        "2. PRODUCTION IMPORT CHECK"
    )

    ok = True

    for module_name in PRODUCTION_MODULES:
        try:
            importlib.import_module(
                module_name
            )
            print(
                f"[OK]      import "
                f"{module_name}"
            )
        except Exception as exc:
            print(
                f"[FAILED]  import "
                f"{module_name}: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )
            ok = False

    return ok


def run_tests() -> bool:
    print_heading(
        "3. REGRESSION TEST SUITE"
    )

    missing = [
        name
        for name in TEST_FILES
        if not (ROOT / name).is_file()
    ]

    if missing:
        print(
            "Cannot run the complete "
            "suite because these test "
            "files are missing:"
        )

        for name in missing:
            print(
                f"  - {name}"
            )

        return False

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for filename in TEST_FILES:
        module_name = Path(filename).stem

        try:
            module = importlib.import_module(
                module_name
            )
        except Exception as exc:
            print(
                f"[FAILED] importing "
                f"{filename}: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )
            return False

        suite.addTests(
            loader.loadTestsFromModule(
                module
            )
        )

    runner = unittest.TextTestRunner(
        verbosity=1
    )

    result = runner.run(
        suite
    )

    print()
    print(
        f"Tests run: "
        f"{result.testsRun} | "
        f"Failures: "
        f"{len(result.failures)} | "
        f"Errors: "
        f"{len(result.errors)}"
    )

    return result.wasSuccessful()


def main() -> int:
    print(
        "SEVENTH GATE PROJECT "
        "PRE-FLIGHT"
    )
    print(
        f"Folder: {ROOT}"
    )

    files_ok = check_files()

    if not files_ok:
        print_heading(
            "RESULT"
        )
        print(
            "NOT READY: one or more "
            "required project files are "
            "missing. Fix the missing "
            "files before changing "
            "production code."
        )
        return 1

    imports_ok = check_imports()

    if not imports_ok:
        print_heading(
            "RESULT"
        )
        print(
            "NOT READY: at least one "
            "production module failed "
            "to import. Fix that before "
            "moving forward."
        )
        return 1

    tests_ok = run_tests()

    print_heading(
        "RESULT"
    )

    if (
        files_ok
        and imports_ok
        and tests_ok
    ):
        print(
            "READY: required files are "
            "present, all production "
            "modules import, and the "
            "full regression suite "
            "passes."
        )
        return 0

    print(
        "NOT READY: the regression "
        "suite found a problem. Do not "
        "continue building until it is "
        "fixed."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
