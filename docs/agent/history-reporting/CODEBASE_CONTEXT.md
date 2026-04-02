# Codebase Context

> **Living document** -- each phase updates this with new discoveries and changes.
> Read this before exploring the codebase. It may already have what you need.
>
> Last updated by: Phase 0 - Initial Setup (2026-04-02)

---

## Architecture Overview

ytmpd is a daemon that bridges YouTube Music and MPD (Music Player Daemon). It syncs YouTube Music playlists as MPD playlists, runs an HTTP proxy for stream URL resolution, and provides a Unix socket command interface.

**Main layers:**
- **Daemon** (`daemon.py`): Orchestrator running 4 background threads (sync, socket, proxy, auto-auth) plus the main signal-handling loop.
- **YouTube Music API** (`ytmusic.py`): Wrapper around `ytmusicapi.YTMusic` with rate limiting, retry, and authentication management.
- **MPD interface** (`mpd_client.py`): Wrapper around `python-mpd2` for playlist management and track info.
- **Storage** (`track_store.py`): SQLite database mapping video_id to stream URLs and metadata.
- **Proxy** (`icy_proxy.py`): Async aiohttp server that redirects MPD requests to YouTube stream URLs with lazy resolution and auto-refresh.
- **Config** (`config.py`): YAML-based configuration with defaults, validation, and path expansion.

**Entry point:** `ytmpd/__main__.py` -> creates `YTMPDaemon` -> calls `daemon.run()`

---

## Key Files & Modules

> List important files that agents are likely to need. Include purpose and when you would read each file.

| File Path | Purpose | Notes |
|-----------|---------|-------|
| `ytmpd/daemon.py` | Main daemon orchestrator (1202 lines) | Thread lifecycle, signal handling, socket commands. Read for thread patterns. |
| `ytmpd/ytmusic.py` | YouTube Music API wrapper (866 lines) | Auth, playlists, tracks, ratings. Read for adding new API methods. |
| `ytmpd/mpd_client.py` | MPD client wrapper (467 lines) | Playlist creation, connection management. Read for MPD interaction patterns. |
| `ytmpd/track_store.py` | SQLite track metadata store (206 lines) | video_id <-> stream_url/metadata mapping. Thread-safe with lock. |
| `ytmpd/icy_proxy.py` | HTTP redirect proxy (346 lines) | Proxy URL format, video ID validation regex, stream URL refresh. |
| `ytmpd/config.py` | Config loading and validation | Defaults, YAML parsing, nested dict validation (auto_auth pattern). |
| `ytmpd/exceptions.py` | Custom exception hierarchy | All exception classes for the project. |
| `ytmpd/sync_engine.py` | Playlist sync orchestration | Coordinates YTMusic -> TrackStore -> MPD playlist flow. |
| `ytmpd/stream_resolver.py` | yt-dlp URL extraction with caching | Resolves video_id to stream URL. |
| `ytmpd/rating.py` | Like/dislike state machine | RatingState enum used by YTMusicClient. |
| `ytmpd/notify.py` | Desktop notifications | Optional desktop notification support. |
| `ytmpd/cookie_extract.py` | Firefox cookie extraction | Auto-auth cookie extraction for browser.json. |
| `ytmpd/history_reporter.py` | MPD playback history reporter | Idle loop, track change detection, pause tracking, YTMusic reporting. |
| `examples/config.yaml` | Example/reference configuration | All config options documented with comments. |
| `pyproject.toml` | Build config, deps, tool settings | Python 3.11+, ruff line-length=100, mypy strict. |

---

## Important APIs & Interfaces

> Document classes, functions, and interfaces that multiple phases will interact with.

### YTMusicClient (`ytmpd/ytmusic.py`)

```python
class YTMusicClient:
    def __init__(self, auth_file: Path | None = None) -> None
    def _init_client(self) -> None
    def refresh_auth(self, auth_file: Path | None = None) -> bool
    def is_authenticated(self) -> tuple[bool, str]  # (valid, error_msg), 5-min cache
    def _rate_limit(self) -> None  # 100ms min between calls
    def _retry_on_failure(self, func: Any, *args: Any, max_retries: int = 3, **kwargs: Any) -> Any

    # Playlist & track methods
    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]
    def get_song_info(self, video_id: str) -> dict[str, Any]  # Returns: video_id, title, artist, album, duration, thumbnail_url
    def get_user_playlists(self) -> list[Playlist]
    def get_playlist_tracks(self, playlist_id: str) -> list[Track]
    def get_liked_songs(self, limit: int | None = None) -> list[Track]

    # Rating methods
    def get_track_rating(self, video_id: str) -> RatingState
    def set_track_rating(self, video_id: str, rating: RatingState) -> None

    # History reporting methods (added in Phase 1)
    def get_song(self, video_id: str) -> dict[str, Any]  # Raw ytmusicapi response with playbackTracking
    def report_history(self, song: dict[str, Any]) -> bool  # Best-effort, never raises

    @staticmethod
    def _parse_duration(duration_str: str) -> int
    @staticmethod
    def setup_browser() -> None
```

**Underlying client access**: `self._client: YTMusic | None` -- the raw ytmusicapi client. New methods can call `self._client.get_song()` and `self._client.add_history_item()` directly.

**Rate limiting pattern** (use for new methods):
```python
def some_method(self, ...) -> ...:
    self._rate_limit()
    result = self._retry_on_failure(self._client.some_api_call, arg1, arg2)
    return result
```

### MPDClient (`ytmpd/mpd_client.py`)

```python
class MPDClient:
    def __init__(self, socket_path: str, playlist_directory: str | None = None) -> None
    def connect(self) -> None
    def disconnect(self) -> None
    def is_connected(self) -> bool  # Checks via ping
    def _ensure_connected(self) -> None  # Auto-reconnects

    def list_playlists(self) -> list[str]
    def playlist_exists(self, name: str) -> bool
    def clear_playlist(self, name: str) -> None
    def add_to_playlist(self, name: str, url: str) -> None
    def create_or_replace_playlist(self, name: str, tracks: list[TrackWithMetadata], ...) -> None
    def currentsong(self) -> dict[str, str]

    # Internal python-mpd2 client for direct access
    _client: MPDClientBase | None
```

**For idle listening**, use `_client` directly:
- `_client.idle('player')` -- blocks until player event, returns `['player']`
- `_client.status()` -- returns dict with `state` (play/stop/pause), `song`, `elapsed`, etc.
- `_client.currentsong()` -- returns dict with `file` (the URL), `title`, `artist`, etc.

### TrackStore (`ytmpd/track_store.py`)

```python
class TrackStore:
    def __init__(self, db_path: str) -> None  # Supports ':memory:' for tests
    def add_track(self, video_id: str, stream_url: str | None, title: str, artist: str | None = None) -> None
    def get_track(self, video_id: str) -> dict[str, Any] | None  # Keys: video_id, stream_url, artist, title, updated_at
    def update_stream_url(self, video_id: str, stream_url: str) -> None
    def close(self) -> None
```

Thread-safe: uses `check_same_thread=False` and `threading.Lock()`.

### HistoryReporter (`ytmpd/history_reporter.py`)

```python
class HistoryReporter:
    def __init__(
        self,
        mpd_socket_path: str,
        ytmusic: YTMusicClient,
        track_store: TrackStore,
        proxy_config: dict[str, Any],
        min_play_seconds: int = 30,
    ) -> None
    def run(self, shutdown_event: threading.Event) -> None  # Main blocking loop
    def _extract_video_id(url: str) -> str | None  # Static, extracts from proxy URL
```

**Key behaviour**: Maintains its own MPD connection. Uses `idle('player')` to block until state changes. Tracks play duration excluding pauses. Reports to YTMusic when `elapsed >= min_play_seconds`.

**State transitions**: play->play (report prev), play->stop (report prev), play->pause (record pause start), pause->play same (resume, exclude pause time), pause->play different (report prev, start new), stop->play (start tracking).

### Daemon Thread Lifecycle (`ytmpd/daemon.py`)

**Key attributes for thread management:**
```python
self._running: bool  # Master shutdown flag
self._sync_lock: threading.Lock  # Prevents concurrent syncs
self._auto_auth_shutdown: threading.Event  # Signals auto-auth thread to stop

# Thread instances (all daemon=True)
self._sync_thread: threading.Thread | None
self._socket_thread: threading.Thread | None
self._proxy_thread: threading.Thread | None
self._auto_auth_thread: threading.Thread | None
```

**Preferred shutdown pattern** (from auto-auth loop):
```python
# In the thread:
def _some_loop(self) -> None:
    try:
        while self._running:
            if self._shutdown_event.wait(timeout=interval):
                break  # Shutdown signal
            if not self._running:
                break
            # Do work...
    except Exception as e:
        logger.error("Error: %s", e, exc_info=True)

# In stop():
self._shutdown_event.set()
self._thread.join(timeout=5)
```

**Thread spawn pattern** (from run()):
```python
self._some_thread = threading.Thread(
    target=self._some_loop,
    name="descriptive-name",
    daemon=True,
)
self._some_thread.start()
```

---

## Patterns & Conventions

### Error Handling
- Custom exceptions in `ytmpd/exceptions.py` -- all inherit from `YTMPDError`
- Logging + graceful degradation: `try: ... except SpecificError as e: logger.error(...); return False`
- Retry with exponential backoff: `_retry_on_failure()` with `2^attempt` second delays
- Thread loops catch all exceptions to prevent uncaught crashes

### Naming Conventions
- Modules: `snake_case.py`
- Classes: `PascalCase`
- Methods/functions: `snake_case`
- Private methods: `_leading_underscore`
- Constants: `UPPER_SNAKE_CASE`
- Logger: `logger = logging.getLogger(__name__)` at module level

### File Organization
- Core modules in `ytmpd/`
- Tests in `tests/` with `test_` prefix
- Examples/config in `examples/`
- Each module has its own logger instance

### End-to-End Flow Example (Sync)
1. `daemon.run()` spawns `_sync_loop` thread
2. `_sync_loop` sleeps for interval, then calls `_perform_sync()`
3. `_perform_sync()` calls `SyncEngine.sync()` under `_sync_lock`
4. `SyncEngine` calls `YTMusicClient.get_user_playlists()` + `get_playlist_tracks()`
5. Tracks stored in `TrackStore.add_track()` (SQLite)
6. Playlists written via `MPDClient.create_or_replace_playlist()` (M3U/XSPF files)
7. State persisted to `sync_state.json`

### End-to-End Flow Example (Proxy Request)
1. MPD requests `http://localhost:8080/proxy/{video_id}`
2. `ICYProxyServer._handle_proxy_request()` validates video_id format
3. Looks up track in `TrackStore.get_track(video_id)`
4. If URL expired or missing, calls `_refresh_stream_url()` -> `StreamResolver`
5. Returns HTTP 307 redirect to YouTube stream URL
6. MPD follows redirect and streams audio

---

## Data Models

### TrackStore SQLite Schema
```sql
CREATE TABLE tracks (
    video_id TEXT PRIMARY KEY,   -- YouTube video ID (11 chars)
    stream_url TEXT,              -- YouTube stream URL (nullable for lazy resolution)
    artist TEXT,                  -- Track artist
    title TEXT NOT NULL,          -- Track title
    updated_at REAL NOT NULL      -- Unix timestamp of last update
);
CREATE INDEX idx_tracks_updated_at ON tracks(updated_at);
```

### Dataclasses
```python
# ytmpd/ytmusic.py
@dataclass
class Playlist:
    id: str           # YouTube playlist ID
    name: str
    track_count: int

@dataclass
class Track:
    video_id: str
    title: str
    artist: str
    duration_seconds: float | None = None

# ytmpd/mpd_client.py
@dataclass
class TrackWithMetadata:
    url: str
    title: str
    artist: str
    video_id: str
    duration_seconds: float | None = None
```

### Video ID Format
- Pattern: `^[a-zA-Z0-9_-]{11}$` (exactly 11 characters)
- Defined as `VIDEO_ID_PATTERN` in `icy_proxy.py` line 42
- Also validated in `daemon.py` `_validate_video_id()` lines 765-785

### Proxy URL Format
```
http://{proxy_host}:{proxy_port}/proxy/{video_id}
```
Example: `http://localhost:8080/proxy/SxFn3x3wt-E`

Generated in `mpd_client.py` line 271:
```python
track_url = f"http://{proxy_config['host']}:{proxy_config['port']}/proxy/{track.video_id}"
```

---

## Dependencies & Integration Points

### Runtime Dependencies (pyproject.toml)
- `ytmusicapi>=1.0.0` -- YouTube Music API
- `pyyaml>=6.0` -- Config parsing
- `python-mpd2>=3.1.0` -- MPD client protocol
- `yt-dlp>=2023.0.0` -- YouTube stream URL extraction
- `aiohttp>=3.9.0` -- Async HTTP server (proxy)

### Dev Dependencies
- `pytest>=7.0.0`, `pytest-asyncio>=0.21.0`, `pytest-cov>=4.0.0`
- `mypy>=1.0.0` (strict: `disallow_untyped_defs = true`)
- `ruff>=0.1.0` (line-length=100, target py311)

### How Modules Connect
- `YTMPDaemon` owns instances of: `YTMusicClient`, `MPDClient`, `TrackStore`, `ICYProxyServer`, `SyncEngine`, `StreamResolver`
- `SyncEngine` receives `YTMusicClient`, `MPDClient`, `TrackStore` via constructor
- `ICYProxyServer` receives `TrackStore`, `StreamResolver` via constructor
- All shared state access is thread-safe (TrackStore uses lock, YTMusicClient uses rate limiter)

---

## Environment & Configuration

### Config File
- Location: `~/.config/ytmpd/config.yaml`
- Auto-created with defaults on first run
- Loaded via `config.load_config()` -- returns merged dict (defaults + user overrides)

### Key Config Sections
- Core paths: `socket_path`, `state_file`, `log_file`, `proxy_track_mapping_db`
- MPD: `mpd_socket_path`, `mpd_playlist_directory`, `mpd_music_directory`
- Sync: `sync_interval_minutes`, `enable_auto_sync`, `playlist_prefix`
- Proxy: `proxy_enabled`, `proxy_host`, `proxy_port`
- Auto-auth: `auto_auth.enabled`, `.browser`, `.container`, `.profile`, `.refresh_interval_hours`

### Build & Run
```bash
# Install
pip install -e ".[dev]"

# Run daemon
ytmpd

# Run tests
pytest tests/ -v

# Type check
mypy ytmpd/

# Lint
ruff check ytmpd/
```

### External Service Dependencies
- MPD running and accessible via socket/TCP
- YouTube Music account with browser.json auth file at `~/.config/ytmpd/browser.json`

---

## Update Log

> Each phase briefly notes what it added or changed in this document.

- **Phase 0 (Setup)**: Initial codebase exploration and documentation.
- **Phase 1 (Core History Reporter)**: Added `ytmpd/history_reporter.py` (HistoryReporter class), added `get_song()` and `report_history()` to YTMusicClient, added HistoryReporter API section, updated YTMusicClient API listing.
