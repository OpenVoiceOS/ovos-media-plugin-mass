# Copyright 2025 OpenVoiceOS
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
"""End-to-end tests for ovos-media-plugin-mass (Music Assistant).

Uses AudioServiceHarness / AudioCaptureSession from ovoscope.audio to inject
MAssAudioService (legacy) and MAssOCPAudioService (OCP) backends into a real
ovos-audio AudioService instance backed by a FakeBus, then drives playback over
the bus and asserts the resulting client calls and message sequence.

Mocking strategy
----------------
- ``SimpleHTTPMusicAssistantClient`` is replaced with a MagicMock so no real HTTP
  calls are made to a Music Assistant server.
- ``_start_ping_loop`` is patched to a no-op on instantiation so the
  constructor does not spawn a background poll daemon during tests.
- ``player_state`` is then set to ``available=True`` so ``supported_uris()``
  advertises ``library`` and the AudioService can route the test track.
"""
import time
import unittest
from unittest.mock import MagicMock, patch

from ovos_utils.fakebus import FakeBus

from ovos_utils.ocp import MediaEntry, PlaybackType

from ovos_plugin_manager.templates.media import PlaybackEvent

from ovos_media_plugin_mass.audio import MAssAudioService
from ovos_media_plugin_mass.media import MAssOCPAudioService
from ovoscope.audio import AudioCaptureSession, AudioServiceHarness
from ovoscope.media import OCPPlayerHarness

_PLAYER_ID: str = "test-mass-player"
_TRACK_URI: str = "library://track/42"
_QUEUE_ID: str = "q-001"
_AVAILABLE: dict = {"available": True, "player_type": "cast"}
_CONFIG: dict = {
    "url": "http://localhost:8095",
    "identifier": _PLAYER_ID,
}


def _mock_mass_client() -> MagicMock:
    """Return a MagicMock SimpleHTTPMusicAssistantClient pre-configured for tests."""
    client = MagicMock()
    client.get_player_state.return_value = dict(_AVAILABLE)
    client.get_active_queue.return_value = {"queue_id": _QUEUE_ID}
    client.track_info.return_value = {
        "name": "Test Track",
        "external_ids": {},
        "duration": 180,
        "track_number": 1,
        "disc_number": 1,
        "artists": [{"name": "Test Artist"}],
        "album": {"name": "Test Album"},
    }
    return client


def _patch_mass_init(mock_client: MagicMock):
    """Return the context managers needed to safely construct a MAss backend.

    Patches out both SimpleHTTPMusicAssistantClient and the ping-loop starter
    (which would otherwise spawn a background poll daemon thread).
    """
    return (
        patch(
            "ovos_media_plugin_mass.media.SimpleHTTPMusicAssistantClient",
            return_value=mock_client,
        ),
        patch.object(
            MAssOCPAudioService,
            "_start_ping_loop",
            lambda self: None,  # no-op: avoid spawning a poll daemon
        ),
    )


class TestMAssLegacyAudioService(unittest.TestCase):
    """Tests for MAssAudioService (legacy ovos-audio backend)."""

    def _make_backend(self, bus: FakeBus) -> MAssAudioService:
        """Instantiate MAssAudioService with a mocked Music Assistant client."""
        mock_client = _mock_mass_client()
        patch1, patch2 = _patch_mass_init(mock_client)
        with patch1, patch2:
            backend = MAssAudioService(_CONFIG, bus, "mass-test")
        backend.mass.api = mock_client
        backend.mass.player_state = dict(_AVAILABLE)
        backend.mass._loaded_uri = _TRACK_URI
        return backend

    def test_legacy_play_through_audioservice(self) -> None:
        """Injecting MAssAudioService and calling play() must invoke the inner
        client's play_media with the correct queue_id and track URI.
        """
        with AudioServiceHarness() as h:
            backend = self._make_backend(h.bus)
            h.service.service = [backend]
            h.service.default = backend
            backend.set_track_start_callback(h.service.track_start)

            h.play([_TRACK_URI])
            time.sleep(0.05)

        backend.mass.api.play_media.assert_called_once_with(
            _QUEUE_ID, _TRACK_URI
        )

    def test_legacy_stop_returns_bool(self) -> None:
        """stop() must return a bool (True when was playing, False otherwise)."""
        with AudioServiceHarness() as h:
            backend = self._make_backend(h.bus)
            h.service.service = [backend]
            h.service.default = backend

            backend.mass.is_playing = True
            result = backend.stop()

        self.assertIsInstance(result, bool)
        self.assertTrue(result)

    def test_legacy_stop_returns_false_when_not_playing(self) -> None:
        """stop() must return False when the player was not active."""
        with AudioServiceHarness() as h:
            backend = self._make_backend(h.bus)
            h.service.service = [backend]
            h.service.default = backend

            backend.mass.is_playing = False
            result = backend.stop()

        self.assertIsInstance(result, bool)
        self.assertFalse(result)

    def test_legacy_volume_ducking(self) -> None:
        """lower_volume()/restore_volume() must issue the client volume commands."""
        backend = self._make_backend(FakeBus())
        backend.lower_volume()
        backend.restore_volume()
        backend.mass.api.player_command_volume_down.assert_called_once_with(_PLAYER_ID)
        backend.mass.api.player_command_volume_up.assert_called_once_with(_PLAYER_ID)

    def test_legacy_next_previous_use_queue_commands(self) -> None:
        """next()/previous() must issue Music Assistant queue commands."""
        with AudioServiceHarness() as h:
            backend = self._make_backend(h.bus)
            h.service.service = [backend]
            h.service.default = backend

            backend.next()
            backend.previous()

        backend.mass.api.queue_command_next.assert_called_once_with(_QUEUE_ID)
        backend.mass.api.queue_command_previous.assert_called_once_with(_QUEUE_ID)


class TestMAssOCPAudioService(unittest.TestCase):
    """Tests for MAssOCPAudioService (OCP / ovos-media backend)."""

    def _make_backend(self, bus: FakeBus) -> MAssOCPAudioService:
        """Instantiate MAssOCPAudioService with a mocked Music Assistant client."""
        mock_client = _mock_mass_client()
        patch1, patch2 = _patch_mass_init(mock_client)
        with patch1, patch2:
            backend = MAssOCPAudioService(_CONFIG, bus=bus)
        backend.api = mock_client
        backend.player_state = dict(_AVAILABLE)
        backend._loaded_uri = _TRACK_URI
        # ovos-audio's AudioService.shutdown() reads backend.name
        backend.name = "mass-test"
        return backend

    def test_ocp_play_invokes_client(self) -> None:
        """An OCP MediaBackend is driven by the ovos-media daemon, not ovos-audio,
        so play() is exercised directly: it must call the client's play_media
        with the active queue id and the loaded track URI.
        """
        backend = self._make_backend(FakeBus())
        backend.play()
        backend.api.play_media.assert_called_once_with(_QUEUE_ID, _TRACK_URI)

    def test_ocp_play_reports_track_start(self) -> None:
        """play() must report PlaybackEvent.TRACK_START for the loaded uri,
        with no ``ovos.common_play.*`` state emitted by the backend itself."""
        backend = self._make_backend(FakeBus())
        events = []
        backend.bind_event_reporter(lambda event, **data: events.append((event, data)))

        common_play_msgs = []
        backend.bus.on("ovos.common_play.media.state",
                        lambda msg: common_play_msgs.append(msg))
        backend.bus.on("ovos.common_play.player.state",
                        lambda msg: common_play_msgs.append(msg))

        backend.play()

        self.assertIn((PlaybackEvent.TRACK_START, {"uri": _TRACK_URI}), events)
        self.assertEqual(common_play_msgs, [])

    def test_audio_capture_sequence(self) -> None:
        """AudioCaptureSession must record mycroft.audio.service.play and
        mycroft.audio.service.stop in the correct order.

        The OCP backend reports physical events via ``bind_event_reporter``;
        this test adapts them to legacy ovos-audio's ``track_start`` callback
        so the AudioService state machine (and the bus messages it emits)
        drives forward exactly as it would under a real ovos-media daemon.
        """
        with AudioServiceHarness() as h:
            backend = self._make_backend(h.bus)
            h.service.service = [backend]
            h.service.default = backend

            def _report_to_track_start(event, **data):
                if event == PlaybackEvent.TRACK_START:
                    h.service.track_start(data.get("uri"))
                elif event in (PlaybackEvent.END_OF_MEDIA, PlaybackEvent.STOPPED,
                               PlaybackEvent.ERROR):
                    h.service.track_start(None)

            backend.bind_event_reporter(_report_to_track_start)

            with AudioCaptureSession(h.bus) as cap:
                h.play([_TRACK_URI])
                time.sleep(0.05)
                h.stop()
                time.sleep(0.05)

        cap.assert_sequence(
            "mycroft.audio.service.play",
            "mycroft.audio.service.stop",
        )


def _mass_backend_factory(bus: FakeBus) -> MAssOCPAudioService:
    """Build a MAssOCPAudioService (client mocked) for OCPPlayerHarness injection."""
    mock_client = _mock_mass_client()
    patch1, patch2 = _patch_mass_init(mock_client)
    with patch1, patch2:
        backend = MAssOCPAudioService(_CONFIG, bus=bus)
    backend.api = mock_client
    backend.player_state = dict(_AVAILABLE)
    backend.name = "mass-test"
    return backend


class TestMAssThroughOCPPlayer(unittest.TestCase):
    """Drive MAssOCPAudioService through the real OCPMediaPlayer via ovoscope.

    Unlike TestMAssOCPAudioService (which exercises the backend directly), this
    injects the real backend into OCPPlayerHarness with a `backend_factory`, so the
    player's full play -> load_track -> LOADED_MEDIA -> backend.play() path drives
    the Music Assistant client end-to-end.
    """

    @unittest.skip(
        "ovoscope's OCPPlayerHarness real-backend mode still calls "
        "set_track_start_callback() on the injected backend directly - a "
        "pre-v2-template MediaBackend API removed by the media-backend-v2 "
        "migration. Re-enable once ovoscope publishes a harness that drives "
        "v2 MediaBackend plugins via bind_event_reporter/report()."
    )
    def test_player_play_invokes_client(self) -> None:
        with OCPPlayerHarness(backend_factory=_mass_backend_factory) as h:
            h.play(MediaEntry(uri=_TRACK_URI, playback=PlaybackType.AUDIO))
            h.backend.api.track_info.assert_called_with(_TRACK_URI)
            h.backend.api.play_media.assert_called_once_with(_QUEUE_ID, _TRACK_URI)


if __name__ == "__main__":
    unittest.main()
