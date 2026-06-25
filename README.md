# ovos-media-plugin-mass

Music Assistant **playback backend** for OVOS. It controls
[Music Assistant](https://www.music-assistant.io/) players, playing the
`library://<type>/<id>` uris that the Music Assistant catalog returns.

It ships **one backend on both media stacks** — the same plugin works whether you
run the legacy `ovos-audio` service or the modern `ovos-media` service:

| Stack | Entry-point group | Class |
|---|---|---|
| `ovos-media` (current) | `opm.media.audio` | `MAssOCPAudioService` |
| `ovos-audio` (legacy) | `mycroft.plugin.audioservice` | `MAssAudioService` |

To **search** Music Assistant by voice you also need a catalog component:
[ovos-media-provider-mass](https://github.com/OpenVoiceOS/ovos-media-provider-mass)
on the `ovos-media` stack, or
[ovos-skill-music-assistant](https://github.com/OpenVoiceOS/ovos-skill-music-assistant)
on the legacy OCP/`ovos-audio` stack.

## Install

```bash
pip install ovos-media-plugin-mass
```

## Configuration

The easiest way is the bundled `ovos-mass-autoconfigure` command, which scans your
server and writes both the legacy and `ovos-media` player entries into
`mycroft.conf`:

```bash
$ ovos-mass-autoconfigure
This script will auto configure Music Assistant devices under your mycroft.conf
Make sure your Music Assistant server is accessible from this device
Please enter your Music Assistant server url: http://192.168.1.100:8095

Scanning...
    - Found player: HomeLabRenderer - dlna:uuid:4b778a71-0499-485a-a5a4-88140603fba9

mycroft.conf updated!
```

It emits configuration for both stacks:

```jsonc
// Legacy Audio Service:
{"backends": {"mass-HomeLabRenderer:dlna": {
    "active": true, "type": "ovos_mass", "player_type": "dlna",
    "identifier": "uuid:4b778a71-0499-485a-a5a4-88140603fba9",
    "url": "http://192.168.1.100:8095"}}}

// ovos-media Service:
{"audio_players": {"mass-HomeLabRenderer:dlna": {
    "active": true, "module": "ovos-media-audio-plugin-mass", "player_type": "dlna",
    "aliases": ["HomeLabRenderer", "Home Lab Renderer"],
    "identifier": "uuid:4b778a71-0499-485a-a5a4-88140603fba9",
    "url": "http://192.168.1.100:8095"}}}
```

See [docs/configuration.md](docs/configuration.md) for the field reference.

## Related projects

- [py-music-assistant](https://github.com/TigreGotico/py-music-assistant) — shared HTTP client + mediavocab bridge (this plugin's transport layer)
- [ovos-media-provider-mass](https://github.com/OpenVoiceOS/ovos-media-provider-mass) — Music Assistant MediaProvider (search, `ovos-media` stack)
- [ovos-skill-music-assistant](https://github.com/OpenVoiceOS/ovos-skill-music-assistant) — Music Assistant OCP search skill (legacy stack)
- [hivemind-homeassistant](https://github.com/JarbasHiveMind/hivemind-homeassistant) — expose OVOS as a player in Home Assistant

## Docs

- [docs/index.md](docs/index.md) — overview & how the two stacks fit together
- [docs/architecture.md](docs/architecture.md) — backends, uri resolution, playback flow
- [docs/configuration.md](docs/configuration.md) — configuration reference
- [docs/faq.md](docs/faq.md) — troubleshooting

## Tests

```bash
pip install -e .[test]
pytest test/                  # unit + end2end (ovoscope), network-free
```

The end-to-end tests ([test/end2end/](test/end2end/)) drive both backends through
a real `ovos-audio` `AudioService` on a `FakeBus` via `ovoscope`, with the Music
Assistant HTTP client mocked.

## License

Apache-2.0
