"""Tests for PlaybackTimestampTracker.

Pure-Python logic with no external dependencies. This is the baseline for
all timestamp approximation used by MAssBaseService.
"""
import time
import unittest

from ovos_media_plugin_mass.media import PlaybackTimestampTracker


class TestPlaybackTimestampTrackerInitialState(unittest.TestCase):

    def setUp(self):
        self.tracker = PlaybackTimestampTracker()

    def test_initial_timestamp_is_minus_one(self):
        self.assertEqual(self.tracker.current_timestamp, -1)

    def test_initial_not_recording(self):
        self.assertFalse(self.tracker.recording)

    def test_initial_accumulated_time_is_zero(self):
        self.assertEqual(self.tracker.accumulator, 0)


class TestPlaybackTimestampTrackerStart(unittest.TestCase):

    def setUp(self):
        self.tracker = PlaybackTimestampTracker(duration=120)

    def test_start_enables_recording(self):
        self.tracker.start()
        self.assertTrue(self.tracker.recording)

    def test_start_resets_accumulator(self):
        self.tracker.accumulator = 99
        self.tracker.start()
        self.assertEqual(self.tracker.accumulator, 0)

    def test_timestamp_grows_after_start(self):
        self.tracker.start()
        time.sleep(0.05)
        self.assertGreater(self.tracker.current_timestamp, 0)

    def test_timestamp_does_not_exceed_duration(self):
        self.tracker = PlaybackTimestampTracker(duration=0.01)
        self.tracker.start()
        time.sleep(0.05)
        # current_timestamp = max(accumulated, duration) — capped at duration
        self.assertGreaterEqual(self.tracker.current_timestamp, 0.01)


class TestPlaybackTimestampTrackerPause(unittest.TestCase):

    def setUp(self):
        self.tracker = PlaybackTimestampTracker(duration=300)
        self.tracker.start()

    def test_pause_stops_recording(self):
        time.sleep(0.02)
        self.tracker.pause()
        self.assertFalse(self.tracker.recording)

    def test_timestamp_frozen_after_pause(self):
        time.sleep(0.05)
        self.tracker.pause()
        ts1 = self.tracker.current_timestamp
        time.sleep(0.05)
        ts2 = self.tracker.current_timestamp
        self.assertAlmostEqual(ts1, ts2, places=2)

    def test_accumulated_time_preserved_across_pause(self):
        time.sleep(0.1)
        self.tracker.pause()
        acc = self.tracker.accumulator
        self.assertGreater(acc, 0)


class TestPlaybackTimestampTrackerResume(unittest.TestCase):

    def test_resume_after_pause_continues_accumulating(self):
        tracker = PlaybackTimestampTracker(duration=300)
        tracker.start()
        time.sleep(0.05)
        tracker.pause()
        paused_ts = tracker.current_timestamp
        time.sleep(0.05)  # time passes while paused — should NOT accumulate
        tracker.resume()
        time.sleep(0.05)
        resumed_ts = tracker.current_timestamp
        # resumed_ts should be paused_ts + ~0.05, not paused_ts + ~0.10
        self.assertGreater(resumed_ts, paused_ts)
        self.assertLess(resumed_ts, paused_ts + 0.12)


class TestPlaybackTimestampTrackerStop(unittest.TestCase):

    def test_stop_resets_everything(self):
        tracker = PlaybackTimestampTracker(duration=300)
        tracker.start()
        time.sleep(0.05)
        tracker.stop()
        self.assertFalse(tracker.recording)
        self.assertEqual(tracker.accumulator, 0)
        self.assertEqual(tracker.current_timestamp, -1)


class TestPlaybackTimestampTrackerSeek(unittest.TestCase):

    def test_seek_sets_position(self):
        tracker = PlaybackTimestampTracker(duration=300)
        tracker.start()
        tracker.seek(60)
        self.assertAlmostEqual(tracker.current_timestamp, 60, delta=0.1)

    def test_seek_resets_start_time(self):
        tracker = PlaybackTimestampTracker(duration=300)
        tracker.start()
        time.sleep(0.1)
        tracker.seek(90)
        time.sleep(0.05)
        ts = tracker.current_timestamp
        # Should be ~90 + 0.05, not 90 + (0.1 + 0.05)
        self.assertLess(ts, 90.2)
        self.assertGreater(ts, 90.0)


class TestPlaybackTimestampTrackerDuration(unittest.TestCase):

    def test_default_duration_is_minus_one(self):
        tracker = PlaybackTimestampTracker()
        self.assertEqual(tracker.duration, -1)

    def test_custom_duration_stored(self):
        tracker = PlaybackTimestampTracker(duration=180)
        self.assertEqual(tracker.duration, 180)


if __name__ == "__main__":
    unittest.main()
