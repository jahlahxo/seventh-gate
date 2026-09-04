import tempfile
import unittest
from pathlib import Path

import database
from campaign import (
    assert_discord_guild_matches,
    configure_campaign,
    get_campaign_identity,
    get_campaign_setting,
    set_campaign_setting,
)
from campaign_clock import (
    get_campaign_clock,
    get_campaign_datetime,
    initialize_campaign_clock,
)


class CampaignConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database.set_database_path(Path(self.tmp.name) / "campaign.db")
        database.initialize_database()

    def tearDown(self):
        database.reset_database_path()
        self.tmp.cleanup()

    def test_fresh_engine_has_no_hidden_historical_start_date(self):
        with self.assertRaises(RuntimeError):
            get_campaign_clock()

    def test_clock_requires_explicit_start_when_unconfigured(self):
        with self.assertRaises(RuntimeError):
            initialize_campaign_clock()

    def test_configure_campaign_sets_identity_and_clock(self):
        identity = configure_campaign(
            campaign_name="Northern Winter",
            setting_name="Historical Finland",
            start_datetime="1847-03-10 06:30:00",
            calendar_name="gregorian",
            discord_guild_id="111222333",
        )
        self.assertEqual(identity["campaign_name"], "Northern Winter")
        self.assertEqual(identity["setting_name"], "Historical Finland")
        self.assertEqual(identity["discord_guild_id"], "111222333")
        self.assertEqual(identity["current_datetime"], "1847-03-10 06:30:00")

    def test_different_setting_can_use_completely_different_start(self):
        configure_campaign(
            campaign_name="Cursed City",
            setting_name="Modern Supernatural",
            start_datetime="2026-04-11 19:45:00",
            calendar_name="gregorian",
        )
        self.assertEqual(
            get_campaign_datetime().strftime("%Y-%m-%d %H:%M:%S"),
            "2026-04-11 19:45:00",
        )

    def test_reinitialization_does_not_reset_running_campaign_clock(self):
        configure_campaign(
            campaign_name="Campaign A",
            setting_name="Setting A",
            start_datetime="1901-01-01 08:00:00",
        )
        initialize_campaign_clock("1999-01-01 00:00:00")
        self.assertEqual(
            get_campaign_clock()["current_datetime"],
            "1901-01-01 08:00:00",
        )

    def test_custom_campaign_settings_are_extensible(self):
        set_campaign_setting("magic_system", "cursed_energy")
        self.assertEqual(
            get_campaign_setting("magic_system"),
            "cursed_energy",
        )

    def test_wrong_discord_server_is_rejected(self):
        configure_campaign(
            campaign_name="Bound Campaign",
            setting_name="Any Setting",
            start_datetime="2000-01-01 00:00:00",
            discord_guild_id="123",
        )
        self.assertTrue(assert_discord_guild_matches("123"))
        with self.assertRaises(RuntimeError):
            assert_discord_guild_matches("999")


if __name__ == "__main__":
    unittest.main(verbosity=2)
