# ovos-media-plugin-mass

Music Assistant plugin for [ovos-audio](https://github.com/OpenVoiceOS/ovos-audio) and [ovos-media](https://github.com/OpenVoiceOS/ovos-media)

For searching MA by voice you also need the companion [ovos-skill-music-assistant](https://github.com/HiveMindInsiders/ovos-skill-music-assistant)

## Install

`pip install ovos-media-plugin-mass`

## Configuration

The easiest way is to use the provided `ovos-mass-autoconfigure` command

```bash
$ ovos-mass-autoconfigure
This script will auto configure Music Assistant devices under your mycroft.conf
Make sure your Music Assistant server is accessible from this device
Please enter your Music Assistant server url: http://100.88.41.41:8095

Scanning...
    - Found player: HomeLabRenderer - dlna:uuid:4b778a71-0499-485a-a5a4-88140603fba9

mycroft.conf updated!

# Legacy Audio Service:
{'backends': {'mass-HomeLabRenderer:dlna': {'active': True,
                                            'identifier': 'uuid:4b778a71-0499-485a-a5a4-88140603fba9',
                                            'player_type': 'dlna',
                                            'type': 'ovos_mass',
                                            'url': 'http://100.88.41.41:8095'}}}

# ovos-media Service:
{'audio_players': {'mass-HomeLabRenderer:dlna': {'active': True,
                                                 'aliases': ['HomeLabRenderer',
                                                             'Home Lab '
                                                             'Renderer'],
                                                 'identifier': 'uuid:4b778a71-0499-485a-a5a4-88140603fba9',
                                                 'module': 'ovos-media-audio-plugin-mass',
                                                 'player_type': 'dlna',
                                                 'url': 'http://100.88.41.41:8095'}}}
```
