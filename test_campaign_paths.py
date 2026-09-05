from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import database
from campaign_paths import (
    get_campaign_directory,
    resolve_campaign_resource,
)


class CampaignPathTests(
    unittest.TestCase
):
    def setUp(self):
        self.tmp = (
            tempfile.TemporaryDirectory()
        )

        self.campaign_dir = (
            Path(self.tmp.name)
            / "campaigns"
            / "example_world"
        )

        database.set_database_path(
            self.campaign_dir
            / "seventh_gate.db"
        )

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_campaign_directory_follows_active_database(
        self,
    ):
        self.assertEqual(
            get_campaign_directory(),
            self.campaign_dir.resolve(),
        )

    def test_resource_resolves_inside_campaign(
        self,
    ):
        expected = (
            self.campaign_dir
            / "world"
            / "grounding.json"
        ).resolve()

        self.assertEqual(
            resolve_campaign_resource(
                "world/grounding.json"
            ),
            expected,
        )

    def test_absolute_resource_path_is_refused(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            resolve_campaign_resource(
                Path(self.tmp.name)
                / "outside.json"
            )

    def test_resource_cannot_escape_campaign(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            resolve_campaign_resource(
                "../other_world/secret.json"
            )


if __name__ == "__main__":
    unittest.main(
        verbosity=2
    )
