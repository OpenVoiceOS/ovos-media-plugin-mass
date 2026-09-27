"""Regression test: a track that ends naturally must report
PlaybackEvent.END_OF_MEDIA - exactly like an explicit stop reports
PlaybackEvent.STOPPED - via the bound event reporter, never as an
``ovos.common_play.*`` bus message (the daemon owns that wire, not the
backend).

Two natural-end paths are covered:

* known duration - ``check_ended()`` (spawned from ``play()``) detects the
  tracker's timestamp reaching the track duration.
* unknown duration (``tracker.duration <= 0``, e.g. a live/radio stream) -
  ``watch_player_state()`` (spawned instead) detects the MAss player
  reporting idle/stopped after having played.

``create_daemon`` is intercepted so the daemon body runs synchronously
under our control (no real threads/sleeps), and ``time.sleep`` is patched
to drive the loop's exit condition deterministically instead of racing a
real clock.
"""
import unittest
from unittest.mock import MagicMock, patch

from ovos_plugin_manager.templates.media import PlaybackEvent
from ovos_utils.fakebus import FakeBus

from ovos_media_plugin_mass.media import MAssBaseService


def _make_config():
    return {"url": "http://localhost:8095", "identifier": "uuid:test-player-123"}


def _make_svc():
    bus = FakeBus()
    events = []
    common_play_msgs = []
    bus.on("ovos.common_play.media.state",
           lambda msg: common_play_msgs.append(msg))
    bus.on("ovos.common_play.player.state",
           lambda msg: common_play_msgs.append(msg))
    with patch.object(MAssBaseService, "refresh_player_state"), \
         patch.object(MAssBaseService, "_start_ping_loop"), \
         patch("ovos_media_plugin_mass.media.SimpleHTTPMusicAssistantClient"):
        svc = MAssBaseService(_make_config(), bus=bus)
    svc.bind_event_reporter(lambda event, **data: events.append((event, data)))
    svc._loaded_uri = "library://track/1"
    svc.api = MagicMock()
    svc.api.get_active_queue.return_value = {"queue_id": "q1"}
    return svc, events, common_play_msgs


class TestNaturalEndKnownDuration(unittest.TestCase):
    def test_check_ended_emits_end_of_media(self):
        svc, events, common_play_msgs = _make_svc()
        svc.tracker.duration = 10

        with patch("ovos_media_plugin_mass.media.create_daemon") as mock_daemon:
            svc.play()

        # play() itself already reports TRACK_START; the daemon under test
        # (check_ended) is asserted separately below.
        self.assertIn((PlaybackEvent.TRACK_START, {"uri": "library://track/1"}), events)

        mock_daemon.assert_called_once()
        check_ended = mock_daemon.call_args[0][0]
        self.assertEqual(check_ended.__name__, "check_ended")

        # drive the loop: first (only) time.sleep call fast-forwards the
        # tracker straight to the track's duration, with no stop() ever
        # called by us
        def _fast_forward(_):
            svc.tracker.accumulator = svc.tracker.duration
            svc.tracker.start_ts = 0
            svc.tracker.recording = False

        with patch("ovos_media_plugin_mass.media.time.sleep", side_effect=_fast_forward):
            check_ended()

        self.assertIn((PlaybackEvent.END_OF_MEDIA, {"uri": "library://track/1"}), events,
                       f"natural end-of-media never reported END_OF_MEDIA; saw: {events}")
        self.assertEqual(common_play_msgs, [],
                          "backend must never emit ovos.common_play.* itself")
        self.assertFalse(svc.is_playing)
        self.assertFalse(svc._stop_requested)

    def test_real_stop_converges_to_stopped_not_end_of_media(self):
        """A real ``svc.stop()`` call must make the *same* check_ended
        convergence point report STOPPED, not END_OF_MEDIA - ``stop()``
        (concrete on the v2 template) records ``_stop_requested`` before
        delegating to ``_stop()``, and ``_stop()`` itself reports nothing."""
        svc, events, common_play_msgs = _make_svc()
        svc.tracker.duration = 10

        with patch("ovos_media_plugin_mass.media.create_daemon") as mock_daemon:
            svc.play()
        check_ended = mock_daemon.call_args[0][0]

        svc.report = MagicMock(wraps=svc.report)
        svc.stop()
        self.assertTrue(svc._stop_requested)
        svc.report.assert_not_called()  # _stop() itself reports nothing

        # is_playing is already False (set by _stop()); the watcher's own
        # loop condition fails immediately, converging straight to
        # report_track_end without needing another sleep tick
        check_ended()

        self.assertIn((PlaybackEvent.STOPPED, {"uri": "library://track/1"}), events,
                       f"explicit stop never converged to STOPPED; saw: {events}")
        self.assertNotIn(PlaybackEvent.END_OF_MEDIA, [e for e, _ in events])
        self.assertEqual(common_play_msgs, [])
        self.assertFalse(svc._stop_requested,
                          "report_track_end must clear _stop_requested afterward")


class TestNaturalEndUnknownDuration(unittest.TestCase):
    """duration <= 0 (e.g. live/radio stream) - fallback watcher path."""

    def test_play_spawns_watch_player_state_when_duration_unknown(self):
        svc, _, _ = _make_svc()
        svc.tracker.duration = -1

        with patch("ovos_media_plugin_mass.media.create_daemon") as mock_daemon:
            svc.play()

        mock_daemon.assert_called_once()
        target = mock_daemon.call_args[0][0]
        self.assertEqual(target.__name__, "watch_player_state")

    def test_watch_player_state_emits_end_of_media_on_idle(self):
        svc, events, common_play_msgs = _make_svc()
        svc.tracker.duration = -1

        with patch("ovos_media_plugin_mass.media.create_daemon") as mock_daemon:
            svc.play()
        watch_player_state = mock_daemon.call_args[0][0]

        svc.player_state = {"state": "playing", "available": True}

        # first tick: still playing per MAss, no stop() ever called by us -
        # simulate the player going idle on its own on the *next* poll
        def _report_idle(_):
            svc.player_state = {"state": "idle", "available": True}

        with patch("ovos_media_plugin_mass.media.time.sleep", side_effect=_report_idle):
            watch_player_state()

        self.assertIn((PlaybackEvent.END_OF_MEDIA, {"uri": "library://track/1"}), events,
                       f"natural end-of-media never reported END_OF_MEDIA; saw: {events}")
        self.assertEqual(common_play_msgs, [],
                          "backend must never emit ovos.common_play.* itself")
        self.assertFalse(svc._stop_requested)


if __name__ == "__main__":
    unittest.main()
