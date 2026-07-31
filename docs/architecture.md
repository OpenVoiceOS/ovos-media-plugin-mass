# Architecture

The plugin is layered so a single implementation serves both the modern
`ovos-media` stack and the legacy `ovos-audio` stack.

| Layer | Class | Base | Role |
|---|---|---|---|
| OCP backend | `MAssOCPAudioService` | `RemoteAudioPlayerBackend` + `MAssBaseService` | `opm.media.audio` entry point for `ovos-media` |
| Legacy backend | `MAssAudioService` | `AudioBackend` | `mycroft.plugin.audioservice` wrapper that delegates to an inner `MAssOCPAudioService` |
| Core | `MAssBaseService` | `MediaBackend` | all playback logic (load/play/stop/pause/seek/volume/queue) |
| Timing | `PlaybackTimestampTracker` | n/a | local soft-clock estimating track position without polling the server |

`MAssBaseService` holds a `SimpleHTTPMusicAssistantClient` (from
`py-music-assistant`) as `self.api` and a player `identifier` from config.

## Playback flow

1. `load_track(uri)` resolves metadata via `api.track_info(uri)` and stores it in
   `self.meta` (None-guarded against items with no artist/album).
2. `play()` sends `api.play_media(queue_id, uri)` and starts the tracker.
3. `pause()`/`resume()`/`stop()`/`next_track()`/`previous_track()` map to the
   matching `player_queues/*` and `players/cmd/*` commands and keep the local
   tracker in sync.
4. `seek_forward`/`seek_backward`/`set_track_position` issue `players/cmd/seek`
   and re-anchor the tracker.

## Position tracking

Music Assistant does not push live position over this HTTP API, so
`PlaybackTimestampTracker` accumulates elapsed wall-clock time (capped at the
track duration). `get_track_position()` / `get_track_length()` report it in
milliseconds. Position is therefore an estimate, not a server-reported value.

## Supported uris

`supported_uris()` returns `["library"]` when the player reports available.
`force_enable_http` / `force_enable_spotify` config flags add `http`/`https` and
`spotify` schemes for servers/players that can play them directly.

---
[Home](index.md) · [Configuration →](configuration.md)
