"""Regression tests for the four live-confirmed defects in the OpenVoiceOS
merge-matrix audit of ovos-media-plugin-mass:

1. ``handle_player_ping`` self-re-emitted "ovos.mass.ping" from inside its
   own handler -> unbounded busy loop (observed live: 17,333 HTTP calls in
   2.5 minutes, ~50% CPU). Replaced with an Event.wait poll thread.
2. ``py_music_assistant`` returns ``None`` for an absent player; using it as
   a dict raised ``TypeError``.
3. The legacy ``mycroft.plugin.audioservice`` entry point pointed at the
   ``MAssAudioService`` class instead of the ``audio`` module, so
   ``ovos-plugin-manager``'s ``setup_audio_service`` (which requires a
   MODULE exposing ``load_service``) silently returned ``None`` and the
   legacy stack never loaded.
4. ``autoconfigure.py`` marked every discovered player ``active: true``
   instead of only the chosen default, and crashed with ``EOFError`` on
   non-interactive stdin.
"""
import unittest
from unittest.mock import MagicMock, patch

from ovos_utils.fakebus import FakeBus

_BASE_CONFIG = {
    "url": "http://localhost:8095",
    "identifier": "test-player",
}


class TestPingIsNotABusyLoop(unittest.TestCase):
    """Defect 1: the ping handler must never re-emit its own trigger message."""

    def test_no_self_reemission_and_no_bus_subscription(self):
        from ovos_media_plugin_mass.media import MAssBaseService

        bus = FakeBus()
        emitted = []
        bus.emit = lambda message: emitted.append(message)

        with patch("ovos_media_plugin_mass.media.SimpleHTTPMusicAssistantClient") as MockClient, \
                patch.object(MAssBaseService, "_start_ping_loop"):
            client = MockClient.return_value
            client.get_player_state.return_value = {"available": True, "player_type": "dlna"}
            svc = MAssBaseService(_BASE_CONFIG.copy(), bus=bus)

        # the constructor must not have emitted anything onto the bus
        self.assertEqual(emitted, [])
        # there must be no lingering subscription that could self-retrigger
        self.assertNotIn("ovos.mass.ping", bus.ee.event_names())

    def test_poll_thread_uses_configurable_interval_and_no_bus_emit(self):
        from ovos_media_plugin_mass.media import MAssBaseService, DEFAULT_PLAYER_PING_INTERVAL

        bus = FakeBus()
        bus.emit = MagicMock()

        cfg = dict(_BASE_CONFIG, player_ping_interval=0.05)
        with patch("ovos_media_plugin_mass.media.SimpleHTTPMusicAssistantClient") as MockClient:
            client = MockClient.return_value
            client.get_player_state.return_value = {"available": True, "player_type": "dlna"}
            svc = MAssBaseService(cfg, bus=bus)
            try:
                self.assertEqual(svc._ping_interval, 0.05)
                self.assertTrue(svc._ping_thread.is_alive())
                # let the poll loop run a few cycles
                import time
                time.sleep(0.2)
                self.assertGreater(client.get_player_state.call_count, 1)
                # the poll mechanism itself never touches the bus
                bus.emit.assert_not_called()
            finally:
                svc.shutdown()

    def test_shutdown_stops_the_poll_thread(self):
        from ovos_media_plugin_mass.media import MAssBaseService

        bus = FakeBus()
        cfg = dict(_BASE_CONFIG, player_ping_interval=0.05)
        with patch("ovos_media_plugin_mass.media.SimpleHTTPMusicAssistantClient") as MockClient:
            client = MockClient.return_value
            client.get_player_state.return_value = {"available": True, "player_type": "dlna"}
            svc = MAssBaseService(cfg, bus=bus)

        thread = svc._ping_thread
        self.assertTrue(thread.is_alive())
        svc.shutdown()
        self.assertFalse(thread.is_alive())


class TestAbsentPlayerNoneGuard(unittest.TestCase):
    """Defect 2: get_player_state() returning None must not raise."""

    def test_none_state_treated_as_unavailable(self):
        from ovos_media_plugin_mass.media import MAssBaseService

        bus = FakeBus()
        with patch("ovos_media_plugin_mass.media.SimpleHTTPMusicAssistantClient") as MockClient, \
                patch.object(MAssBaseService, "_start_ping_loop"):
            client = MockClient.return_value
            client.get_player_state.return_value = None
            svc = MAssBaseService(_BASE_CONFIG.copy(), bus=bus)

        self.assertEqual(svc.player_state, {"available": False})
        # must not raise TypeError
        self.assertEqual(svc.supported_uris(), [])

    def test_refresh_after_player_disappears(self):
        from ovos_media_plugin_mass.media import MAssBaseService

        bus = FakeBus()
        with patch("ovos_media_plugin_mass.media.SimpleHTTPMusicAssistantClient") as MockClient, \
                patch.object(MAssBaseService, "_start_ping_loop"):
            client = MockClient.return_value
            client.get_player_state.return_value = {"available": True, "player_type": "dlna"}
            svc = MAssBaseService(_BASE_CONFIG.copy(), bus=bus)
            client.get_player_state.return_value = None
            svc.refresh_player_state()

        self.assertEqual(svc.player_state, {"available": False})
        self.assertEqual(svc.supported_uris(), [])


class TestLegacyEntrypointResolvesToModule(unittest.TestCase):
    """Defect 3: the audioservice entry point must resolve to a module
    exposing load_service, as ovos-plugin-manager's setup_audio_service
    requires."""

    def test_entry_point_target_has_load_service(self):
        import importlib.metadata as importlib_metadata

        eps = importlib_metadata.entry_points()
        try:
            group = eps.select(group="mycroft.plugin.audioservice")
        except AttributeError:  # py<3.10 dict-style API
            group = eps.get("mycroft.plugin.audioservice", [])
        matches = [ep for ep in group if ep.name == "ovos_mass"]
        self.assertTrue(matches, "ovos_mass audioservice entry point not registered")

        loaded = matches[0].load()
        self.assertTrue(hasattr(loaded, "load_service"),
                         "entry point must resolve to a module exposing load_service, "
                         "not a class")

    def test_find_audio_service_plugins_exposes_load_service(self):
        from ovos_plugin_manager.audio import find_audio_service_plugins

        plugins = find_audio_service_plugins()
        self.assertIn("ovos_mass", plugins)
        self.assertTrue(hasattr(plugins["ovos_mass"], "load_service"))


class TestAutoconfigureDefaultOnly(unittest.TestCase):
    """Defect 4: only the chosen default player gets active: true."""

    def _fake_player(self, name, provider, player_id):
        p = MagicMock()
        p.name = name
        p.provider = provider
        p.player_id = player_id
        return p

    def test_only_selected_player_is_active(self):
        from ovos_media_plugin_mass import autoconfigure

        players = [
            self._fake_player("Living Room", "dlna", "id-1"),
            self._fake_player("Kitchen", "dlna", "id-2"),
            self._fake_player("Office", "cast", "id-3"),
        ]

        fake_api = MagicMock()
        fake_api.get_players.return_value = players

        class FakeUserConfig(dict):
            def store(self):
                pass

        fake_cfg = FakeUserConfig()

        with patch.object(autoconfigure, "SimpleHTTPMusicAssistantClient", return_value=fake_api), \
                patch.object(autoconfigure, "MycroftUserConfig", return_value=fake_cfg), \
                patch("builtins.input", side_effect=AssertionError("should not prompt with --default")):
            import sys
            argv = ["ovos-mass-autoconfigure", "--url", "http://localhost:8095", "--default", "1"]
            with patch.object(sys, "argv", argv):
                autoconfigure.main()

        active_flags = {
            name: cfg["active"]
            for name, cfg in fake_cfg["media"]["audio_players"].items()
        }
        self.assertEqual(sum(active_flags.values()), 1,
                          "exactly one player must be active")
        kitchen_key = [k for k in active_flags if k.startswith("mass-Kitchen")][0]
        self.assertTrue(active_flags[kitchen_key])
        for k, v in active_flags.items():
            if k != kitchen_key:
                self.assertFalse(v)
        # legacy Audio backends section must only contain the default player
        self.assertEqual(len(fake_cfg["Audio"]["backends"]), 1)

    def test_select_default_non_interactive_raises_clear_error(self):
        from ovos_media_plugin_mass.autoconfigure import _select_default

        players = [MagicMock(player_id="id-1"), MagicMock(player_id="id-2")]
        with patch("sys.stdin.isatty", return_value=False):
            with self.assertRaises(SystemExit):
                _select_default(players, None)

    def test_select_default_by_index_arg(self):
        from ovos_media_plugin_mass.autoconfigure import _select_default

        players = [MagicMock(player_id="id-1"), MagicMock(player_id="id-2")]
        self.assertEqual(_select_default(players, "1"), 1)

    def test_select_default_by_player_id_arg(self):
        from ovos_media_plugin_mass.autoconfigure import _select_default

        players = [MagicMock(player_id="id-1"), MagicMock(player_id="id-2")]
        self.assertEqual(_select_default(players, "id-2"), 1)


if __name__ == "__main__":
    unittest.main()
