import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

import database
import horde
from character_brain import (
    run_character_brain,
)
from choose_model import (
    get_character_model_config,
    resolve_model_selection,
    set_character_preferred_model,
)
from database import (
    get_connection,
    initialize_database,
)


class FakeResponse:
    def __init__(
        self,
        data,
    ):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class HordeModelRankingTests(
    unittest.TestCase
):
    def setUp(self):
        horde.clear_text_model_cache()

    def tearDown(self):
        horde.clear_text_model_cache()

    @patch("horde.requests.get")
    def test_ranking_matches_sillytavern_priority(
        self,
        mocked_get,
    ):
        active = [
            {
                "name": "fast-unlisted",
                "performance": 100,
            },
            {
                "name": "listed",
                "performance": 20,
            },
            {
                "name": "popular-slow",
                "performance": 5,
            },
            {
                "name": "popular-fast",
                "performance": 50,
            },
        ]

        metadata = {
            "listed": {
                "tags": [],
            },
            "popular-slow": {
                "tags": ["popular"],
            },
            "popular-fast": {
                "tags": ["popular"],
            },
        }

        mocked_get.side_effect = [
            FakeResponse(active),
            FakeResponse(metadata),
        ]

        names = (
            horde.get_ranked_text_model_names(
                force=True
            )
        )

        self.assertEqual(
            names,
            [
                "popular-fast",
                "popular-slow",
                "listed",
                "fast-unlisted",
            ],
        )

    @patch("horde.requests.get")
    def test_metadata_failure_still_returns_live_models(
        self,
        mocked_get,
    ):
        active = [
            {
                "name": "slow",
                "performance": 5,
            },
            {
                "name": "fast",
                "performance": 50,
            },
        ]

        mocked_get.side_effect = [
            FakeResponse(active),
            requests.RequestException(
                "metadata unavailable"
            ),
        ]

        names = (
            horde.get_ranked_text_model_names(
                force=True
            )
        )

        self.assertEqual(
            names,
            [
                "fast",
                "slow",
            ],
        )

    @patch("horde.requests.get")
    def test_model_results_are_cached(
        self,
        mocked_get,
    ):
        active = [
            {
                "name": "model-a",
                "performance": 10,
            },
        ]

        mocked_get.side_effect = [
            FakeResponse(active),
            FakeResponse({}),
        ]

        first = (
            horde.get_ranked_text_model_names()
        )
        second = (
            horde.get_ranked_text_model_names()
        )

        self.assertEqual(
            first,
            ["model-a"],
        )
        self.assertEqual(
            second,
            ["model-a"],
        )
        self.assertEqual(
            mocked_get.call_count,
            2,
        )


def fake_context(
    *,
    preferred_model="skyfall",
    fallback_models=None,
):
    return {
        "runtime": {
            "character_id": 7,
            "preferred_model": (
                preferred_model
            ),
            "fallback_models": (
                fallback_models
            ),
            "may_invoke_ai_brain": True,
        }
    }


class CharacterBrainLiveModelTests(
    unittest.TestCase
):
    def _run(
        self,
        *,
        context,
        live_models,
        generator,
    ):
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
            return run_character_brain(
                7,
                {"current": "Hello."},
                generator=generator,
                model_provider=(
                    lambda: list(
                        live_models
                    )
                ),
            )

    def test_configured_preference_wins_when_active(
        self,
    ):
        attempted = []

        def generator(**kwargs):
            attempted.append(
                kwargs["model"]
            )

            return json.dumps({
                "speech": "Here.",
                "thought": None,
                "action": None,
            })

        result = self._run(
            context=fake_context(),
            live_models=[
                "top-ranked",
                "skyfall",
            ],
            generator=generator,
        )

        self.assertEqual(
            attempted,
            ["skyfall"],
        )
        self.assertEqual(
            result.model,
            "skyfall",
        )

    def test_missing_preference_uses_top_live_model(
        self,
    ):
        attempted = []

        def generator(**kwargs):
            attempted.append(
                kwargs["model"]
            )

            return json.dumps({
                "speech": "Here.",
                "thought": None,
                "action": None,
            })

        result = self._run(
            context=fake_context(),
            live_models=[
                "top-ranked",
                "second-ranked",
            ],
            generator=generator,
        )

        self.assertEqual(
            attempted,
            ["top-ranked"],
        )
        self.assertEqual(
            result.model,
            "top-ranked",
        )

    def test_failed_preference_moves_to_next_ranked_model(
        self,
    ):
        attempted = []

        def generator(**kwargs):
            model = kwargs["model"]
            attempted.append(model)

            if model == "skyfall":
                raise RuntimeError(
                    "worker failed"
                )

            return json.dumps({
                "speech": "Fallback.",
                "thought": None,
                "action": None,
            })

        result = self._run(
            context=fake_context(),
            live_models=[
                "top-ranked",
                "skyfall",
                "second-ranked",
            ],
            generator=generator,
        )

        self.assertEqual(
            attempted,
            [
                "skyfall",
                "top-ranked",
            ],
        )
        self.assertEqual(
            result.model,
            "top-ranked",
        )

    def test_discovery_failure_preserves_configured_model(
        self,
    ):
        attempted = []

        def generator(**kwargs):
            attempted.append(
                kwargs["model"]
            )

            return json.dumps({
                "speech": "Still here.",
                "thought": None,
                "action": None,
            })

        with (
            patch(
                "character_brain.build_character_context",
                return_value=fake_context(),
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
                generator=generator,
                model_provider=(
                    lambda: (
                        _raise_discovery_error()
                    )
                ),
            )

        self.assertEqual(
            attempted,
            ["skyfall"],
        )
        self.assertEqual(
            result.model,
            "skyfall",
        )


def _raise_discovery_error():
    raise RuntimeError(
        "Horde status unavailable"
    )


class ModelSelectorTests(
    unittest.TestCase
):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.set_database_path(
            Path(self.tmp.name) / "test.db"
        )
        initialize_database()

        conn = get_connection()

        try:
            cur = conn.execute(
                """
                INSERT INTO characters(
                    name,
                    preferred_model,
                    fallback_models
                )
                VALUES(?,?,?)
                """,
                (
                    "Antti Rautio",
                    "old-model",
                    "fallback-a,fallback-b",
                ),
            )
            self.character_id = int(
                cur.lastrowid
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_number_selection_uses_live_order(
        self,
    ):
        chosen = resolve_model_selection(
            "2",
            [
                "model-a",
                "model-b",
                "model-c",
            ],
        )

        self.assertEqual(
            chosen,
            "model-b",
        )

    def test_exact_name_selection_is_case_insensitive(
        self,
    ):
        chosen = resolve_model_selection(
            "MODEL-B",
            [
                "model-a",
                "model-b",
            ],
        )

        self.assertEqual(
            chosen,
            "model-b",
        )

    def test_setting_preferred_model_preserves_existing_fallbacks(
        self,
    ):
        set_character_preferred_model(
            "Antti Rautio",
            "new-model",
        )

        config = get_character_model_config(
            "Antti Rautio"
        )

        self.assertEqual(
            config["preferred_model"],
            "new-model",
        )
        self.assertEqual(
            config["fallback_models"],
            "fallback-a,fallback-b",
        )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
