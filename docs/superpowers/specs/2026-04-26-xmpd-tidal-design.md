# xmpd: multi-source music daemon (rebrand of ytmpd + Tidal integration)

**Date:** 2026-04-26
**Status:** Design approved; ready for implementation planning.
**Successor to:** `ytmpd` (single-source YouTube Music daemon at `tuncenator/ytmpd`)
**Audience:** the implementing AI executing this spec, plus the human reviewer.

## Background

`ytmpd` is a personal music daemon that syncs YouTube Music playlists into MPD, exposing standard MPD tooling (`mpc`, `ncmpcpp`, mobile clients, i3 keybinds, AirPlay via the optional `extras/airplay-bridge/`) for a YouTube Music library. Architecturally it is YouTube-Music-shaped throughout: the package, CLI, Python module names, config dir, track-store schema, stream resolver (yt-dlp), proxy URL pattern, history reporter, rating module, and search/radio entry points all assume a single source.

The user has subscribed to Tidal HiFi and wants Tidal alongside YouTube Music inside the same MPD-driven workflow. This spec defines the rebrand from `ytmpd` to `xmpd` ("multi-source MPD daemon"), the provider-abstraction refactor that supports multiple sources cleanly, and the addition of Tidal as the second provider with full feature parity to YouTube Music (sync, search, radio, like/dislike, history, like-indicator). A subsequent spec (out of scope here) will add cross-provider liked-tracks sync.

## Goals

1. Rename the project from `ytmpd` to `xmpd` end-to-end (Python package, CLI binaries, systemd unit, config dir, repo) with full git-history preservation.
2. Extract a `Provider` abstraction; refactor existing YouTube-Music code to fit it, no behavior change.
3. Add `TidalProvider` with parity to YT for: sync, search, radio, like/dislike, history reporting, like indicator.
4. Allow each provider to be independently enabled/disabled and authenticated via config and a CLI command.
5. Preserve the user's existing YouTube-Music data (cached track metadata, auth tokens, config) through migration.
6. Extend `extras/airplay-bridge/` so Tidal-served tracks get correct album art on AirPlay receivers.

## Non-goals

- Cross-provider liked-tracks sync (e.g., "if I like a YT track, also favorite it on Tidal"). Acknowledged as a future phase; this spec leaves a hook (`Track.liked_signature`) but does not implement.
- Supporting providers beyond YouTube Music and Tidal in this iteration.
- Migrating spec/design docs from prior eras into renamed forms — historical specs stay verbatim under their original names.
- Changing MPD's role. xmpd remains a feeder; MPD owns playback.
- Rewriting `airplay-bridge` to be provider-aware as a first-class concept. It only learns enough to fetch art for Tidal-tagged tracks.
- Maintaining backward compatibility with `ytmpctl` as an installed alias. Hard-cut to `xmpctl`.

## Naming and scope decisions (locked)

| Decision | Value |
|---|---|
| Repo name | `xmpd` |
| Python package | `xmpd` |
| CLI binary | `xmpctl` (note: no `d`; matches old `ytmpctl` convention where the daemon is `xmpd`, the controller is `xmpctl`) |
| Status binary | `xmpd-status`, `xmpd-status-preview` |
| Systemd unit | `xmpd.service` |
| Config dir | `~/.config/xmpd/` |
| Log file | `xmpd.log` (was `ytmpd.log`) |
| Provider canonical names | `yt`, `tidal` |
| Proxy URL pattern | `http://localhost:8080/proxy/<provider>/<track_id>` |
| MPD playlist prefixes | `YT: ` for YouTube, `TD: ` for Tidal (configurable in `playlist_prefix.<provider>`) |
| YT "Liked Songs" mapped name | `YT: Liked Songs` (unchanged) |
| Tidal favorites mapped name | `TD: Favorites` |
| Tidal default quality ceiling | `HI_RES_LOSSLESS` |
| Tidal favorited-playlist sync | included by default (`tidal.sync_favorited_playlists: true`) |
| Tidal dislike semantics | maps to "unfavorite" (mirrors YT's broken-toggle pattern documented in old README) |
| Repo migration path | new repo `tuncenator/xmpd` with full git history; old `tuncenator/ytmpd` archived with notice |
| CLI alias | none. Hard rename. Old clone left on disk as a fallback, deleted by user when confident. |
| Config dir migration | `cp -r ~/.config/ytmpd ~/.config/xmpd`, rename `ytmpd.log` → `xmpd.log` inside |

## Architecture

### Provider abstraction

`xmpd/providers/base.py` defines a Protocol-style class plus shared dataclasses. Concrete providers under `xmpd/providers/ytmusic.py` and `xmpd/providers/tidal.py`. A registry in `xmpd/providers/__init__.py` exposes `get_enabled_providers()` reading config.

**Naming convention:** module/class names are descriptive (`ytmusic.py`, `YTMusicProvider`); the in-code/config canonical name (`provider.name`, config section, URL path component, `playlist_prefix` key) is the short form (`yt`, `tidal`). The mapping is fixed: `YTMusicProvider.name = 'yt'`, `TidalProvider.name = 'tidal'`. Anywhere a provider needs to be looked up by name, use the short form.

```python
# xmpd/providers/base.py
from typing import Protocol, runtime_checkable
from dataclasses import dataclass

@dataclass(frozen=True)
class TrackMetadata:
    title: str
    artist: str | None
    album: str | None
    duration_seconds: int | None
    art_url: str | None  # provider-supplied canonical art (Tidal: tidalapi album.image; YT: thumbnail)

@dataclass(frozen=True)
class Track:
    provider: str          # "yt" | "tidal"
    track_id: str
    metadata: TrackMetadata
    liked: bool | None     # None = unknown
    liked_signature: str | None = None  # future: cross-provider matching key (artist+title+album fuzzy hash); reserved

@dataclass(frozen=True)
class Playlist:
    provider: str
    playlist_id: str
    name: str
    track_count: int
    is_owned: bool          # Tidal distinguishes; YT always True
    is_favorites: bool      # the special "Liked Songs"/"Favorites" pseudo-playlist

@runtime_checkable
class Provider(Protocol):
    name: str  # canonical, "yt" or "tidal"

    def is_enabled(self) -> bool: ...
    def is_authenticated(self) -> bool: ...

    # Library
    def list_playlists(self) -> list[Playlist]: ...
    def get_playlist_tracks(self, playlist_id: str) -> list[Track]: ...
    def get_favorites(self) -> list[Track]: ...

    # Stream
    def resolve_stream(self, track_id: str) -> str: ...                  # playable HTTP/HLS URL
    def get_track_metadata(self, track_id: str) -> TrackMetadata: ...

    # Discovery
    def search(self, query: str, limit: int = 25) -> list[Track]: ...
    def get_radio(self, seed_track_id: str, limit: int = 25) -> list[Track]: ...

    # Ratings
    def like(self, track_id: str) -> None: ...
    def dislike(self, track_id: str) -> None: ...                        # Tidal: maps to unlike
    def unlike(self, track_id: str) -> None: ...
    def get_like_state(self, track_id: str) -> bool: ...

    # History
    def report_play(self, track_id: str, duration_seconds: int) -> None: ...
```

Auth lifecycle is per-provider and lives in `xmpd/auth/`:

- `xmpd/auth/ytmusic_cookie.py` — was `ytmpd/cookie_extract.py`. Firefox cookie extraction, browser.json refresh.
- `xmpd/auth/tidal_oauth.py` — new. tidalapi OAuth device flow, token persistence at `~/.config/xmpd/tidal_session.json`, clipboard helper for the auth URL.

### Provider toggle and lifecycle

Daemon startup:

1. Read config; identify enabled providers.
2. For each enabled provider, attempt to authenticate (load token, validate). On failure, log a one-line warning (`"Tidal not configured; run xmpctl auth tidal"`), mark provider unauthenticated, continue. Do NOT block on input.
3. Build provider registry containing only authenticated providers.
4. If registry is empty, log warning, continue running idle (proxy still serves cached tracks; CLI commands still work; sync skipped).
5. Sync engine iterates over the registry on its schedule.
6. Stream proxy registers a route per enabled provider: `/proxy/yt/...`, `/proxy/tidal/...`.

CLI gating:

- `xmpctl auth <provider>` runs the interactive setup flow regardless of `enabled` state (used to bootstrap before flipping `enabled: true`).
- `xmpctl like|dislike|sync|search|radio` infer the provider from context (currently-playing track's proxy URL prefix, or an explicit `--provider` flag where ambiguous).

### Track identity and proxy URL pattern

Compound identity `(provider, track_id)`. Track IDs:

- YT: 11-char video ID, regex `[A-Za-z0-9_-]{11}`. Already validated.
- Tidal: integer string. Treat as opaque; validate `^\d+$`, length up to 20 to be safe.

Proxy URL: `http://<host>:<port>/proxy/<provider>/<track_id>`.

`xmpd/stream_proxy.py` (was `ytmpd/icy_proxy.py`):

- Class renamed `ICYProxyServer` → `StreamRedirectProxy`. The "ICY" name was wrong; this is a 307-redirect resolver, no ICY metadata is injected. `docs/ICY_PROXY.md` deleted; replace with a concise `docs/STREAM_PROXY.md` describing the actual behavior.
- Route: `/proxy/{provider}/{track_id}`.
- Validates provider against the registry; rejects unknown with 404.
- Validates `track_id` against per-provider regex; 400 on bad format.
- Lookup in `track_store` by `(provider, track_id)`.
- Refresh logic: per-provider `stream_cache_hours` (YT: 5h, Tidal: configurable, default 1h until verified). Implementing AI verifies actual Tidal TTL during integration and tunes default.

### Track store schema

Migration from existing schema:

```sql
-- Old (ytmpd):
CREATE TABLE tracks (
    video_id TEXT PRIMARY KEY,
    stream_url TEXT,
    title TEXT NOT NULL,
    artist TEXT,
    updated_at REAL NOT NULL
);

-- Migration on first xmpd startup against an old DB:
ALTER TABLE tracks RENAME COLUMN video_id TO track_id;
ALTER TABLE tracks ADD COLUMN provider TEXT NOT NULL DEFAULT 'yt';
ALTER TABLE tracks ADD COLUMN album TEXT;            -- new; nullable for old rows
ALTER TABLE tracks ADD COLUMN duration_seconds INTEGER; -- new; nullable
ALTER TABLE tracks ADD COLUMN art_url TEXT;          -- new; nullable
-- Drop old PK, recreate as compound:
CREATE UNIQUE INDEX tracks_pk_idx ON tracks(provider, track_id);
```

Migration runs idempotently; daemon detects schema version via PRAGMA `user_version`, applies missing migrations once. Default `provider='yt'` retroactively tags existing data correctly.

### Configuration layout

Full config sketch (lives at `~/.config/xmpd/config.yaml`):

Config section names match the provider canonical names (`yt`, `tidal`) used elsewhere (URLs, code, `playlist_prefix` keys, `provider.name`). One name per provider, used everywhere.

```yaml
# Per-provider
yt:
  enabled: true                   # default true (old ytmpd users keep working)
  stream_cache_hours: 5           # per-provider override; falls back to top-level if absent
  auto_auth:
    enabled: true
    browser: firefox-dev
    container: null
    profile: null
    refresh_interval_hours: 12

tidal:
  enabled: false                  # opt-in; flipped after `xmpctl auth tidal`
  stream_cache_hours: 1           # tighter until TTL behavior verified
  quality_ceiling: HI_RES_LOSSLESS
  sync_favorited_playlists: true

# Shared
mpd_socket_path: ~/.config/mpd/socket
mpd_music_directory: ~/Music
playlist_format: xspf             # or m3u
sync_interval_minutes: 30
enable_auto_sync: true
stream_cache_hours: 5             # default for any provider that doesn't set its own

playlist_prefix:
  yt: "YT: "
  tidal: "TD: "

radio_playlist_limit: 25

history_reporting:
  enabled: false
  min_play_seconds: 30

like_indicator:
  enabled: true
  tag: "+1"
  alignment: right

# Proxy
proxy_enabled: true
proxy_host: localhost
proxy_port: 8080
proxy_track_mapping_db: ~/.config/xmpd/track_mapping.db

# Logging
log_level: INFO
log_file: ~/.config/xmpd/xmpd.log
```

Old `ytmpd` had `auto_auth:` at the top level; the new shape nests it under `yt:`. Most other top-level keys (e.g. `mpd_socket_path`, `sync_interval_minutes`) stay top-level and are unchanged. The config-shape migration is a one-shot rewrite handled by `install.sh` during Phase E; the daemon code only needs to understand the new shape. If the user runs the new daemon against an unmigrated config, they get a clear error pointing them at `install.sh` (or to the migration recipe in `docs/MIGRATION.md`). No deprecation shim in the daemon.

### Auth flows

**YouTube Music (unchanged):**

- Existing Firefox-cookie auto-auth pipeline; `xmpctl auth --auto`.
- Token at `~/.config/xmpd/browser.json`.

**Tidal (new):**

- `xmpctl auth tidal` runs `tidalapi.Session.login_oauth_simple()` (or equivalent). The lib returns a verification URL like `https://link.tidal.com/ABCDE`.
- xmpctl prints the URL to stdout AND copies it to clipboard via `xclip` (X11) or `wl-copy` (Wayland), with a graceful "no clipboard tool found" fallback that just prints. A short message tells the user to paste into their browser.
- xmpctl polls until the token is issued or a timeout (e.g. 5 minutes) elapses.
- On success, write `~/.config/xmpd/tidal_session.json` (token, refresh token, expiry).
- tidalapi auto-refreshes on subsequent uses while the refresh token is valid (months). When the refresh token expires, the daemon logs the warning and stops syncing Tidal until `xmpctl auth tidal` is re-run.

The daemon never invokes interactive auth itself. Missing or expired Tidal token = warn-and-skip.

### History reporter

`xmpd/history_reporter.py` is provider-aware. It identifies the active provider from MPD's current track URL (`/proxy/<provider>/<id>`), looks up the matching `Provider` in the registry, and calls `provider.report_play(track_id, duration_seconds)`. Best-effort: a 4xx/5xx from the provider's history endpoint is logged at WARNING and the play is dropped.

Threshold (`history_reporting.min_play_seconds`) is shared across providers.

### Sync engine

`xmpd/sync_engine.py` iterates over the enabled-and-authenticated providers. Per provider:

1. Fetch playlists (own + favorites; Tidal also includes favorited if `tidal.sync_favorited_playlists`).
2. Per playlist, fetch track listings, populate `track_store` with `(provider, track_id)` rows.
3. Resolve stream URLs (lazily during proxy hit, or eagerly during sync — preserve current behavior where YT defers).
4. Generate MPD playlist files (m3u or xspf) with proxy URLs prefixed by `playlist_prefix[provider]`.
5. Refresh expired stream URLs as needed.

The sync interval is shared. A provider's failure does not stop other providers.

### MPD client interactions

`xmpd/mpd_client.py` writes proxy URLs of the new shape into m3u/xspf files. Format generators (`xspf_generator.py`, m3u writer in `mpd_client.py`) are provider-agnostic; they receive `Track` objects and emit URLs computed by the proxy URL builder.

### Like indicator

Per-track `liked` state is queried from each provider during sync. The indicator append (e.g. `Artist - Title [+1]`) is unchanged; just sourced from the right provider. `YT: Liked Songs` and `TD: Favorites` are skipped (redundant tagging).

### Search

`xmpctl search [--provider yt|tidal|all]` (default `all`). Results are merged and labeled by provider in the interactive picker:

```
> miles davis kind of blue
[YT]  1. So What - Miles Davis (9:22)
[TD]  2. So What - Miles Davis (9:22) [HI_RES]
[YT]  3. Freddie Freeloader - Miles Davis (9:33)
...
```

Tidal results show available quality tag (`[HI_RES]`, `[LOSSLESS]`, etc.) so the user can pick consciously when both providers offer the same track.

### Radio

`xmpctl radio` infers provider from currently-playing track's proxy URL, calls that provider's `get_radio`. Cross-provider radio is not supported in this iteration (Tidal radio seeded from a Tidal track, YT radio from a YT track). If invoked while nothing is playing or the current track has no provider context, prompt the user with `--provider`.

## Phased implementation

The implementing AI executes phases in order. Each phase ends with all tests green. Each phase merges to `main` of the new repo (or, if the AI prefers, ships as a single multi-commit branch).

### Phase A: rebrand + repo move

Mechanical rename. No architectural change. Goal: every file referencing `ytmpd` is updated; tests pass.

**Pre-flight (read-only, in `~/Sync/Programs/ytmpd/`):**

- Verify `main` is clean and synced with origin.
- Prune dead worktree: `git worktree prune`.
- Identify branches with unmerged commits beyond planning docs (none expected as of this spec; only `refactor/icy-refactor` has 1 commit of planning docs which are superseded by this spec — drop the branch).

**Step 1 — clone to new working dir:**

```bash
cd ~/Sync/Programs
git clone ytmpd xmpd
cd xmpd
git remote remove origin
```

`~/Sync/Programs/ytmpd/` stays untouched as a safety net.

**Step 2 — single rename commit:**

`git mv` operations:

- `ytmpd/` → `xmpd/`
- `ytmpd.service` → `xmpd.service`
- `bin/ytmpctl` → `bin/xmpctl`
- `bin/ytmpd-status` → `bin/xmpd-status`
- `bin/ytmpd-status-preview` → `bin/xmpd-status-preview`

Deletions:

- `ytmpd.egg-info/` (regenerates on install)
- `docs/agent/icy-refactor/` (superseded planning docs)
- `docs/ICY_PROXY.md` (replace later with `STREAM_PROXY.md` in Phase B)

Sed across the codebase (use exact-token replacements to avoid mangling unrelated text):

| Pattern | Replacement |
|---|---|
| `from ytmpd` | `from xmpd` |
| `import ytmpd` | `import xmpd` |
| `'ytmpd'` (string literals) | `'xmpd'` (audit each; some are user-facing log messages or path defaults) |
| `"ytmpd"` (string literals) | `"xmpd"` (same audit) |
| `ytmpctl` | `xmpctl` (in docs, scripts, binaries) |
| `ytmpd-status` | `xmpd-status` |
| `ytmpd.service` | `xmpd.service` |
| `~/.config/ytmpd/` | `~/.config/xmpd/` |
| `ytmpd.log` | `xmpd.log` |
| `ytmpd.egg-info` | `xmpd.egg-info` |
| `tuncenator/ytmpd` (URLs) | `tuncenator/xmpd` |

Targeted updates:

- `pyproject.toml`: `name`, `[project.scripts]` entries (`ytmpctl = "ytmpd.bin.ytmpctl:main"` → `xmpctl = "xmpd.bin.xmpctl:main"` or however currently structured; verify entry-point shape).
- `xmpd.service`: `Description=`, `Documentation=`, `ExecStart=...python -m xmpd`, `ReadWritePaths=%h/.config/xmpd %h/Music`.
- `install.sh`, `uninstall.sh`: every reference; also see Phase E for migration helper additions.
- `README.md`: title, command examples, paths. Reframe lead paragraph as "multi-source music daemon (YouTube Music + Tidal)" while preserving honesty about phased rollout.
- `CHANGELOG.md`: preserve all historical "ytmpd v1.0.0" entries verbatim. Add new top entry: `## Unreleased — renamed to xmpd; multi-source architecture follows`.
- `examples/config.yaml`: full rewrite per the config layout in this spec; see Phase B/C for shape.
- `examples/i3blocks.conf`: command path updates.
- All test files in `tests/`: imports + path string assertions (e.g. test fixtures referencing `~/.config/ytmpd/...`).
- All docs in `docs/`: `i3blocks-integration.md`, `MIGRATION.md`, `version-management.md`, `SECURITY_FIXES.md`, `agent/mpd-integration/QUICKSTART.md`, prior specs (leave content but update path references where the spec describes file layout).
- `.pre-commit-config.yaml`: any tool-name configs that key on the package.

**`extras/airplay-bridge/` updates in this phase (rename only; functional Tidal art lookup is Phase D):**

- `mpd_owntone_metadata.py`:
  - `ART_HTTP_USER_AGENT = "ytmpd-airplay-bridge/1.0 (+https://github.com/tyildirim/ytmpd)"` → `"xmpd-airplay-bridge/1.0 (+https://github.com/tuncenator/xmpd)"` (also fixes the stale `tyildirim` username; current is `tuncenator`).
  - `_classify_album` returns the literal string `"ytmpd"` as an internal source marker (line ~442). Rename to `"xmpd-yt"`. This is data, not a docstring; verify all consumers (likely the function itself and possibly the caller's logging).
  - All comments and docstrings mentioning "ytmpd".
- `extras/airplay-bridge/install.sh`, `extras/airplay-bridge/README.md` if present: every reference.

**Logger names:** `getLogger(__name__)` adapts automatically. Verify with grep: no explicit `getLogger('ytmpd...')` or `logging.Logger('ytmpd')` calls. (Confirmed clean during design.)

**Commit message:**

```
rename: ytmpd → xmpd for multi-source support

Mechanical rename of the Python package, CLI binaries, systemd unit,
and config dir from `ytmpd` to `xmpd`. No behavioral changes; the
provider abstraction and Tidal integration follow in subsequent commits.

- Python package: ytmpd/ → xmpd/
- CLI: ytmpctl → xmpctl
- Status: ytmpd-status → xmpd-status (+ preview)
- systemd: ytmpd.service → xmpd.service
- Default config dir: ~/.config/ytmpd/ → ~/.config/xmpd/
- airplay-bridge: User-Agent and internal source marker updated
- Drops superseded docs/agent/icy-refactor/ planning docs
- Drops docs/ICY_PROXY.md (replaced by docs/STREAM_PROXY.md in Phase B)
```

Single commit. Partial rename leaves the codebase non-functional.

**Step 3 — create remote and push:**

```bash
gh repo create tuncenator/xmpd --public \
  --description "Multi-source music daemon: syncs YouTube Music + Tidal libraries to MPD"
git remote add origin git@github.com:tuncenator/xmpd.git
git push -u origin main --tags
```

**Step 4 — archive old repo:**

In `~/Sync/Programs/ytmpd/`:

1. Add a top-of-file notice to `README.md`:

   ```markdown
   > **This project has moved.** ytmpd is now [xmpd](https://github.com/tuncenator/xmpd),
   > a multi-source music daemon that adds Tidal alongside YouTube Music. This repo
   > is preserved for historical reference and will not receive updates.
   ```

2. Commit and push, then archive:

   ```bash
   git add README.md
   git commit -m "docs: project renamed to xmpd; this repo archived"
   git push origin main
   gh repo archive tuncenator/ytmpd
   ```

**Phase A acceptance:** `pytest` passes in the new repo. `python -m xmpd` starts the daemon (against migrated config) and behaves identically to the old daemon. `xmpctl --help` works. Old GitHub repo is archived with notice.

### Phase B: provider abstraction extraction

Refactor; no new functionality. Goal: existing YT code routed through a `Provider`-shaped interface; tests still pass; ready to drop in Tidal.

**Steps:**

1. Create `xmpd/providers/__init__.py`, `xmpd/providers/base.py` with the Protocol and dataclasses defined in this spec.
2. Move and refactor `xmpd/ytmusic.py` → `xmpd/providers/ytmusic.py` as `YTMusicProvider`. Implement every Provider method by delegating to the existing `YTMusicClient` internals or wrapping them. Preserve all existing YT behavior (auto-auth, like/dislike toggle quirks, history reporting, search, radio, like indicator).
3. Move `xmpd/cookie_extract.py` → `xmpd/auth/ytmusic_cookie.py`. Update imports.
4. Rename `xmpd/icy_proxy.py` → `xmpd/stream_proxy.py`; class `ICYProxyServer` → `StreamRedirectProxy`. Switch route to `/proxy/{provider}/{track_id}` (provider parameter validated against registry). Preserve all redirect/refresh logic. Note: this is a behavior-equivalent rename; existing single-provider deployments use only `yt` for now.
5. Replace `docs/ICY_PROXY.md` with `docs/STREAM_PROXY.md` describing the actual 307-redirect lazy-resolver behavior (no ICY metadata is injected; that was the old name's lie).
6. Migrate track-store schema. Add `xmpd/track_store.py` migration logic per the SQL above. Compound key `(provider, track_id)`; old rows get `provider='yt'`. Add `album`, `duration_seconds`, `art_url` columns (nullable for old rows).
7. Update `xmpd/sync_engine.py` to iterate over registry. With only YT enabled, behavior is identical.
8. Update `xmpd/daemon.py` to read provider config sections (`yt:`, `tidal:`), build the registry from enabled+authenticated providers, log warnings for misconfigured providers, never block on input. The daemon understands only the new config shape; stale `auto_auth:` at top level produces a clear error pointing at `install.sh`/`docs/MIGRATION.md`.
9. Update `xmpd/mpd_client.py` and `xmpd/xspf_generator.py` to use the new proxy URL builder (`build_proxy_url(provider, track_id)`).
10. Update `xmpd/history_reporter.py` to identify provider from the proxy URL prefix and call `provider.report_play(...)`.
11. Update `xmpd/rating.py` to dispatch via provider.
12. Update `bin/xmpctl`: search/radio/like/dislike inferences and the new `auth` subcommand structure. Provider canonical names are used in subcommands: `xmpctl auth yt` (subsumes old `ytmpctl auth --auto`) and, in Phase C, `xmpctl auth tidal`.
13. Update tests. Existing YT-shaped tests should still pass after refactoring; structurally they may need to instantiate `YTMusicProvider` instead of `YTMusicClient` directly.

**Phase B acceptance:** `pytest` passes. Daemon starts, syncs YT, plays tracks. Behavior is indistinguishable from Phase A externally.

### Phase C: Tidal provider

Add the Tidal source.

**Dependencies:** add `tidalapi` to `pyproject.toml` with a pinned version (latest stable as of implementation date). Add a comment that the lib is unofficial and may need bumping when Tidal changes their API.

**Steps:**

1. Implement `xmpd/auth/tidal_oauth.py`:
   - Wraps `tidalapi.Session.login_oauth_simple()` (or whatever current API is).
   - Returns the verification URL; persists tokens to `~/.config/xmpd/tidal_session.json`.
   - Provides clipboard helper: detect `wl-copy` (Wayland) → `xclip` (X11) → fallback. Shell out via `subprocess`; never crash if unavailable.
   - Token loader for daemon use; raises a typed `TidalAuthRequired` exception if missing.
2. Implement `xmpd/providers/tidal.py` as `TidalProvider` per the Protocol. Maps:
   - `list_playlists()` — `session.user.playlists()` plus, if `sync_favorited_playlists`, also `session.user.favorites.playlists()`. Tag each with `is_owned` accordingly. Synthesize the favorites pseudo-playlist via `session.user.favorites.tracks()`.
   - `get_playlist_tracks(id)` — straightforward; convert tidalapi `Track` objects to xmpd `Track`s with `provider='tidal'`.
   - `get_favorites()` — favorites tracks endpoint; returned as a list (used by sync engine to populate `TD: Favorites`).
   - `resolve_stream(track_id)` — `session.track(id).get_url(quality=resolved_quality)` where `resolved_quality = min(config.tidal.quality_ceiling, track.audio_quality)`. Returns playable URL (HLS manifest or direct file depending on quality and Tidal's current behavior — verify during implementation).
   - `get_track_metadata(track_id)` — `session.track(id)`; populate `TrackMetadata` including `art_url` from `track.album.image(640)`.
   - `search(query)` — `session.search(query, models=[tidalapi.media.Track])`; convert results.
   - `get_radio(seed_id)` — `session.track(seed_id).get_track_radio()`.
   - `like(id)` — `session.user.favorites.add_track(id)`.
   - `dislike(id)` — alias for `unlike(id)`. Document in code comment.
   - `unlike(id)` — `session.user.favorites.remove_track(id)`.
   - `get_like_state(id)` — check membership in `session.user.favorites.tracks()`. Cache the favorites set during sync to avoid one API call per track.
   - `report_play(id, duration_seconds)` — best-effort; tidalapi's playback reporting if available, otherwise no-op with debug log. Do NOT raise.
3. Wire `TidalProvider` into the registry. Default `tidal.enabled: false` (opt-in).
4. Add `xmpctl auth tidal` subcommand that invokes the OAuth flow.
5. Update example `config.yaml` with the full layout from this spec.
6. Update `xmpd/stream_proxy.py` to register `/proxy/tidal/...` route when Tidal is enabled. Per-provider validation regex (`^\d{1,20}$` for Tidal track IDs).
7. Update `xmpd/track_store.py` to handle Tidal rows uniformly.
8. Update `bin/xmpctl search` to support `--provider {yt,tidal,all}` flag, default `all`, results labeled.
9. Update `bin/xmpctl radio` to infer provider from current track URL.
10. Tests: unit tests with `tidalapi` mocked. Integration tests behind `pytest -m tidal_integration` flag (real auth required). Provide test fixtures that mock the OAuth flow and the favorites/playlists/search/radio responses.

**Phase C acceptance:** `pytest` passes. With `tidal.enabled: true` and a valid token, daemon syncs Tidal playlists into MPD as `TD: Favorites`, `TD: <playlist name>`. Tracks play. `xmpctl search`, `xmpctl radio`, `xmpctl like`, `xmpctl dislike` all work for Tidal tracks. History reporting fires (best-effort).

### Phase D: AirPlay bridge — Tidal album art

`extras/airplay-bridge/mpd_owntone_metadata.py` currently has a YouTube-thumbnail fetch path keyed off the `/proxy/<11-char-video-id>` URL pattern. For Tidal-served tracks, we want `art_url` from the Tidal track's album.

**Steps:**

1. Update the URL parsing in `mpd_owntone_metadata.py` to recognize the new pattern `/proxy/<provider>/<track_id>`. Branch by provider.
2. For `provider == 'yt'`: existing YouTube thumbnail fetch path. (URL-construction may need to extract just the `track_id` portion.)
3. For `provider == 'tidal'`: read `art_url` from the track-store row (which the daemon populated during sync). The bridge already has a SQLite reader for the track DB (or add one) to fetch metadata fields. Cache locally per existing chain.
4. Update `_classify_album` to return three categories: `"xmpd-yt"`, `"xmpd-tidal"`, MPD's actual album for everything else. Audit consumers for the old `"ytmpd"` value and update.
5. Verify the existing iTunes/MusicBrainz fallback chain still applies for everything; Tidal art is preferred (free, no rate limit, accurate) but if Tidal art lookup fails for a track, fall back through the chain.

**Phase D acceptance:** Playing a Tidal track over AirPlay (Denon, kitchen) shows the correct album art. Playing a YT track still works. Local tracks still trigger the existing iTunes/MusicBrainz chain.

### Phase E: install/migration polish + docs

**`install.sh`:**

- Detects `~/.config/ytmpd/` and offers `cp -r ~/.config/ytmpd ~/.config/xmpd` if `~/.config/xmpd/` doesn't exist. Inside the new dir, rename `ytmpd.log` → `xmpd.log`.
- Rewrites `~/.config/xmpd/config.yaml` shape: nests existing top-level `auto_auth:` block under a new `yt:` section, adds `yt.enabled: true`, adds a stub `tidal:` section with `enabled: false` and the documented Tidal defaults. Idempotent (skip if already migrated). Implementing AI uses a YAML-aware approach (e.g. `ruamel.yaml` to preserve comments) rather than naive sed, so the user's existing comments survive.
- Detects existing `~/.config/systemd/user/ytmpd.service` and disables/removes it before installing the new `xmpd.service`.
- Drops `xmpd.service` into `~/.config/systemd/user/`, runs `systemctl --user daemon-reload`.
- Note in the install summary that the user should `sed -i 's/\bytmpctl\b/xmpctl/g; s/ytmpd-status/xmpd-status/g' ~/.i3/config && i3-msg reload`.

**`uninstall.sh`:** updates references; preserves `~/.config/xmpd/` data by default.

**`docs/MIGRATION.md`:** rewrite (or add a new section) covering the rename, including the manual-fallback recipe in case the install script can't run unattended.

**`README.md`:** rewrite for multi-source. Include sections for:
- Quick start (both providers off by default except YT)
- `xmpctl auth tidal` walkthrough
- Per-provider config keys
- Cross-provider behavior of like/dislike/search/radio
- AirPlay bridge updated context

**`CHANGELOG.md`:** entry summarizing the rebrand and Tidal addition.

**Phase E acceptance:** A fresh user can clone the new repo, run `install.sh`, configure Tidal, and reach a working state with both providers without consulting the spec.

## Tests strategy

- **Unit tests** for each provider with the upstream library mocked (`ytmusicapi`, `tidalapi`). Cover: list_playlists, get_playlist_tracks, get_favorites, resolve_stream, search, radio, like/dislike round-trip, get_like_state, report_play (success and best-effort-failure).
- **Track store migration tests:** seed an old-shape DB, run migration, verify rows tagged `provider='yt'` and new columns nullable.
- **Stream proxy tests:** verify routing for both providers, 404 on unknown provider, 400 on bad IDs, 307 redirect behavior, refresh-on-expiry.
- **Daemon integration tests:** registry construction with various enabled/authenticated combinations (YT only, Tidal only, both, neither). Verify graceful warn-and-continue on missing auth.
- **Tidal integration tests** (live API): gated behind `pytest -m tidal_integration`. Skipped by default; require `XMPD_TIDAL_TEST_TOKEN` env var.
- **CLI tests** for `xmpctl auth tidal` flow with mocked clipboard helper, mocked OAuth.
- **AirPlay bridge tests:** none added (existing convention is no tests for this module per local-album-art spec; manual verification).

## Migration recipe (user-machine, post-Phase-E)

After the implementing AI ships and the user pulls the new repo:

```bash
# in ~/Sync/Programs/xmpd
./install.sh                   # idempotent; copies config dir, replaces systemd unit

sed -i 's/\bytmpctl\b/xmpctl/g; s/ytmpd-status/xmpd-status/g' ~/.i3/config
i3-msg reload

# optional: enable Tidal
xmpctl auth tidal              # prints + clipboard-copies a tidal.com URL
# (paste in browser, log in, approve)
sed -i 's/^  enabled: false/  enabled: true/' ~/.config/xmpd/config.yaml  # under tidal:
systemctl --user restart xmpd
xmpctl status
```

After ~2 weeks of confidence, delete the old fallback:

```bash
rm -rf ~/Sync/Programs/ytmpd
rm -rf ~/.config/ytmpd
```

## Risks and known constraints

- **tidalapi is unofficial.** Tidal periodically changes their API. Pin a known-good version in `pyproject.toml`. Wrap tidalapi calls with `try/except` in the provider; log+notify on unexpected breakage. The user accepts that "Tidal integration may break and need maintenance" is part of the deal.
- **HiRes streams as HLS manifests.** Tidal's HiRes responses may be HLS manifests rather than direct FLAC URLs. Modern MPD has built-in HLS support but quality may vary. Implementing AI verifies during integration; if HiRes manifests are unreliable, fall back per-track to LOSSLESS without changing the user's `quality_ceiling`. Surface a warning if such fallback occurs frequently.
- **Tidal stream URL TTL** is unknown at spec time. Defaults `tidal.stream_cache_hours: 1` to be safe; implementing AI verifies actual TTL and tunes (or dynamically refreshes on 403/410 from the redirect target).
- **Tidal play-reporting endpoint** may 4xx without warning. Best-effort only; never raises.
- **Region-locked tracks** are skipped silently with debug log. Not surfaced to user unless they enable debug logging.
- **Cross-provider track-id collisions:** none possible because the provider name is part of the compound key. Documented for clarity.
- **Concurrent provider syncs:** sync engine processes providers sequentially per cycle to keep MPD-side updates predictable. (Could parallelize later; out of scope.)

## Out of scope (future work)

1. **Cross-provider liked-tracks sync.** When the user likes a track on YT, also favorite on Tidal (and vice versa). This requires fuzzy matching across providers (artist + title + album). The `Track.liked_signature` field reserved in this spec is the hook for that future work — populate during sync via a normalized hash, then a sync layer can match across providers using this key.
2. **Additional providers** (Spotify, Apple Music, Deezer, Bandcamp, etc.). The Provider Protocol is designed for extension but no other implementations are planned in this iteration.
3. **Provider-specific UI flourishes** (e.g., Tidal Atmos format detection, Spotify-style "wrapped" stats).
4. **MPD-level format negotiation** (e.g., transcoding HiRes FLAC to LOSSLESS for bandwidth-constrained outputs). Defer.
5. **Offline mode / pre-download** for Tidal tracks (Tidal Premium offering). Defer.

## Acceptance criteria (overall)

The implementing AI's work is complete when:

- The new repo `tuncenator/xmpd` exists with full git history; the old `tuncenator/ytmpd` is archived with the notice.
- `pytest` passes locally and in CI (if added).
- The user can run `xmpctl auth tidal`, complete the OAuth flow via clipboard-paste-into-browser, and have Tidal sync into MPD as `TD: ...` playlists.
- Existing YT functionality is identical to pre-rename behavior (sync, search, radio, like/dislike, history, like indicator, i3blocks status).
- The user can disable either provider in config and the other keeps working.
- The AirPlay bridge displays correct album art for Tidal-served tracks.
- The user's existing config and track-store data are preserved through migration without manual intervention beyond running `install.sh`.
- Documentation (README, CHANGELOG, MIGRATION) reflects multi-source reality.
- All references to `ytmpd`/`ytmpctl`/`ytmpd-status`/`ytmpd.service`/`~/.config/ytmpd/` are gone from active code paths (historical CHANGELOG entries and prior specs may retain them as historical record).

## Appendix: file-level inventory of the rename

Files with `ytmpd`/`YTMPD`/`ytmpctl` token occurrences as of design time (verified by grep, excluding `.venv`, `.git`, `htmlcov`, caches, `MagicMock`, `.coverage`, `uv.lock`, `.egg-info`):

- `pyproject.toml`
- `.pre-commit-config.yaml`
- `README.md`
- `CHANGELOG.md`
- `install.sh`, `uninstall.sh`
- `ytmpd.service`
- `bin/ytmpctl`, `bin/ytmpd-status`, `bin/ytmpd-status-preview`
- `examples/config.yaml`, `examples/i3blocks.conf`
- `docs/i3blocks-integration.md`, `docs/MIGRATION.md`, `docs/SECURITY_FIXES.md`, `docs/version-management.md`
- `docs/ICY_PROXY.md` (delete; replace with `docs/STREAM_PROXY.md` in Phase B)
- `docs/agent/mpd-integration/QUICKSTART.md`
- `docs/agent/icy-refactor/*` (delete; superseded)
- `docs/superpowers/specs/*` (historical specs left verbatim; only path-reference updates if any)
- All `ytmpd/*.py` (renamed to `xmpd/*.py`; internals updated)
- All `tests/**/*.py`
- `extras/airplay-bridge/mpd_owntone_metadata.py` (User-Agent string + `_classify_album` marker + comments)
- `extras/airplay-bridge/install.sh`, `extras/airplay-bridge/README.md` (if present; verify)

Approximate count: ~50 files touched, ~170 references to `~/.config/ytmpd` paths alone (mostly in test fixtures and code defaults). Rename is mechanical but voluminous; pair `git mv` for renames with a single sed pass for content, then a manual review of any string literals that look user-facing (log messages, error text).
