"""Regression test: a track that ends naturally must report
MediaState.END_OF_MEDIA / PlayerState.STOPPED on the bus, exactly like an
explicit stop does.

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

from ovos_utils.fakebus import FakeBus
from ovos_utils.ocp import MediaState, PlayerState

from ovos_media_plugin_mass.media import MAssBaseService


def _make_config():
    return {"url": "http://localhost:8095", "identifier": "uuid:test-player-123"}


def _make_svc():
    bus = FakeBus()
    states = []
    player_states = []
    bus.on("ovos.common_play.media.state",
           lambda msg: states.append(msg.data.get("state")))
    bus.on("ovos.common_play.player.state",
           lambda msg: player_states.append(msg.data.get("state")))
    with patch.object(MAssBaseService, "refresh_player_state"), \
         patch.object(MAssBaseService, "_start_ping_loop"), \
         patch("ovos_media_plugin_mass.media.SimpleHTTPMusicAssistantClient"):
        svc = MAssBaseService(_make_config(), bus=bus)
    svc._now_playing = "library://track/1"
    svc.api = MagicMock()
    svc.api.get_active_queue.return_value = {"queue_id": "q1"}
    return svc, states, player_states


class TestNaturalEndKnownDuration(unittest.TestCase):
    def test_check_ended_emits_end_of_media(self):
        svc, states, player_states = _make_svc()
        svc.tracker.duration = 10

        with patch("ovos_media_plugin_mass.media.create_daemon") as mock_daemon:
            svc.play()

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

        self.assertIn(MediaState.END_OF_MEDIA, states,
                       f"natural end-of-media never emitted END_OF_MEDIA; saw: {states}")
        self.assertIn(PlayerState.STOPPED, player_states,
                       f"natural end-of-media never emitted PlayerState.STOPPED; saw: {player_states}")
        self.assertFalse(svc.is_playing)


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
        svc, states, player_states = _make_svc()
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

        self.assertIn(MediaState.END_OF_MEDIA, states,
                       f"natural end-of-media never emitted END_OF_MEDIA; saw: {states}")
        self.assertIn(PlayerState.STOPPED, player_states,
                       f"natural end-of-media never emitted PlayerState.STOPPED; saw: {player_states}")


if __name__ == "__main__":
    unittest.main()
