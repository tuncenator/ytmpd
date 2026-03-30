# Codebase Context

> **Living document** -- each phase updates this with new discoveries and changes.
> Read this before exploring the codebase. It may already have what you need.
>
> Last updated by: Phase 4 - Integration Testing and Documentation (2026-03-30)

---

## Architecture Overview

**ytmpd** is a YouTube Music to MPD (Music Player Daemon) synchronization daemon written in Python 3.12+. It runs as a background daemon with multiple threads:

- **Main thread**: Signal handling, keeps process alive
- **Sync thread** (`_sync_loop`): Periodic auto-sync (default 30 min)
- **Socket thread** (`_listen_for_triggers`): Unix socket IPC for CLI commands
- **Proxy thread** (`_run_proxy_server`): Async aiohttp ICY metadata proxy

**Data flow**: YTMusicClient -> SyncEngine -> StreamResolver (yt-dlp) -> MPDClient -> MPD playlists

**Authentication**: Uses `browser.json` (extracted browser request headers) via ytmusicapi. No OAuth. Manual refresh required when cookies expire (~every few days). This is the problem the auto-auth feature solves.

**Config directory**: `~/.config/ytmpd/` contains browser.json, config.yaml, state files, logs, and SQLite databases.

---

## Key Files & Modules

| File Path | Purpose | Notes |
|-----------|---------|-------|
| `ytmpd/daemon.py` | Main daemon class, socket server, thread management, auto-auth | `_auto_auth_loop()`: proactive refresh thread + notification on failure. `_attempt_auto_refresh()`: cookie extraction + client reinit. `_perform_sync()`: reactive refresh on auth failure + notification. `_cmd_status()`: includes auto-auth fields |
| `ytmpd/notify.py` | Desktop notification via notify-send | `send_notification()`: rate-limited (1/hour), handles missing notify-send gracefully |
| `ytmpd/ytmusic.py` | YouTube Music API wrapper via ytmusicapi | `refresh_auth()`: reinitialize client with fresh credentials. `is_authenticated()`: cached 5-min auth check |
| `ytmpd/config.py` (209 lines) | Config loading, validation, defaults | `load_config()` merges user YAML with defaults. `get_config_dir()` returns `~/.config/ytmpd/` |
| `ytmpd/exceptions.py` | Custom exception hierarchy | `YTMusicAuthError` for auth failures, `CookieExtractionError` for cookie extraction. All inherit from `YTMPDError` |
| `ytmpd/sync_engine.py` (535 lines) | Orchestrates YouTube -> MPD playlist sync | `sync_all_playlists()` is the main entry point |
| `ytmpd/stream_resolver.py` (392 lines) | yt-dlp URL extraction with caching | Persistent cache at `stream_cache.json`, 5-hour TTL |
| `ytmpd/icy_proxy.py` (346 lines) | Async HTTP proxy for ICY metadata injection | aiohttp server, lazy URL resolution |
| `ytmpd/mpd_client.py` (466 lines) | MPD wrapper for playlist CRUD | Supports Unix socket and TCP connections |
| `ytmpd/track_store.py` (205 lines) | SQLite metadata storage | Thread-safe with locks |
| `ytmpd/rating.py` (180 lines) | Like/dislike state machine | RatingManager, RatingState, RatingAction |
| `ytmpd/__main__.py` (66 lines) | Entry point | `python -m ytmpd` starts daemon |
| `bin/ytmpctl` | CLI client for daemon commands | `cmd_auth(auto=False)` supports `--auto` flag for cookie extraction, `cmd_status()` shows auto-auth info |
| `bin/ytmpd-status` | i3blocks status display script | `get_auth_status()` returns `(bool, str, int)` 3-tuple with auth_valid, error, auto_refresh_failures. Color overrides: red on auth failure, orange on refresh failures |
| `examples/config.yaml` | Example configuration | All config keys documented with comments, includes `auto_auth` section |
| `ytmpd/cookie_extract.py` | Firefox cookie extraction module | `FirefoxCookieExtractor` class: profile detection, cookie extraction, browser.json generation |
| `tests/test_cookie_extract.py` | Unit tests for cookie extraction | 33 tests covering all methods and edge cases |
| `tests/test_auto_auth_daemon.py` | Tests for daemon auto-auth integration | 21 tests: refresh_auth, proactive/reactive refresh, cooldown, status, state persistence |
| `tests/test_notify.py` | Tests for notification module | 11 tests: send, urgency, icon, missing notify-send, rate limiting |
| `tests/integration/test_auto_auth.py` | Integration tests for auto-auth pipeline | 25 tests: full pipeline, edge cases, containers, profiles, validation, daemon status |

---

## Important APIs & Interfaces

### YTMusicClient (`ytmpd/ytmusic.py`)

```python
class YTMusicClient:
    def __init__(self, auth_file: Path | None = None) -> None
    def _init_client(self) -> None  # Creates YTMusic(str(self.auth_file))
    def refresh_auth(self, auth_file: Path | None = None) -> bool  # Reinit client, reset cache
    def is_authenticated(self) -> tuple[bool, str]  # Cached 5 min, returns (valid, error_msg)
    def get_user_playlists(self) -> list[Playlist]
    def get_playlist_tracks(self, playlist_id: str) -> list[Track]
    def get_liked_songs(self) -> list[Track]
    def search(self, query: str) -> list[Track]
    def get_song_info(self, video_id: str) -> Track
    def get_track_rating(self, video_id: str) -> RatingState
    def set_track_rating(self, video_id: str, rating: str) -> bool
    @staticmethod
    def setup_browser() -> None  # Interactive header paste setup
```

### YTMPDaemon (`ytmpd/daemon.py`)

```python
class YTMPDaemon:
    def __init__(self)  # Loads config, detects auth file, inits all components, auto-auth setup
    def run(self) -> None  # Main loop: starts threads (incl. auto-auth), blocks until shutdown
    def _sync_loop(self)  # Background periodic sync
    def _auto_auth_loop(self)  # Background periodic cookie refresh (when enabled)
    def _attempt_auto_refresh(self) -> bool  # Extract cookies, rebuild browser.json, reinit client
    def _perform_sync(self)  # Executes single sync; reactive refresh on auth failure
    def _cmd_status(self) -> dict[str, Any]  # Returns auth/sync/auto-auth stats
    def _listen_for_triggers(self)  # Unix socket command processor
```

### FirefoxCookieExtractor (`ytmpd/cookie_extract.py`)

```python
class FirefoxCookieExtractor:
    def __init__(self, browser: str = "firefox", profile: str | None = None, container: str | None = None)
    def find_profile_dir(self) -> Path  # Auto-detect or explicit Firefox profile
    def extract_cookies(self, domain: str = ".youtube.com") -> list[dict]  # Temp-copy & query cookies.sqlite
    def _query_cookies_with_retry(self, conn, domain, origin_filter, max_retries=3, retry_delay=1.0) -> list[dict]  # Retry on locked DB
    def build_browser_json(self, output_path: Path) -> Path  # Full pipeline: extract -> validate -> write JSON
    def validate_cookies(self, cookies: list[dict]) -> bool  # Check required cookies present & not expired
```

### Notification (`ytmpd/notify.py`)

```python
def send_notification(
    title: str, message: str, urgency: str = "normal", icon: str = "dialog-warning"
) -> bool
# Rate-limited to max 1 per hour (module-level state). Returns True if sent.
```

### Config (`ytmpd/config.py`)

```python
def get_config_dir() -> Path  # Returns ~/.config/ytmpd/
def load_config() -> dict[str, Any]  # Loads YAML, merges with defaults (deep-merge for auto_auth), validates
```

### ytmusicapi auth type detection (`ytmusicapi/auth/auth_parse.py`)

```python
def determine_auth_type(auth_headers) -> AuthType
# Checks for OAuth fields first (scope, token_type, access_token, etc.)
# Then checks authorization header for "SAPISIDHASH" -> AuthType.BROWSER
# Default: AuthType.OAUTH_CUSTOM_CLIENT (causes errors if no oauth_credentials)
```

**Critical**: browser.json MUST contain an `authorization` key with `SAPISIDHASH` for ytmusicapi to recognize it as browser auth. The actual hash is recomputed at request time from `__Secure-3PAPISID` cookie + origin.

### SAPISIDHASH computation (`ytmusicapi/helpers.py:60-68`)

```python
def get_authorization(auth: str) -> str:
    # auth = "SAPISID_VALUE https://music.youtube.com"
    sha_1 = sha1()
    unix_timestamp = str(int(time.time()))
    sha_1.update((unix_timestamp + " " + auth).encode("utf-8"))
    return "SAPISIDHASH " + unix_timestamp + "_" + sha_1.hexdigest()
```

---

## Patterns & Conventions

- **Error handling**: Custom exception hierarchy rooted at `YTMPDError`. Auth errors don't retry; API errors retry with exponential backoff (2^attempt seconds, max 3 retries).
- **Rate limiting**: 100ms minimum between ytmusicapi API calls (`_rate_limit()`)
- **Thread safety**: Locks for shared state (`_sync_lock`, TrackStore locks). Daemon threads are `daemon=True`.
- **Config pattern**: YAML file merged with hardcoded defaults. `_validate_config()` normalizes paths and validates types/ranges.
- **Logging**: Python `logging` module, configurable level, file output to `~/.config/ytmpd/ytmpd.log`
- **IPC protocol**: Text commands over Unix socket (`sync_socket`), JSON responses terminated with newline.
- **CLI scripts**: Auto-detect venv and re-exec with venv Python if available.

### End-to-end auth flow:
1. Daemon `__init__` -> detects `browser.json` or `oauth.json` in config dir
2. `YTMusicClient.__init__` -> `_init_client()` -> `YTMusic(str(auth_file))`
3. ytmusicapi `parse_auth_str()` -> reads JSON -> `determine_auth_type()` -> needs "authorization" key with SAPISIDHASH
4. On each API call: `YTMusic.headers` property recomputes SAPISIDHASH from `__Secure-3PAPISID` cookie + timestamp
5. `is_authenticated()` -> tries `get_library_playlists(limit=1)` -> caches result 5 min

---

## Data Models

### browser.json format (what ytmusicapi expects)

```json
{
    "accept": "*/*",
    "accept-encoding": "gzip, deflate",
    "authorization": "SAPISIDHASH <timestamp>_<sha1hash>",
    "content-encoding": "gzip",
    "content-type": "application/json",
    "cookie": "SID=...; __Secure-3PSID=...; HSID=...; SSID=...; APISID=...; SAPISID=...; __Secure-3PAPISID=...; ...",
    "origin": "https://music.youtube.com",
    "user-agent": "Mozilla/5.0 ...",
    "x-goog-authuser": "0"
}
```

Required cookies: SID, HSID, SSID, APISID, SAPISID, __Secure-1PAPISID, __Secure-3PAPISID, __Secure-1PSID, __Secure-3PSID, __Secure-1PSIDCC, __Secure-3PSIDCC, __Secure-1PSIDTS, __Secure-3PSIDTS, LOGIN_INFO, SIDCC, PREF, VISITOR_PRIVACY_METADATA, VISITOR_INFO1_LIVE

### Firefox cookie database

- Location: `~/.mozilla/firefox/<profile>/cookies.sqlite`
- Table: `moz_cookies`
- Key columns: `name`, `value`, `host`, `expiry`, `originAttributes`, `isSecure`
- Container filter: `originAttributes = ''` for no-container (default), `^userContextId=N` for containers
- Container names: `~/.mozilla/firefox/<profile>/containers.json` -> `identities` array

### Config: proposed auto_auth section

```yaml
auto_auth:
  enabled: true
  browser: firefox-dev  # or firefox
  container: null        # null = no container, or container name string
  profile: null          # null = auto-detect, or explicit profile directory name
  refresh_interval_hours: 12  # proactive refresh schedule
```

---

## Dependencies & Integration Points

- **ytmusicapi 1.11.5**: Core dependency. Browser auth via JSON file. Auth type detection requires SAPISIDHASH in authorization header.
- **python-mpd2**: MPD client protocol
- **yt-dlp**: Stream URL extraction (also has `--cookies-from-browser` capability)
- **aiohttp**: Async HTTP for ICY proxy
- **pyyaml**: Config parsing
- **sqlite3** (stdlib): TrackStore + Firefox cookie extraction

### User's Firefox setup:
- **Browser**: Firefox Developer Edition
- **Profile**: `4wkrywqj.dev-edition-default` (in `~/.mozilla/firefox/`)
- **Containers**: Uses Multi-Account Containers. Primary Google account uses NO container (`originAttributes = ''`)
- **Containerized accounts**: ACCOUNT_002 (id=16), ACCOUNT_004 (id=12), ACCOUNT_005 (id=10)

---

## Environment & Configuration

- **Python**: 3.12+ with uv package manager
- **Virtual env**: `.venv/` in project root
- **Install**: `uv pip install -e ".[dev]"`
- **Tests**: `pytest` (541 passed, 7 pre-existing failures, 4 skipped), `pytest --cov=ytmpd`
- **Linting**: `ruff check ytmpd/`, `ruff format ytmpd/`
- **Type checking**: `mypy ytmpd/`
- **Current version**: 1.4.4

---

## Update Log

- **Phase 0 (Setup)**: Initial codebase exploration and documentation. Proved cookie extraction from Firefox Dev Edition works with ytmusicapi authentication.
- **Phase 1 (Cookie Extraction Module)**: Created `ytmpd/cookie_extract.py` with `FirefoxCookieExtractor` class. Added `CookieExtractionError` to exceptions. Added `auto_auth` config section with defaults, deep-merge, and validation. Updated `examples/config.yaml`. 33 unit tests.
- **Phase 2 (Daemon Auto-Refresh Integration)**: Added `refresh_auth()` to `YTMusicClient`. Added `_auto_auth_loop()` proactive refresh thread, `_attempt_auto_refresh()` with atomic file write, reactive refresh in `_perform_sync()` with 5-min cooldown. Updated `_cmd_status()` with auto-auth fields. State persistence for `last_auto_refresh` and `auto_refresh_failures`. 21 tests.
- **Phase 3 (Notifications, CLI, i3blocks)**: Created `ytmpd/notify.py` with rate-limited `send_notification()`. Added notification triggers in daemon after proactive/reactive refresh failures. Added `ytmpctl auth --auto` command. Updated `ytmpctl status` with auto-auth display. Updated `bin/ytmpd-status` with auth-aware color coding (red/orange). Updated `get_auth_status()` to return 3-tuple. 11 tests.
- **Phase 4 (Integration Testing & Docs)**: Added `_query_cookies_with_retry()` with locked DB retry (3 attempts, 1s delay) and corrupt DB handling. Created 25 integration tests in `tests/integration/test_auto_auth.py`. Added Auto-Authentication section to README.md. Updated project structure in README.
