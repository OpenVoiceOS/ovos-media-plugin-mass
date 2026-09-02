# Copyright 2026 OpenVoiceOS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Unit tests for ovos-media-plugin-mass.

Covers MAssOCPAudioService (media.py) and MAssAudioService (audio.py).
SimpleHTTPMusicAssistantClient is mocked throughout to avoid live network
connections.
"""
import unittest
from unittest.mock import MagicMock, patch

from ovos_plugin_manager.templates.media import RemoteAudioPlayerBackend
from ovos_utils.fakebus import FakeBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_CONFIG = {
    "url": "http://localhost:8095",
    "identifier": "test-player"
}


def _make_ocp_service() -> "MAssOCPAudioService":  # noqa: F821
    """Return a MAssOCPAudioService with the HTTP client mocked."""
    from ovos_media_plugin_mass.media import MAssOCPAudioService
    with patch("ovos_media_plugin_mass.media.SimpleHTTPMusicAssistantClient") as MockClient, \
            patch.object(MAssOCPAudioService, "_start_ping_loop", lambda self: None):
        client = MockClient.return_value
        client.get_player_state.return_value = {"available": True, "player_type": "generic"}
        client.get_active_queue.return_value = {"queue_id": "q1"}
        svc = MAssOCPAudioService(_BASE_CONFIG.copy(), bus=FakeBus())
        svc.api = client
    return svc


def _make_legacy_service() -> "MAssAudioService":  # noqa: F821
    """Return a MAssAudioService with the inner OCP service's HTTP client mocked."""
    from ovos_media_plugin_mass.media import MAssOCPAudioService
    from ovos_media_plugin_mass.audio import MAssAudioService
    with patch("ovos_media_plugin_mass.media.SimpleHTTPMusicAssistantClient") as MockClient, \
            patch.object(MAssOCPAudioService, "_start_ping_loop", lambda self: None):
        client = MockClient.return_value
        client.get_player_state.return_value = {"available": True, "player_type": "generic"}
        client.get_active_queue.return_value = {"queue_id": "q1"}
        svc = MAssAudioService(_BASE_CONFIG.copy(), FakeBus(), "mass")
        svc.mass.api = client
    return svc


# ---------------------------------------------------------------------------
# OCP service class import test
# ---------------------------------------------------------------------------

class TestMAssOCPServiceExists(unittest.TestCase):
    """Basic importability and inheritance check."""

    def test_ocp_service_class_exists(self) -> None:
        """MAssOCPAudioService is importable and is a RemoteAudioPlayerBackend."""
        from ovos_media_plugin_mass.media import MAssOCPAudioService
        self.assertTrue(issubclass(MAssOCPAudioService, RemoteAudioPlayerBackend))


# ---------------------------------------------------------------------------
# Legacy wrapper tests
# ---------------------------------------------------------------------------

class TestMAssLegacyWrapper(unittest.TestCase):
    """MAssAudioService delegates all calls to the inner MAssOCPAudioService."""

    def setUp(self) -> None:
        self.svc = _make_legacy_service()

    def test_legacy_wrapper_delegates_play(self) -> None:
        """play() forwards to inner mass.play()."""
        self.svc.mass.play = MagicMock()
        self.svc.play()
        self.svc.mass.play.assert_called_once()

    def test_legacy_wrapper_stop_returns_bool(self) -> None:
        """stop() always returns a bool (bug-fix regression test)."""
        self.svc.mass.stop = MagicMock(return_value=True)
        result = self.svc.stop()
        self.assertIsInstance(result, bool)
        self.assertTrue(result)

        self.svc.mass.stop = MagicMock(return_value=False)
        result = self.svc.stop()
        self.assertIsInstance(result, bool)
        self.assertFalse(result)

    def test_legacy_wrapper_next_skips_queue(self) -> None:
        """next() forwards to inner mass.next_track()."""
        self.svc.mass.next_track = MagicMock()
        self.svc.next()
        self.svc.mass.next_track.assert_called_once()

    def test_legacy_wrapper_previous_skips_queue(self) -> None:
        """previous() forwards to inner mass.previous_track()."""
        self.svc.mass.previous_track = MagicMock()
        self.svc.previous()
        self.svc.mass.previous_track.assert_called_once()

    def test_legacy_wrapper_get_track_length_delegates(self) -> None:
        """get_track_length() delegates to inner mass.get_track_length()."""
        self.svc.mass.get_track_length = MagicMock(return_value=240000)
        self.assertEqual(self.svc.get_track_length(), 240000)

    def test_legacy_wrapper_get_track_position_delegates(self) -> None:
        """get_track_position() delegates to inner mass.get_track_position()."""
        self.svc.mass.get_track_position = MagicMock(return_value=60000)
        self.assertEqual(self.svc.get_track_position(), 60000)


# ---------------------------------------------------------------------------
# load_service factory tests
# ---------------------------------------------------------------------------

class TestLoadService(unittest.TestCase):
    """load_service() factory behaviour."""

    def test_load_service_matching_type(self) -> None:
        """load_service creates MAssAudioService for backends typed 'mass'."""
        base_config = {
            "backends": {
                "my_mass": {
                    "type": "mass",
                    "active": True,
                    "url": "http://localhost:8095",
                    "identifier": "test-player"
                }
            }
        }
        with patch("ovos_media_plugin_mass.media.SimpleHTTPMusicAssistantClient") as MockClient:
            MockClient.return_value.get_player_state.return_value = {
                "available": True, "player_type": "generic"
            }
            MockClient.return_value.get_active_queue.return_value = {"queue_id": "q1"}
            from ovos_media_plugin_mass.audio import load_service
            instances = load_service(base_config, FakeBus())
        self.assertEqual(len(instances), 1)
        from ovos_media_plugin_mass.audio import MAssAudioService
        self.assertIsInstance(instances[0], MAssAudioService)

    def test_load_service_warns_when_empty(self) -> None:
        """load_service logs a warning when no mass backends are configured."""
        from ovos_utils.log import LOG
        base_config = {"backends": {}}
        with patch.object(LOG, "warning") as mock_warn:
            from ovos_media_plugin_mass.audio import load_service
            instances = load_service(base_config, FakeBus())
        self.assertEqual(instances, [])
        mock_warn.assert_called_once()


if __name__ == "__main__":
    unittest.main()
