import tempfile, unittest
from pathlib import Path
import database
from campaign_clock import (advance_campaign_time,get_campaign_clock,
 get_campaign_datetime,get_clock_history,initialize_campaign_clock,
 set_campaign_datetime,set_clock_paused,set_time_scale)

class CampaignClockTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        database.set_database_path(Path(self.tmp.name)/"clock.db")
        database.initialize_database()
    def tearDown(self):
        database.reset_database_path(); self.tmp.cleanup()
    def test_initializes_once_without_reset(self):
        initialize_campaign_clock("1847-03-10 06:30:00")
        advance_campaign_time(hours=2,reason="Morning passes.",source_type="test")
        initialize_campaign_clock("1900-01-01 00:00:00")
        self.assertEqual(get_campaign_clock()["current_datetime"],"1847-03-10 08:30:00")
    def test_crosses_day_boundary(self):
        initialize_campaign_clock("1847-03-10 23:30:00")
        advance_campaign_time(hours=2,reason="Night passes.",source_type="test")
        self.assertEqual(get_campaign_clock()["current_datetime"],"1847-03-11 01:30:00")
    def test_leap_year(self):
        initialize_campaign_clock("1848-02-28 12:00:00")
        advance_campaign_time(days=1,reason="A day passes.",source_type="test")
        self.assertEqual(get_campaign_clock()["current_datetime"],"1848-02-29 12:00:00")
    def test_backward_rejected(self):
        initialize_campaign_clock("1847-03-10 12:00:00")
        with self.assertRaises(ValueError):
            set_campaign_datetime("1847-03-09 12:00:00",reason="rewind",source_type="test")
    def test_change_audited(self):
        initialize_campaign_clock("1847-03-10 12:00:00")
        advance_campaign_time(minutes=45,reason="Travel.",source_type="test",source_id="journey-1")
        h=get_clock_history()
        self.assertEqual(len(h),1); self.assertEqual(h[0]["seconds_advanced"],2700)
        self.assertEqual(h[0]["source_id"],"journey-1")
    def test_wall_clock_does_not_advance_campaign(self):
        initialize_campaign_clock("1847-03-10 12:00:00")
        self.assertEqual(get_campaign_datetime(),get_campaign_datetime())
    def test_pause_and_scale_persist(self):
        initialize_campaign_clock("1847-03-10 12:00:00")
        set_clock_paused(True); set_time_scale(2.5)
        c=get_campaign_clock()
        self.assertEqual(c["paused"],1); self.assertEqual(c["time_scale"],2.5)

if __name__=="__main__":
    unittest.main(verbosity=2)
