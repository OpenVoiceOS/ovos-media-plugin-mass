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

from ovos_bus_client.message import Message
from ovos_plugin_manager.templates.media import MediaBackend, RemoteAudioPlayerBackend
from ovos_utils import create_daemon

from ovos_media_plugin_mass.music_assistant_client import SimpleHTTPMusicAssistantClient


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
    def current_timestamp(self):
        if not self.recording and not self.accumulator:
            return -1
        ts = self.accumulated_time
        if self.duration > 0:
            ts = max(ts, self.duration)
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

        self.api = SimpleHTTPMusicAssistantClient(self.url)
        self.tracker = PlaybackTimestampTracker()
        self.is_playing = False

        # player availability check
        self.bus.on("ovos.mass.ping", self.handle_player_ping)
        self.player_state = {"available": False}
        self.handle_player_ping(Message("ovos.mass.ping"))

    def handle_player_ping(self, message):
        self.player_state = self.api.get_player_state(self.player_id)
        threading.Event().wait(20)
        self.bus.emit(message)

    def load_track(self, uri, metadata: dict = None):
        track_info = self.api.track_info(uri)
        koi = ['name', 'external_ids', 'duration', 'track_number', 'disc_number']
        metadata = metadata or {}
        for k in koi:
            if k in track_info:
                metadata[k] = track_info[k]
        if track_info['artists']:
            metadata["artist"] = track_info['artists'][0]['name']
        if track_info['album']:
            metadata["album"] = track_info['album']['name']
        metadata['uri'] = uri
        if metadata["duration"]:
            self.tracker.duration = metadata["duration"]
        super().load_track(uri, metadata)

    def supported_uris(self):
        """ Return supported uris of mass. """
        if not self.player_state["available"]:
            return []
        uris = ["library"]
        if self.player_state["player_type"] in []:  # TODO - which player types support http streams?
            uris += ["http", "https"]
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

        if self.tracker.duration > 0 and self._track_start_callback:

            def check_ended():
                while self.is_playing:
                    time.sleep(0.1)
                    if self.tracker.current_timestamp >= self.tracker.duration:
                        self._track_start_callback(None)

            create_daemon(check_ended)

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

    def lower_volume(self):
        self.api.player_command_volume_down(self.player_id)

    def restore_volume(self):
        self.api.player_command_volume_up(self.player_id)

    def shutdown(self):
        """ Disconnect from the device. """
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

    def set_track_position(self, milliseconds):
        """
        go to position in milliseconds

          Args:
                milliseconds (int): number of milliseconds of final position
        """
        seconds = int(milliseconds / 1000)
        self.api.player_command_seek(self.player_id, seconds)
        self.tracker.seek(seconds)


class MAssOCPAudioService(RemoteAudioPlayerBackend, MAssBaseService):
    def __init__(self, config, bus=None):
        super().__init__(config, bus)
