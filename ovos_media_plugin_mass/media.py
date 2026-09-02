# Copyright 2025 Tigre Gótico Lda.
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
#
import threading
import time

from ovos_plugin_manager.templates.media import MediaBackend, RemoteAudioPlayerBackend
from ovos_utils import create_daemon
from ovos_utils.log import LOG

from py_music_assistant import SimpleHTTPMusicAssistantClient

# config key controlling how often the player state is polled, in seconds
PLAYER_PING_INTERVAL_CONF_KEY = "player_ping_interval"
DEFAULT_PLAYER_PING_INTERVAL = 5


class PlaybackTimestampTracker:
    """helper to approximately track current track timestamp for players that don't report it"""

    def __init__(self, duration=-1):
        self.accumulator = 0
        self.start_ts = 0
        self.recording = False
        self.duration = duration

    def start(self):
        self.start_ts = time.time()
        self.accumulator = 0
        self.recording = True

    def seek(self, position: int):
        self.accumulator = position
        self.start_ts = time.time()

    def resume(self):
        self.start_ts = time.time()
        self.recording = True

    def pause(self):
        if self.recording:
            self.accumulator += time.time() - self.start_ts
            self.start_ts = 0
            self.recording = False

    def stop(self):
        self.accumulator = 0
        self.start_ts = 0
        self.recording = False

    @property
    def accumulated_time(self):
        if self.start_ts == 0:
            return self.accumulator
        return self.accumulator + time.time() - self.start_ts

    @property
    def current_timestamp(self) -> float:
        """Return the current playback position in seconds, capped at track duration.

        Returns -1 when the tracker has never been started.
        """
        if not self.recording and not self.accumulator:
            return -1
        ts = self.accumulated_time
        if self.duration > 0:
            ts = min(ts, self.duration)
        return ts


class MAssBaseService(MediaBackend):
    """
        Backend for playback on a specific music assistant player
    """

    def __init__(self, config, bus=None):
        super().__init__(config, bus)
        self.connection_attempts = 0
        self.bus = bus
        self.config = config

        if self.config is None or 'url' not in self.config:
            raise ValueError("MAss server url not set!")
        else:
            self.url = self.config['url']

        if self.config is None or 'identifier' not in self.config:
            raise ValueError("MAss identifier not set!")  # Can't connect since no id is specified
        else:
            self.player_id = self.config['identifier']

        self.api = SimpleHTTPMusicAssistantClient(self.url, token=self.config.get("token"))
        self.tracker = PlaybackTimestampTracker()
        self.is_playing = False
        self.meta: dict = {}

        # player availability check
        self.player_state = {"available": False}
        self._ping_interval = self.config.get(PLAYER_PING_INTERVAL_CONF_KEY,
                                                DEFAULT_PLAYER_PING_INTERVAL)
        self._ping_stop_event = threading.Event()
        self._ping_thread = None
        self.refresh_player_state()
        self._start_ping_loop()

    def refresh_player_state(self) -> None:
        """Fetch the current player state from the MAss API.

        A player that is no longer reachable/known to the server is
        reported as unavailable instead of leaving ``player_state`` as
        ``None``.
        """
        state = self.api.get_player_state(self.player_id)
        self.player_state = state if state is not None else {"available": False}

    def _start_ping_loop(self) -> None:
        """Start the background thread that periodically refreshes player state.

        Uses ``Event.wait`` (not bus self-emission) so the poll interval is
        configurable via ``player_ping_interval`` (seconds, default 5) and
        stops promptly when ``shutdown()`` sets the stop event.
        """
        if self._ping_thread is not None:
            return

        def _loop() -> None:
            while not self._ping_stop_event.wait(self._ping_interval):
                try:
                    self.refresh_player_state()
                except Exception as e:
                    LOG.warning(f"failed to refresh MAss player state: {e}")

        self._ping_thread = create_daemon(_loop)

    def load_track(self, uri: str, metadata: dict | None = None) -> None:
        """Load a track URI and populate metadata from the MAss API.

        Stores enriched metadata in ``self.meta`` so that ``track_info()``
        can return it without a second API call.

        Args:
            uri: MAss library URI or HTTP URL for the track.
            metadata: Optional seed metadata dict; enriched in-place.
        """
        track_info = self.api.track_info(uri) or {}
        koi = ['name', 'external_ids', 'duration', 'track_number', 'disc_number']
        metadata = metadata or {}
        for k in koi:
            if k in track_info:
                metadata[k] = track_info[k]
        # None-guard: a track may have no artists/album, or an artist with no name
        artists = track_info.get('artists') or []
        if artists and isinstance(artists[0], dict) and artists[0].get('name'):
            metadata["artist"] = artists[0]['name']
        album = track_info.get('album')
        if isinstance(album, dict) and album.get('name'):
            metadata["album"] = album['name']
        metadata['uri'] = uri
        if metadata.get("duration"):
            self.tracker.duration = metadata["duration"]
        self.meta = metadata
        super().load_track(uri, metadata)

    def supported_uris(self):
        """ Return supported uris of mass. """
        if not (self.player_state or {}).get("available"):
            return []
        uris = ["library"]
        if self.config.get("force_enable_http") or self.player_state["player_type"] in []:  # TODO - which player types support http streams?
            uris += ["http", "https"]
        # TODO how to detect for spotify support?
        # MA allows to turn any player into a spotify player
        if self.config.get("force_enable_spotify"):
            uris += ["spotify"]
        return uris

    @property
    def active_queue(self):
        return self.api.get_active_queue(self.player_id)

    def play(self, repeat=False):
        """ Start playback."""
        self.is_playing = True
        self.api.play_media(self.active_queue["queue_id"], self._now_playing)
        self.tracker.start()

        # track start/end callbacks
        if self._track_start_callback:  # optimistic, we dont have a callback from MA
            self._track_start_callback(self._now_playing)

        if self.tracker.duration > 0:

            def check_ended() -> None:
                """Daemon that reports natural end-of-media once duration is reached.

                Guards against firing after an explicit ``stop()`` call by
                checking ``self.is_playing`` before invoking the callback.
                """
                while self.is_playing:
                    time.sleep(0.1)
                    if self.is_playing and self.tracker.current_timestamp >= self.tracker.duration:
                        if self._track_start_callback:
                            self._track_start_callback(None)
                        # natural end-of-media (duration reached, no stop()
                        # requested by us) - ocp_stop() is idempotent
                        # (no-ops once self._now_playing is None), so it is
                        # safe to call here even if a stop() races us
                        self.ocp_stop()
                        break

            create_daemon(check_ended)
        else:
            # duration unknown (e.g. a live/radio stream, or the MAss API
            # didn't report one) - the timestamp-based check above can never
            # fire, so we would never detect a natural end. Fall back to
            # polling the player's reported state (refreshed by the ping
            # loop into self.player_state at player_ping_interval) and treat
            # idle/stopped - after we know playback actually started - as a
            # natural end.
            def watch_player_state() -> None:
                while self.is_playing:
                    time.sleep(self._ping_interval)
                    if self.is_playing and (self.player_state or {}).get("state") in ("idle", "stopped"):
                        if self._track_start_callback:
                            self._track_start_callback(None)
                        self.ocp_stop()
                        break

            create_daemon(watch_player_state)

    def stop(self):
        """ Stop playback and quit app. """
        if self.is_playing:
            self.is_playing = False
            self.api.player_command_stop(self.player_id)
            self.tracker.stop()
            return True
        else:
            return False

    def pause(self):
        """ Pause current playback. """
        self.api.queue_command_pause(self.active_queue["queue_id"])
        self.tracker.pause()

    def resume(self):
        self.api.queue_command_play(self.active_queue["queue_id"])
        self.tracker.resume()

    def next_track(self):
        """Skip to the next track in the Music Assistant queue."""
        self.api.queue_command_next(self.active_queue["queue_id"])
        self.tracker.start()

    def previous_track(self):
        """Return to the previous track in the Music Assistant queue."""
        self.api.queue_command_previous(self.active_queue["queue_id"])
        self.tracker.start()

    def lower_volume(self):
        self.api.player_command_volume_down(self.player_id)

    def restore_volume(self):
        self.api.player_command_volume_up(self.player_id)

    def shutdown(self):
        """ Disconnect from the device and stop the player-state poll thread. """
        self._ping_stop_event.set()
        if self._ping_thread is not None:
            self._ping_thread.join(timeout=self._ping_interval + 1)
            self._ping_thread = None
        self.stop()

    def get_track_length(self):
        """
        getting the duration of the audio in milliseconds
        """
        return (self.tracker.duration or self.tracker.current_timestamp) * 1000

    def get_track_position(self):
        """
        get current position in milliseconds
        """
        ts = self.tracker.current_timestamp
        return ts * 1000  # calculate approximate

    def set_track_position(self, milliseconds: int) -> None:
        """Seek to an absolute position in the current track.

        Args:
            milliseconds: Target position in milliseconds from the start of
                the track.
        """
        seconds = int(milliseconds / 1000)
        self.api.player_command_seek(self.player_id, seconds)
        self.tracker.seek(seconds)

    def track_info(self) -> dict:
        """Return metadata for the currently loaded track.

        Metadata is populated during :meth:`load_track` from the MAss API.
        Returns an empty dict when no track has been loaded yet.

        Returns:
            dict: Track metadata keys may include ``name``, ``artist``,
                ``album``, ``duration``, ``uri``, ``track_number``,
                ``disc_number``, and ``external_ids``.
        """
        return getattr(self, "meta", {})

    def seek_forward(self, seconds: float) -> None:
        """Seek forward by a relative number of seconds.

        Computes the new absolute position from the current tracker timestamp,
        clamps it to the track duration, then issues a MAss seek command and
        updates the local tracker.

        Args:
            seconds: Number of seconds to seek forward.
        """
        current = max(self.tracker.current_timestamp, 0)
        new_position = current + seconds
        if self.tracker.duration > 0:
            new_position = min(new_position, self.tracker.duration)
        new_position = int(new_position)
        self.api.player_command_seek(self.player_id, new_position)
        self.tracker.seek(new_position)

    def seek_backward(self, seconds: float) -> None:
        """Seek backward by a relative number of seconds.

        Computes the new absolute position from the current tracker timestamp,
        clamps it to zero, then issues a MAss seek command and updates the
        local tracker.

        Args:
            seconds: Number of seconds to seek backward.
        """
        current = max(self.tracker.current_timestamp, 0)
        new_position = max(current - seconds, 0)
        new_position = int(new_position)
        self.api.player_command_seek(self.player_id, new_position)
        self.tracker.seek(new_position)


class MAssOCPAudioService(RemoteAudioPlayerBackend, MAssBaseService):
    def __init__(self, config, bus=None):
        super().__init__(config, bus)
