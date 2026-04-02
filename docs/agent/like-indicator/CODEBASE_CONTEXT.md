# Codebase Context

> **Living document** -- each phase updates this with new discoveries and changes.
> Read this before exploring the codebase. It may already have what you need.
>
> Last updated by: Phase 2 - Testing (2026-04-02)

---

## Architecture Overview

ytmpd is a Python daemon that bridges YouTube Music and MPD (Music Player Daemon). It periodically syncs YouTube Music playlists to MPD as M3U or XSPF playlist files, optionally proxying audio streams through an ICY metadata proxy.

**Main layers:**
- **API Layer** (`ytmusic.py`): Wraps `ytmusicapi` library for YouTube Music API calls (playlists, tracks, ratings, history)
- **Sync Layer** (`sync_engine.py`): Orchestrates fetching playlists, resolving URLs, writing playlist files
- **MPD Layer** (`mpd_client.py`): Manages MPD connection and playlist file generation (M3U/XSPF)
- **Proxy Layer** (`icy_proxy.py`, `stream_resolver.py`, `track_store.py`): On-demand stream URL resolution and metadata
- **Daemon Layer** (`daemon.py`): Wires all components together, runs background threads
- **Config Layer** (`config.py`): YAML-based config with defaults, deep-merge, and validation

**Data flow:**
```
YouTube Music API --> SyncEngine --> MPDClient --> Playlist files (M3U/XSPF) --> MPD --> ncmpcpp
```

---

## Key Files & Modules

> List important files that agents are likely to need. Include purpose and when you would read each file.

| File Path | Purpose | Notes |
|-----------|---------|-------|
| `ytmpd/config.py` | Config loading, defaults, validation | Deep-merge for nested dicts at line 86-89 (includes `like_indicator`). Validation in `_validate_config()`. `like_indicator` validation at end of function. |
| `ytmpd/sync_engine.py` | Playlist sync orchestration | `sync_all_playlists()` at line 140. Liked set built after liked songs fetch. `_sync_single_playlist_internal()` accepts `liked_video_ids` param. |
| `ytmpd/mpd_client.py` | MPD connection + playlist file writing | `_apply_like_indicator()` helper for title formatting. `create_or_replace_playlist()` accepts `liked_video_ids`, `like_indicator`, `is_liked_playlist`. |
| `ytmpd/daemon.py` | Component wiring and daemon lifecycle | SyncEngine initialized at lines 111-128. Passes `like_indicator` config. |
| `ytmpd/ytmusic.py` | YouTube Music API wrapper | `get_liked_songs()` at line 536 returns `list[Track]`. `Track` dataclass has `video_id`, `title`, `artist`, `duration_seconds`. |
| `ytmpd/xspf_generator.py` | XSPF XML generation | `XSPFTrack` dataclass and `generate_xspf()` function. |
| `ytmpd/rating.py` | Like/dislike toggle state machine | `RatingState` enum and `RatingManager`. Not directly modified by this feature. |
| `examples/config.yaml` | Documented example configuration | Update when adding new config sections. |
| `tests/test_config.py` | Config validation tests | Reference for testing patterns. |
| `tests/test_mpd_client.py` | MPD client tests | Reference for mocking MPD and testing playlist generation. |
| `tests/test_sync_engine.py` | Sync engine tests | Reference for mocking YTMusic/MPD and testing sync flow. |
| `tests/test_like_indicator.py` | Like indicator tests | 33 tests: config validation, title formatting, M3U/XSPF generation, SyncEngine integration. |

---

## Important APIs & Interfaces

> Document classes, functions, and interfaces that multiple phases will interact with.

### YTMusicClient (`ytmpd/ytmusic.py`)

```python
class YTMusicClient:
    def get_user_playlists(self) -> list[Playlist]: ...
    def get_playlist_tracks(self, playlist_id: str) -> list[Track]: ...
    def get_liked_songs(self, limit: int | None = None) -> list[Track]: ...
    def get_track_rating(self, video_id: str) -> RatingState: ...
    def set_track_rating(self, video_id: str, rating: RatingState) -> None: ...
```

### Track dataclass (`ytmpd/ytmusic.py`, line ~54)

```python
@dataclass
class Track:
    video_id: str
    title: str
    artist: str
    duration_seconds: float | None = None
```

### Playlist dataclass (`ytmpd/ytmusic.py`)

```python
@dataclass
class Playlist:
    id: str
    name: str
    track_count: int
```

### SyncEngine (`ytmpd/sync_engine.py`)

```python
class SyncEngine:
    def __init__(
        self,
        ytmusic_client: YTMusicClient,
        mpd_client: MPDClient,
        stream_resolver: StreamResolver,
        playlist_prefix: str = "YT: ",
        track_store: Optional["TrackStore"] = None,
        proxy_config: Optional[dict] = None,
        should_stop_callback: Optional[callable] = None,
        playlist_format: str = "m3u",
        mpd_music_directory: Optional[str] = None,
        sync_liked_songs: bool = True,
        liked_songs_playlist_name: str = "Liked Songs",
    ): ...

    def sync_all_playlists(self) -> SyncResult: ...
    def sync_single_playlist(self, playlist_name: str) -> SyncResult: ...
```

### MPDClient (`ytmpd/mpd_client.py`)

```python
class MPDClient:
    def _apply_like_indicator(
        self,
        title: str,
        video_id: str,
        liked_video_ids: set[str] | None,
        like_indicator: dict | None,
        is_liked_playlist: bool,
    ) -> str: ...

    def create_or_replace_playlist(
        self,
        name: str,
        tracks: list[TrackWithMetadata],
        proxy_config: dict[str, Any] | None = None,
        playlist_format: str = "m3u",
        mpd_music_directory: Optional[str] = None,
        liked_video_ids: set[str] | None = None,
        like_indicator: dict | None = None,
        is_liked_playlist: bool = False,
    ) -> None: ...
```

### TrackWithMetadata (`ytmpd/mpd_client.py`, line 23)

```python
@dataclass
class TrackWithMetadata:
    url: str
    title: str
    artist: str
    video_id: str
    duration_seconds: Optional[float] = None
```

### Config structure (`ytmpd/config.py`)

Config is a flat dict with nested dicts for subsystems. Nested dicts requiring deep-merge: `auto_auth`, `history_reporting`, `like_indicator`.

```python
"like_indicator": {
    "enabled": False,   # bool
    "tag": "+1",        # non-empty string, shown as [tag]
    "alignment": "right",  # "left" or "right"
}
```

---

## Patterns & Conventions

### Config pattern
- Defaults defined in `default_config` dict in `load_config()` (line 37)
- Nested dicts deep-merged at line 86-89
- Validation in `_validate_config()` follows pattern: check type, check value range, raise `ValueError`

### Sync flow
- `sync_all_playlists()` fetches all playlists, then iterates calling `_sync_single_playlist_internal()` for each
- Liked songs handled as a special playlist with `id="__LIKED_SONGS__"` and name from config `liked_songs_playlist_name`
- Each playlist sync: fetch tracks -> resolve URLs (or skip if proxy) -> build `TrackWithMetadata` list -> call `mpd.create_or_replace_playlist()`

### Playlist generation
- `create_or_replace_playlist()` dispatches to `_create_m3u_playlist()` or `_create_xspf_playlist()` based on format
- M3U: writes `#EXTM3U` header + `#EXTINF:-1,Artist - Title` + URL per track
- XSPF: builds `XSPFTrack` list, calls `generate_xspf()`, writes XML file
- M3U goes to `mpd_playlist_directory`, XSPF goes to `mpd_music_directory/_youtube/`

### Testing patterns
- Tests use `unittest.mock.patch` and `MagicMock` for external dependencies
- `tmp_path` pytest fixture for temporary file paths
- Each test file typically has a `@pytest.fixture` for the class under test with mocked dependencies

---

## Data Models

### Liked Songs identification
- Liked songs playlist uses sentinel ID `"__LIKED_SONGS__"`
- During sync, `get_liked_songs()` returns `list[Track]` -- same dataclass as regular playlist tracks
- Track membership in liked songs is determined by presence, not a flag on the Track object

### TrackStore (SQLite)
```sql
CREATE TABLE tracks (
    video_id TEXT PRIMARY KEY,
    stream_url TEXT,
    artist TEXT,
    title TEXT NOT NULL,
    updated_at REAL NOT NULL
);
```

---

## Dependencies & Integration Points

- SyncEngine receives all dependencies via constructor injection
- Daemon (`daemon.py`) is the composition root -- it reads config and wires everything together
- Config values flow: `config.yaml` -> `load_config()` -> `daemon.__init__()` -> component constructors

---

## Environment & Configuration

- **Python**: 3.11+
- **Package manager**: uv
- **Config file**: `~/.config/ytmpd/config.yaml`
- **Auth file**: `~/.config/ytmpd/browser.json`
- **Run tests**: `uv run pytest tests/ -v`
- **Run daemon**: `uv run python -m ytmpd`
- **Lint**: `uv run ruff check ytmpd/`

---

## Update Log

> Each phase briefly notes what it added or changed in this document.

- **Phase 0 (Setup)**: Initial codebase exploration and documentation.
- **Phase 1 (Core Implementation)**: Added `like_indicator` config, SyncEngine liked set building, MPDClient `_apply_like_indicator()` helper, M3U/XSPF title modification, daemon wiring. Updated existing test assertions for new params. Fixed pre-existing daemon test mock.
- **Phase 2 (Testing)**: Created `tests/test_like_indicator.py` with 33 tests. Fixed `callable | None` -> `Callable | None` type annotation bug in `sync_engine.py`.
