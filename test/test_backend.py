"""Tests for MAssBaseService, MAssAudioService, and load_service().

All network calls are mocked — no real Music Assistant server needed.
"""
import unittest
from unittest.mock import MagicMock, patch

from ovos_utils.fakebus import FakeBus


def _make_config(url="http://localhost:8095",
                 identifier="uuid:test-player-123",
                 player_type="dlna",
                 active=True):
    return {
        "url": url,
        "identifier": identifier,
        "player_type": player_type,
        "active": active,
    }


class TestMAssBaseServiceInit(unittest.TestCase):

    def test_missing_url_raises(self):
        from ovos_media_plugin_mass.media import MAssBaseService
        with self.assertRaises((ValueError, Exception)):
            MAssBaseService({"identifier": "uuid:123"}, bus=FakeBus())

    def test_missing_identifier_raises(self):
        from ovos_media_plugin_mass.media import MAssBaseService
        with self.assertRaises((ValueError, Exception)):
            MAssBaseService({"url": "http://localhost:8095"}, bus=FakeBus())

    def test_valid_config_stores_url_and_player_id(self):
        from ovos_media_plugin_mass.media import MAssBaseService
        cfg = _make_config()
        bus = FakeBus()
        with patch.object(MAssBaseService, "refresh_player_state"), \
             patch.object(MAssBaseService, "_start_ping_loop"):
            svc = MAssBaseService(cfg, bus=bus)
        self.assertEqual(svc.url, "http://localhost:8095")
        self.assertEqual(svc.player_id, "uuid:test-player-123")


class TestMAssBaseServiceSupportedUris(unittest.TestCase):

    def _make_svc(self, available=True, player_type="dlna",
                  force_http=False, force_spotify=False):
        from ovos_media_plugin_mass.media import MAssBaseService
        cfg = _make_config(player_type=player_type)
        cfg["force_enable_http"] = force_http
        cfg["force_enable_spotify"] = force_spotify
        bus = FakeBus()
        with patch.object(MAssBaseService, "refresh_player_state"), \
             patch.object(MAssBaseService, "_start_ping_loop"):
            svc = MAssBaseService(cfg, bus=bus)
        svc.player_state = {"available": available, "player_type": player_type}
        return svc

    def test_returns_empty_when_unavailable(self):
        svc = self._make_svc(available=False)
        self.assertEqual(svc.supported_uris(), [])

    def test_returns_library_when_available(self):
        svc = self._make_svc(available=True)
        uris = svc.supported_uris()
        self.assertIn("library", uris)

    def test_http_not_included_by_default(self):
        svc = self._make_svc(available=True, force_http=False)
        uris = svc.supported_uris()
        self.assertNotIn("http", uris)
        self.assertNotIn("https", uris)

    def test_http_included_when_forced(self):
        svc = self._make_svc(available=True, force_http=True)
        uris = svc.supported_uris()
        self.assertIn("http", uris)
        self.assertIn("https", uris)

    def test_spotify_not_included_by_default(self):
        svc = self._make_svc(available=True, force_spotify=False)
        self.assertNotIn("spotify", svc.supported_uris())

    def test_spotify_included_when_forced(self):
        svc = self._make_svc(available=True, force_spotify=True)
        self.assertIn("spotify", svc.supported_uris())


class TestMAssBaseServicePlaybackDelegation(unittest.TestCase):
    """stop/pause/resume/seek must call the right MA API methods."""

    def _make_svc(self):
        from ovos_media_plugin_mass.media import MAssBaseService
        cfg = _make_config()
        bus = FakeBus()
        with patch.object(MAssBaseService, "refresh_player_state"), \
             patch.object(MAssBaseService, "_start_ping_loop"):
            svc = MAssBaseService(cfg, bus=bus)
        svc.player_state = {"available": True, "player_type": "dlna"}
        svc.api = MagicMock()
        svc.api.get_active_queue.return_value = {"queue_id": "q-123"}
        svc.tracker = MagicMock()
        return svc

    def test_stop_calls_api_stop(self):
        svc = self._make_svc()
        svc.is_playing = True
        svc.stop()
        svc.api.player_command_stop.assert_called_once_with(svc.player_id)

    def test_stop_returns_false_when_not_playing(self):
        svc = self._make_svc()
        svc.is_playing = False
        result = svc.stop()
        self.assertFalse(result)
        svc.api.player_command_stop.assert_not_called()

    def test_pause_calls_queue_pause(self):
        svc = self._make_svc()
        svc.pause()
        svc.api.queue_command_pause.assert_called_once_with("q-123")

    def test_resume_calls_queue_play(self):
        svc = self._make_svc()
        svc.resume()
        svc.api.queue_command_play.assert_called_once_with("q-123")

    def test_seek_calls_player_seek(self):
        svc = self._make_svc()
        svc.set_track_position(30000)  # 30 000 ms → 30 s
        svc.api.player_command_seek.assert_called_once_with(svc.player_id, 30)

    def test_volume_down_delegates_to_api(self):
        svc = self._make_svc()
        svc.lower_volume()
        svc.api.player_command_volume_down.assert_called_once_with(svc.player_id)

    def test_volume_up_delegates_to_api(self):
        svc = self._make_svc()
        svc.restore_volume()
        svc.api.player_command_volume_up.assert_called_once_with(svc.player_id)


class TestLoadServiceLegacy(unittest.TestCase):
    """load_service() must parse the legacy Audio.backends config and
    instantiate one MAssAudioService per active 'ovos_mass' or 'mass' backend."""

    def test_no_matching_backends_returns_empty(self):
        from ovos_media_plugin_mass.audio import load_service
        config = {"backends": {"vlc": {"type": "ovos_vlc", "active": True}}}
        result = load_service(config, FakeBus())
        self.assertEqual(result, [])

    def test_inactive_backend_skipped(self):
        from ovos_media_plugin_mass.audio import load_service
        config = {"backends": {
            "mass-player": {"type": "ovos_mass", "url": "http://h:8095",
                            "identifier": "uuid:x", "active": False}
        }}
        result = load_service(config, FakeBus())
        self.assertEqual(result, [])

    def test_active_mass_backend_instantiated(self):
        from ovos_media_plugin_mass.audio import load_service, MAssAudioService
        config = {"backends": {
            "mass-player": {"type": "ovos_mass", "url": "http://h:8095",
                            "identifier": "uuid:x", "active": True}
        }}
        with patch.object(MAssAudioService, "__init__", return_value=None):
            result = load_service(config, FakeBus())
        self.assertEqual(len(result), 1)

    def test_multiple_active_backends_all_instantiated(self):
        from ovos_media_plugin_mass.audio import load_service, MAssAudioService
        config = {"backends": {
            "player-a": {"type": "ovos_mass", "url": "http://h:8095",
                         "identifier": "uuid:a", "active": True},
            "player-b": {"type": "mass", "url": "http://h:8095",
                         "identifier": "uuid:b", "active": True},
        }}
        with patch.object(MAssAudioService, "__init__", return_value=None):
            result = load_service(config, FakeBus())
        self.assertEqual(len(result), 2)

    def test_type_mass_also_matched(self):
        from ovos_media_plugin_mass.audio import load_service, MAssAudioService
        config = {"backends": {
            "legacy": {"type": "mass", "url": "http://h:8095",
                       "identifier": "uuid:y", "active": True}
        }}
        with patch.object(MAssAudioService, "__init__", return_value=None):
            result = load_service(config, FakeBus())
        self.assertEqual(len(result), 1)


class TestMAssAudioServiceDelegation(unittest.TestCase):
    """MAssAudioService must delegate all calls to the inner MAssOCPAudioService."""

    def _make_svc(self):
        from ovos_media_plugin_mass.audio import MAssAudioService
        cfg = _make_config()
        bus = FakeBus()
        with patch("ovos_media_plugin_mass.audio.MAssOCPAudioService.__init__",
                   return_value=None):
            svc = MAssAudioService(cfg, bus, name="test-mass")
        inner = MagicMock()
        svc.mass = inner
        return svc, inner

    def test_play_delegates(self):
        svc, inner = self._make_svc()
        svc.play()
        inner.play.assert_called_once()

    def test_stop_delegates(self):
        svc, inner = self._make_svc()
        svc.stop()
        inner.stop.assert_called_once()

    def test_pause_delegates(self):
        svc, inner = self._make_svc()
        svc.pause()
        inner.pause.assert_called_once()

    def test_resume_delegates(self):
        svc, inner = self._make_svc()
        svc.resume()
        inner.resume.assert_called_once()

    def test_supported_uris_delegates(self):
        svc, inner = self._make_svc()
        inner.supported_uris.return_value = ["library"]
        result = svc.supported_uris()
        self.assertEqual(result, ["library"])

    def test_track_info_delegates(self):
        svc, inner = self._make_svc()
        inner.meta = {"title": "Test"}
        result = svc.track_info()
        self.assertEqual(result, {"title": "Test"})


if __name__ == "__main__":
    unittest.main()
