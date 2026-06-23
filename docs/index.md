# ovos-media-plugin-mass

A [Music Assistant](https://www.music-assistant.io/) **playback backend** for
OVOS. It controls a Music Assistant player over the server's HTTP API, playing
the `library://…` uris that the catalog layer resolves.

It ships two entry points so it works on both audio stacks:

| Stack | Entry point | Class |
|---|---|---|
| `ovos-media` (current) | `opm.media.audio` → `ovos-media-audio-plugin-mass` | `MAssOCPAudioService` |
| `ovos-audio` (legacy) | `mycroft.plugin.audioservice` → `ovos_mass` | `MAssAudioService` |

## Where it fits

```
provider.search ─▶ Release(uri="library://track/42")
                          │
                          ▼
          ovos-media daemon picks this backend
                          │
                          ▼
        MAssOCPAudioService.load_track(uri) ─▶ play on the Music Assistant player
```

The catalog/search half is the companion
[`ovos-media-provider-mass`](https://github.com/OpenVoiceOS/ovos-media-provider-mass)
(or, on the legacy stack, the
[`ovos-skill-music-assistant`](https://github.com/OpenVoiceOS/ovos-skill-music-assistant)
OCP skill). All three share the
[`py-music-assistant`](https://github.com/TigreGotico/py-music-assistant) HTTP
client.

## Install & configure

```bash
pip install ovos-media-plugin-mass
ovos-mass-autoconfigure        # scans your server and writes mycroft.conf
```

See:

- [architecture.md](architecture.md) — the class layers and playback flow
- [configuration.md](configuration.md) — config keys for both stacks
- [faq.md](faq.md) — common questions
