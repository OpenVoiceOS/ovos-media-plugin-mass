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

from ovos_plugin_manager.templates.media import MediaBackend, PlaybackEvent, RemoteAudioPlayerBackend
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

    can_seek = True
    can_pause = True

    def __init__(self, config, bus=None):
        super().__init__(config, bus)
        self.connection_attempts = 0
        self.bus = bus
        self.config = config

        if self.config is None or 'url' not in self.config:
            raise ValueError(
                "MAss server url not set! Set 'url' on this backend's config "
                "entry (media.audio_players.<name>.url on ovos-media, "
                "Audio.backends.<name>.url on legacy ovos-audio) - see "
                "docs/configuration.md, or run ovos-mass-autoconfigure."
            )
        else:
            self.url = self.config['url']

        if self.config is None or 'identifier' not in self.config:
            # Can't connect since no id is specified
            raise ValueError(
                "MAss identifier not set! Set 'identifier' (the target Music "
                "Assistant player_id) on this backend's config entry "
                "(media.audio_players.<name>.identifier on ovos-media, "
                "Audio.backends.<name>.identifier on legacy ovos-audio) - see "
                "docs/configuration.md, or run ovos-mass-autoconfigure."
            )
        else:
            self.player_id = self.config['identifier']

        self.api = SimpleHTTPMusicAssistantClient(self.url, token=self.config.get("token"))
        self.tracker = PlaybackTimestampTracker()
        self.is_playing = False
        self.meta: dict = {}
        self._loaded_uri = None
        # last Music Assistant reported state we already reacted to, so the
        # ping loop doesn't re-report a transition we already reported from
        # a locally-issued play()/pause()/resume()/stop() call
        self._last_ma_state = None
        # set by the ping loop when it can't reach MAss while a track is
        # playing; consumed (and cleared) by the play() watcher daemon so
        # report_track_end reports the error instead of a natural end
        self._pending_error = None

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
        ``None``. Also detects and reports playback state transitions that
        were made from outside this plugin (e.g. someone pausing/resuming
        the player from the Music Assistant UI directly).
        """
        state = self.api.get_player_state(self.player_id)
        self.player_state = state if state is not None else {"available": False}
        self._report_external_transition()

    def _report_external_transition(self) -> None:
        """Report PAUSED/RESUMED when MAss's reported state changes without
        this plugin having caused the change itself."""
        if not self.is_playing:
            return
        ma_state = (self.player_state or {}).get("state")
        if ma_state is None or ma_state == self._last_ma_state:
            return
        if ma_state == "paused" and self._last_ma_state != "paused":
            self.report(PlaybackEvent.PAUSED, uri=self._loaded_uri)
        elif ma_state == "playing" and self._last_ma_state == "paused":
            self.report(PlaybackEvent.RESUMED, uri=self._loaded_uri)
        self._last_ma_state = ma_state

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
                    if self.is_playing:
                        # can't reach the MAss server anymore while a track
                        # was playing - a network/MA failure genuinely ended
                        # it, not a natural end or a requested stop. Record
                        # the error and flip is_playing; the watcher daemon
                        # spawned by play() is the single site that calls
                        # report_track_end, so it picks this up on its next
                        # loop check instead of us reporting here too.
                        self._pending_error = e
                        self.is_playing = False

        self._ping_thread = create_daemon(_loop)

    def load_track(self, uri: str, metadata: dict | None = None) -> bool:
        """Load a track URI and populate metadata from the MAss API.

        Stores enriched metadata in ``self.meta`` so that ``track_info()``
        can return it without a second API call.

        Args:
            uri: MAss library URI or HTTP URL for the track.
            metadata: Optional seed metadata dict; enriched in-place.

        Returns:
            bool: True if the track metadata was fetched successfully.
        """
        try:
            track_info = self.api.track_info(uri) or {}
        except Exception as e:
            LOG.error(f"failed to load track '{uri}': {e}")
            self.report(PlaybackEvent.ERROR, error=str(e), uri=uri)
            return False
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
        self._loaded_uri = uri
        return True

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
        self._last_ma_state = "playing"
        try:
            self.api.play_media(self.active_queue["queue_id"], self._loaded_uri)
        except Exception as e:
            LOG.error(f"failed to start MAss playback: {e}")
            self.is_playing = False
            self.report(PlaybackEvent.ERROR, error=str(e), uri=self._loaded_uri)
            return
        self.tracker.start()
        self.report(PlaybackEvent.TRACK_START, uri=self._loaded_uri)

        uri = self._loaded_uri

        if self.tracker.duration > 0:

            def check_ended() -> None:
                """Daemon that watches for the end of this track and converges
                on the single ``report_track_end`` call site once playback is
                no longer happening - whether that is because the tracker
                reached the track's duration (natural end) or because
                ``_stop()``/an external error flipped ``is_playing`` to
                False in the meantime. ``report_track_end`` itself tells a
                requested stop apart from a natural end.
                """
                while self.is_playing:
                    time.sleep(0.1)
                    if self.is_playing and self.tracker.current_timestamp >= self.tracker.duration:
                        self.is_playing = False
                        break
                self.tracker.stop()
                self._last_ma_state = None
                error, self._pending_error = self._pending_error, None
                self.report_track_end(uri=uri, error=error)

            create_daemon(check_ended)
        else:
            # duration unknown (e.g. a live/radio stream, or the MAss API
            # didn't report one) - the timestamp-based check above can never
            # fire, so we would never detect a natural end. Fall back to
            # polling the player's reported state (refreshed by the ping
            # loop into self.player_state at player_ping_interval) and treat
            # idle/stopped - after we know playback actually started - as
            # playback no longer happening, converging on the same
            # ``report_track_end`` call site as ``check_ended`` above.
            def watch_player_state() -> None:
                while self.is_playing:
                    time.sleep(self._ping_interval)
                    if self.is_playing and (self.player_state or {}).get("state") in ("idle", "stopped"):
                        self.is_playing = False
                        break
                self.tracker.stop()
                self._last_ma_state = None
                error, self._pending_error = self._pending_error, None
                self.report_track_end(uri=uri, error=error)

            create_daemon(watch_player_state)

    def _stop(self) -> bool:
        """ Stop playback and quit app.

        Reports nothing itself - the watcher daemon spawned by ``play()``
        notices ``is_playing`` went False and converges on
        ``report_track_end`` (which reports STOPPED, since ``stop()``
        already recorded the explicit-stop flag before calling this).
        """
        if self.is_playing:
            self.is_playing = False
            self._last_ma_state = "idle"
            self.api.player_command_stop(self.player_id)
            return True
        else:
            return False

    def pause(self):
        """ Pause current playback. """
        self.api.queue_command_pause(self.active_queue["queue_id"])
        self.tracker.pause()
        self._last_ma_state = "paused"
        self.report(PlaybackEvent.PAUSED, uri=self._loaded_uri)

    def resume(self):
        self.api.queue_command_play(self.active_queue["queue_id"])
        self.tracker.resume()
        self._last_ma_state = "playing"
        self.report(PlaybackEvent.RESUMED, uri=self._loaded_uri)

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


class MAssOCPAudioService(RemoteAudioPlayerBackend, MAssBaseService):
    def __init__(self, config, bus=None):
        super().__init__(config, bus)
