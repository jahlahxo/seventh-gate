import importlib.util
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRIPT = (
    HERE.parent
    / "tools"
    / "configure_campaign.py"
)

spec = (
    importlib.util
    .spec_from_file_location(
        "finland_campaign_config",
        SCRIPT,
    )
)
module = (
    importlib.util
    .module_from_spec(
        spec
    )
)
spec.loader.exec_module(
    module
)


class FinlandCampaignConfigTests(unittest.TestCase):
    def test_opening_time_is_evening_10_november_1878(self):
        self.assertEqual(
            module.CAMPAIGN_START,
            "1878-11-10 18:30:00",
        )

    def test_continuity_and_story_style_defaults_are_declared(self):
        settings = (
            module.CAMPAIGN_SETTINGS
        )

        self.assertEqual(
            settings[
                "recent_scene_token_budget"
            ],
            "7000",
        )
        self.assertEqual(
            settings[
                "thought_display"
            ],
            "discord_italics",
        )
        self.assertIn(
            "1-3",
            settings[
                "rp_public_soft_length"
            ],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
