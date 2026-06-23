# FAQ

## What is Music Assistant?

[Music Assistant](https://www.music-assistant.io/) is a self-hosted music library
and playback server. This plugin drives one of its players over the server's HTTP
API.

## Which uri schemes does it play?

`library://…` uris (Music Assistant library references) when the player is
available. `force_enable_http` and `force_enable_spotify` config flags add
`http`/`https` and `spotify` schemes for players that can handle them directly.

## `supported_uris()` returns an empty list — why?

The player reports as unavailable: the server did not return a healthy state for
the configured `identifier`. Check that the server is running and that `url` and
`identifier` are correct.

## How is track position tracked?

Via a local soft-clock (`PlaybackTimestampTracker`) that accumulates elapsed time,
since this HTTP API does not push live position. Position is therefore an estimate.

## Can it skip tracks?

Yes — `next_track()` / `previous_track()` (and the legacy `next()` / `previous()`)
issue Music Assistant queue commands.

## How do I configure multiple players?

Add one backend entry per player, each with a unique `identifier` matching its
Music Assistant `player_id`. See [configuration.md](configuration.md).

## What does `track_info()` return?

The metadata captured during the last `load_track()`: keys may include `name`,
`artist`, `album`, `duration`, `uri`, `track_number`, `disc_number` and
`external_ids`. It returns `{}` before any track is loaded.
