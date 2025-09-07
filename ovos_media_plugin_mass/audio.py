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

    def stop(self):
        self.mass.stop()

    def pause(self):
        self.mass.pause()

    def resume(self):
        self.mass.resume()

    def next(self):
        LOG.error("MAss does not support 'next'")

    def previous(self):
        LOG.error("MAss does not support 'previous'")

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

    def set_track_position(self, milliseconds):
        """
        go to position in milliseconds
          Args:
                milliseconds (int): number of milliseconds of final position
        """
        self.mass.set_track_position(milliseconds)


def load_service(base_config, bus):
    backends = base_config.get('backends', {})
    services = [(b, backends[b]) for b in backends
                if backends[b].get('type') in ['mass', 'ovos_mass'] and
                backends[b].get('active', True)]
    instances = [MAssAudioService(s[1], bus, s[0]) for s in services]
    if len(instances) == 0:
        LOG.warning("No MAss backends have been configured")
    return instances
