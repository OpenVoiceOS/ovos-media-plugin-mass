from ovos_plugin_manager.templates.audio import AudioBackend
from ovos_utils.log import LOG

from ovos_media_plugin_mass.media import MAssOCPAudioService


class MAssAudioService(AudioBackend):
    """
        MAss Audio backend - old style plugin for ovos-audio (not ovos-media)
    """

    def __init__(self, config, bus, name='mass'):
        super().__init__(config, bus, name)
        self.mass = MAssOCPAudioService(self.config, bus=self.bus)

    def set_track_start_callback(self, callback_func):
        self.mass.set_track_start_callback(callback_func)

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

        Delegates to :meth:`MAssBaseService.seek_forward`.

        Args:
            seconds: Number of seconds to seek forward.
        """
        self.mass.seek_forward(seconds)

    def seek_backward(self, seconds: float) -> None:
        """Seek backward by a relative number of seconds.

        Delegates to :meth:`MAssBaseService.seek_backward`.

        Args:
            seconds: Number of seconds to seek backward.
        """
        self.mass.seek_backward(seconds)


def load_service(base_config, bus):
    backends = base_config.get('backends', {})
    services = [(b, backends[b]) for b in backends
                if backends[b].get('type') in ['mass', 'ovos_mass'] and
                backends[b].get('active', True)]
    instances = [MAssAudioService(s[1], bus, s[0]) for s in services]
    if len(instances) == 0:
        LOG.warning("No MAss backends have been configured")
    return instances
