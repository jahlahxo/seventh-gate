import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from character_brain import run_character_brain
from choose_model import (
    get_global_preferred_model,
    set_global_preferred_model,
)
from database import initialize_database


def fake_context(preferred_model=None, fallback_models=None):
    return {
        "runtime": {
            "character_id": 7,
            "preferred_model": preferred_model,
            "fallback_models": fallback_models,
            "may_invoke_ai_brain": True,
        }
    }


def successful_generator(attempted, fail_models=()):
    fail_models = set(fail_models)

    def generator(**kwargs):
        model = kwargs["model"]
        attempted.append(model)

        if model in fail_models:
            raise RuntimeError("model unavailable")

        return json.dumps({
            "speech": "Here.",
            "thought": None,
            "action": None,
        })

    return generator


class GlobalModelPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.set_database_path(
            Path(self.tmp.name) / "test.db"
        )
        initialize_database()

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def _run(
        self,
        *,
        context,
        live_models,
        global_model,
        fail_models=(),
    ):
        attempted = []

        with (
            patch(
                "character_brain.build_character_context",
                return_value=context,
            ),
            patch(
                "character_brain.render_character_context",
                return_value="CHARACTER CONTEXT",
            ),
            patch(
                "character_brain.get_character_profile",
                return_value=None,
            ),
        ):
            result = run_character_brain(
                7,
                {"current": "Hello."},
                generator=successful_generator(
                    attempted,
                    fail_models=fail_models,
                ),
                model_provider=lambda: list(live_models),
                default_model_provider=lambda: global_model,
            )

        return attempted, result

    def test_global_model_setting_persists(self):
        set_global_preferred_model(
            "global-model"
        )

        self.assertEqual(
            get_global_preferred_model(),
            "global-model",
        )

    def test_character_without_override_uses_global_model(self):
        attempted, result = self._run(
            context=fake_context(),
            live_models=[
                "top-ranked",
                "global-model",
            ],
            global_model="global-model",
        )

        self.assertEqual(
            attempted,
            ["global-model"],
        )
        self.assertEqual(
            result.model,
            "global-model",
        )

    def test_character_override_wins_over_global_model(self):
        attempted, result = self._run(
            context=fake_context(
                preferred_model="character-model"
            ),
            live_models=[
                "global-model",
                "character-model",
            ],
            global_model="global-model",
        )

        self.assertEqual(
            attempted,
            ["character-model"],
        )
        self.assertEqual(
            result.model,
            "character-model",
        )

    def test_failed_character_override_tries_global_next(self):
        attempted, result = self._run(
            context=fake_context(
                preferred_model="character-model"
            ),
            live_models=[
                "top-ranked",
                "global-model",
                "character-model",
            ],
            global_model="global-model",
            fail_models={"character-model"},
        )

        self.assertEqual(
            attempted,
            [
                "character-model",
                "global-model",
            ],
        )
        self.assertEqual(
            result.model,
            "global-model",
        )

    def test_failed_global_model_uses_top_live_model(self):
        attempted, result = self._run(
            context=fake_context(),
            live_models=[
                "top-ranked",
                "global-model",
                "second-ranked",
            ],
            global_model="global-model",
            fail_models={"global-model"},
        )

        self.assertEqual(
            attempted,
            [
                "global-model",
                "top-ranked",
            ],
        )
        self.assertEqual(
            result.model,
            "top-ranked",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
