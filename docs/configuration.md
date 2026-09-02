# Configuration

The fastest path is `ovos-mass-autoconfigure`, which scans your Music Assistant
server and writes one backend entry per player. The keys it sets:

| Key | Required | Meaning |
|---|---|---|
| `url` | yes | Music Assistant server base URL, e.g. `http://192.168.1.100:8095` |
| `token` | no | Music Assistant API token; required by MA 2.11+, create one in the MA web UI under Settings → Users. Also settable via the `MASS_TOKEN` environment variable |
| `identifier` | yes | the Music Assistant `player_id` to control |
| `player_type` | no | player provider hint (e.g. `dlna`, `cast`) |
| `aliases` | no | spoken names that map to this player |
| `force_enable_http` | no | also accept `http`/`https` stream uris |
| `force_enable_spotify` | no | also accept `spotify` uris |
| `active` | no | set `false` to disable this backend |

## ovos-media (current stack)

Backends live under `media.audio_players`, keyed by an arbitrary name:

```json
{
  "media": {
    "audio_players": {
      "living-room-mass": {
        "module": "ovos-media-audio-plugin-mass",
        "url": "http://192.168.1.100:8095",
        "identifier": "ma_3sqpjlp25u",
        "aliases": ["living room", "downstairs"],
        "active": true
      }
    }
  }
}
```

## ovos-audio (legacy stack)

Backends live under `Audio.backends`, with `type` set to `ovos_mass` (or `mass`):

```json
{
  "Audio": {
    "backends": {
      "living-room-mass": {
        "type": "ovos_mass",
        "url": "http://192.168.1.100:8095",
        "identifier": "ma_3sqpjlp25u",
        "active": true
      }
    }
  }
}
```

## Pairing with search

This plugin only plays uris. Catalog/search is provided by
[`ovos-media-provider-mass`](https://github.com/OpenVoiceOS/ovos-media-provider-mass)
on the `ovos-media` stack (configured under `media_providers.music_assistant`
with the same `url`), or by `ovos-skill-music-assistant` on the legacy stack.

---
[← Architecture](architecture.md) · [Home](index.md) · [FAQ →](faq.md)
