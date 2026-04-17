# Local-track album art for the AirPlay bridge

## Problem

`extras/airplay-bridge/mpd_owntone_metadata.py` translates MPD track changes into shairport-sync metadata frames for OwnTone, which forwards them to AirPlay receivers. Currently only YouTube-proxy tracks get a PICT frame (via `hqdefault.jpg` from `img.youtube.com`). For local tracks, no PICT is emitted, and the AirPlay receiver keeps displaying whatever art arrived last — typically the thumbnail from the previous YouTube song.

The user does not care about the stale-art visual; they only want album art to appear for local tracks when it can be found, with zero tolerance for blocking the metadata loop.

## Goals

1. Fetch album art for local tracks from progressively more expensive sources.
2. Never block the MPD idle → metadata-emit path on art lookup.
3. Cache online lookups aggressively (positive and negative) to stay polite to free services and keep subsequent plays instant.
4. Leave the YouTube-proxy path, ICY-stream path, and OwnTone metadata-frame encoding unchanged.

## Non-goals

- Evicting stale art on the receiver (user explicitly doesn't care).
- Handling ICY-stream art lookups. Stream metadata is `Title: "Artist - Track"` without a separate album field, so online lookup would be unreliable; out of scope.
- Unit tests for this module. `extras/airplay-bridge/` has no existing tests; keep that pattern. Verification is manual (play local track, confirm art on Denon).
- Configurable resolver order. Hardcoded chain is fine for a personal-use daemon.

## Research summary (April 2026)

| Service | Key | Rate limit | Verdict |
|---|---|---|---|
| iTunes Search API | none | ~20 req/min/IP | **Use.** Returns `artworkUrl100` which upgrades to `600x600bb`. |
| MusicBrainz + Cover Art Archive | none | MB: 1 req/sec; CAA: none | **Use.** Best long-tail / indie coverage. |
| Last.fm | key required | n/a | **Skip.** Known album-art delivery regressions through Feb 2026. |
| Deezer | none (public endpoints) | n/a | **Skip.** FAQ forbids storing returned images, which precludes our disk cache. |

## Architecture

### Resolver chain

For local file URIs (no `://` prefix), in order:

1. MPD `readpicture` — embedded ID3/FLAC art.
2. MPD `albumart` — folder cover.jpg/cover.png alongside the file.
3. iTunes Search API — `artist + album`, upgrade to 600x600, fetch JPEG.
4. MusicBrainz release search → Cover Art Archive `front-500` — fetch JPEG.
5. Return `None`. No PICT frame emitted.

Resolvers 3-4 require non-empty `Artist` (or `AlbumArtist`) and `Album` tags; if either is missing, skip online lookup.

### Two-phase emission (async art fetch)

The main `metadata_loop` thread must never wait on art resolution.

- On each track change:
  1. Emit the text-only MDST/MDEN block immediately (artist, title, album, track-id). No PICT.
  2. Hand the song dict to a **single-slot request box** for the art worker. Writing to the box replaces any pending older request; rapid track-skipping cannot pile up stale fetches.
- A dedicated **art worker thread** blocks on the box.
  - On wakeup: record the song's track-key (file URI + Id), run the resolver chain, and on success emit a second MDST/MDEN block with the full text fields + PICT. On None, do nothing.
  - Before emitting, compare the track-key to `last_song_key` in the main loop (exposed via shared state under the same write lock). Drop the result if the user already moved on.

Two full blocks (rather than a PICT-only frame) keeps OwnTone's shairport-sync pipe reader happy — every field round-trips naturally, and there's no flicker because the text payload is identical.

YouTube proxy path keeps its existing inline cache-hit fast path (cache read is a local `Path.read_bytes()`). Cache misses on YouTube also go through the worker — simplifies control flow and removes any lingering blocking calls.

### Caching

`~/.cache/mpd-owntone-metadata/` already exists for the YouTube thumbnails. Adds:

- `albums/<sha1(artist|album).hex>.jpg` — positive cache for online lookups.
- `albums/<sha1(artist|album).hex>.miss` — empty negative-cache marker. TTL: 30 days (mtime-based). Expired markers are re-resolved.

Keys are hashed to avoid filename-safety issues with Unicode/special-char artist/album strings. MPD-local results are not cached on disk — MPD's binary commands over a local socket are cheap enough to re-run per track change.

### MPD binary protocol

MPD's `readpicture` and `albumart` commands return chunked binary:

```
size: N
type: image/jpeg      (optional)
binary: M
<M bytes>
OK
```

Client repeats the command with `<offset>` until `offset + M == size`. Implementation: open a short-lived TCP connection per lookup (the main client is stuck in `idle`), write bytes into a `bytearray`, and return the accumulated bytes. ~40 lines.

### Configuration

- Env var `YTMPD_AIRPLAY_NO_ONLINE_ART=1` disables resolvers 3 and 4 (keeps MPD-local). Default: online enabled.
- Module-level constant `NEG_CACHE_TTL_SEC = 30 * 24 * 3600`.
- Module-level constant `ART_HTTP_USER_AGENT = "ytmpd-airplay-bridge/1.0"` — required by MusicBrainz, polite everywhere.

### Error handling

- All HTTP calls wrapped in broad `except Exception` → log at `warning`, return None. Existing pattern in `fetch_album_art`.
- MPD binary commands: on any socket/parse error, return None and let the next resolver try.
- Worker thread is never killed by a failed lookup; the `except` clause loops back to `wait for next box item`.

### Shutdown

Existing SIGTERM/SIGINT handlers `sys.exit(0)` — worker thread is a daemon thread, dies with the process. No explicit shutdown needed.

## File impact

Single file: `extras/airplay-bridge/mpd_owntone_metadata.py`.

Internal refactor:

- `fetch_album_art` becomes a thin dispatcher over a list of resolver callables.
- New private helpers: `_resolve_yt_proxy`, `_resolve_mpd_readpicture`, `_resolve_mpd_albumart`, `_resolve_itunes`, `_resolve_musicbrainz`, `_online_cache_get/put/miss`.
- New `ArtWorker` class encapsulating the request slot, condition variable, and worker thread.
- `metadata_loop` emits the text block first, then `art_worker.request(song)`.
- `ArtWorker.run` emits the art block under the shared write lock, guarded by a track-key check.

Shared state between main loop and worker:

- `write_lock` (existing) — serializes pipe writes.
- `current_track_key` (new, protected by `write_lock`) — tuple of `(song["file"], song["Id"])`, the same key already tracked by `metadata_loop`. Main loop updates it immediately before emitting the text block; worker reads it under `write_lock` just before emitting, and bails if the key changed.

## Testing / verification

Manual, on the user's hardware:

1. Play a well-tagged local FLAC with embedded art → art appears within a second on Denon.
2. Play a local file with only a folder `cover.jpg` → same.
3. Play a local file with no embedded or folder art, but a findable album (e.g. a popular album) → text metadata appears immediately; art appears after 1-3s.
4. Play a local file with an obscure album → text metadata appears immediately; no art appears; log shows iTunes + MB misses; second play returns fast (negative cache hit).
5. Rapid-skip through 5 tracks → no stale art fetches accumulate; only the last track's art lookup runs to completion.
6. Set `YTMPD_AIRPLAY_NO_ONLINE_ART=1`, restart, play a local file with no embedded/folder art → no network traffic; text-only metadata.

## Branch & delivery

- Branch `feature/local-album-art` off `main`.
- Single commit on the feature branch (or two — refactor + feature — writer's judgment at plan time).
- Merge back to `main` with `--no-ff`.
