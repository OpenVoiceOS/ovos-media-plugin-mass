from ovos_plugin_manager.templates.audio import AudioBackend
from ovos_plugin_manager.templates.media import PlaybackEvent
from ovos_utils.log import LOG

from ovos_media_plugin_mass.media import MAssOCPAudioService


class MAssAudioService(AudioBackend):
    """
        MAss Audio backend - old style plugin for ovos-audio (not ovos-media)
    """

    def __init__(self, config, bus, name='mass'):
        super().__init__(config, bus, name)
        self.mass = MAssOCPAudioService(self.config, bus=self.bus)
        self._track_start_callback = None
        self.mass.bind_event_reporter(self._on_mass_event)

    def _on_mass_event(self, event, **data):
        """Adapt the inner MediaBackend's physical events to ovos-audio's
        legacy ``track_start_callback(uri_or_none)`` convention."""
        if self._track_start_callback is None:
            return
        if event == PlaybackEvent.TRACK_START:
            self._track_start_callback(data.get("uri"))
        elif event in (PlaybackEvent.END_OF_MEDIA, PlaybackEvent.STOPPED, PlaybackEvent.ERROR):
            self._track_start_callback(None)

    def set_track_start_callback(self, callback_func):
        self._track_start_callback = callback_func

    def supported_uris(self):
        return self.mass.supported_uris()

    def play(self, repeat=False):
        self.mass.play()

    def stop(self) -> bool:
        return self.mass.stop() or False

    def pause(self):
        self.mass.pause()

    def resume(self):
        self.mass.resume()

    def next(self):
        self.mass.next_track()

    def previous(self):
        self.mass.previous_track()

    def lower_volume(self):
        self.mass.lower_volume()

    def restore_volume(self):
        self.mass.restore_volume()

    def track_info(self):
        """ Extract info of current track. """
        return self.mass.meta

    def get_track_length(self) -> int:
        """
        getting the duration of the audio in milliseconds
        """
        # we only can estimate how much we already played as a minimum value
        return self.mass.get_track_length()

    def get_track_position(self) -> int:
        """
        get current position in milliseconds
        """
        return self.mass.get_track_position()

    def set_track_position(self, milliseconds: int) -> None:
        """Seek to an absolute position in milliseconds.

        Args:
            milliseconds: Target position in milliseconds from the start of
                the track.
        """
        self.mass.set_track_position(milliseconds)

    def seek_forward(self, seconds: float) -> None:
        """Seek forward by a relative number of seconds.

        Args:
            seconds: Number of seconds to seek forward.
        """
        current_ms = self.mass.get_track_position()
        self.mass.set_track_position(current_ms + int(seconds * 1000))

    def seek_backward(self, seconds: float) -> None:
        """Seek backward by a relative number of seconds.

        Args:
            seconds: Number of seconds to seek backward.
        """
        current_ms = max(self.mass.get_track_position(), 0)
        new_ms = max(current_ms - int(seconds * 1000), 0)
        self.mass.set_track_position(new_ms)


def load_service(base_config, bus):
    backends = base_config.get('backends', {})
    services = [(b, backends[b]) for b in backends
                if backends[b].get('type') in ['mass', 'ovos_mass'] and
                backends[b].get('active', True)]
    instances = [MAssAudioService(s[1], bus, s[0]) for s in services]
    if len(instances) == 0:
        LOG.warning("No MAss backends have been configured")
    return instances
