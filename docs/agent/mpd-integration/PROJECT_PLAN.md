# ytmpd - MPD Integration Project Plan

**Feature/Initiative**: mpd-integration
**Type**: Major Feature / Architecture Migration
**Created**: 2025-10-17
**Estimated Total Phases**: 8

---

## 📍 Project Location

**IMPORTANT: All paths in this document are relative to the project root.**

- **Project Root**: `/home/tunc/Sync/Programs/ytmpd`
- **Verify with**: `pwd` → should output `/home/tunc/Sync/Programs/ytmpd`

When you see a path like `ytmpd/sync_engine.py`, it means `/home/tunc/Sync/Programs/ytmpd/ytmpd/sync_engine.py`

---

## Project Overview

### Purpose

Transform ytmpd from a standalone YouTube Music daemon into a smart sync service that bridges YouTube Music and MPD. This allows users to access their YouTube Music playlists through their existing MPD setup, controlled via standard mpc commands and existing i3 keybindings.

**Key Benefits**:
- No need to change existing i3 keybindings (uses mpc)
- Leverages existing MPD infrastructure (no new audio backend)
- YouTube Music playlists appear as native MPD playlists
- Actual audio playback handled by proven MPD

### Scope

**In Scope**:
- Fetching YouTube Music playlists via ytmusicapi
- Resolving YouTube video IDs to streamable audio URLs using yt-dlp
- Syncing playlists to local MPD instance
- Periodic auto-sync and manual sync triggers
- Prefixing YouTube playlists with "YT: " for easy identification
- Removing custom socket protocol in favor of MPD-native control
- CLI for YouTube-specific operations (sync, list, status)

**Out of Scope**:
- Remote MPD server support (local Unix socket only)
- MPD password authentication
- Real-time sync (sync is periodic or manual)
- Bidirectional sync (MPD → YouTube Music)
- Playlist creation/modification in YouTube Music
- Browser-based playback (replaced by MPD)

### Success Criteria

- [ ] YouTube Music playlists automatically sync to MPD with "YT: " prefix
- [ ] User can control playback via existing mpc commands
- [ ] Sync runs periodically in background (configurable interval)
- [ ] Manual sync trigger available via ytmpctl
- [ ] Stream URLs cached and refreshed before expiration
- [ ] Error handling for unavailable videos, API failures
- [ ] Existing ytmpd users can migrate smoothly
- [ ] Test coverage remains above 80%

---

## Architecture Overview

### Old Architecture (Pre-Migration)
```
ytmpctl → Unix socket → ytmpd daemon → ytmusicapi → YouTube Music
                              ↓
                        Player State
                              ↓
                        (No actual audio)
```

### New Architecture (Post-Migration)
```
YouTube Music Playlists
         ↓
    ytmpd sync daemon (periodic + manual trigger)
         ↓ (python-mpd2)
    MPD server (local Unix socket)
         ↓
    mpc commands (existing i3 keybindings)
         ↓
    Audio output
```

### Key Components

1. **MPD Client Module** (`ytmpd/mpd_client.py`): Wrapper around python-mpd2 for MPD communication
2. **YouTube Playlist Fetcher** (`ytmpd/ytmusic.py`): Enhanced to fetch user playlists
3. **Stream URL Resolver** (`ytmpd/stream_resolver.py`): Uses yt-dlp to extract audio stream URLs
4. **Playlist Sync Engine** (`ytmpd/sync_engine.py`): Core logic for syncing YT → MPD
5. **Sync Daemon** (`ytmpd/daemon.py`): Replaces socket server with periodic sync loop
6. **CLI Tool** (`bin/ytmpctl`): Simplified to sync-specific commands

### Data Flow

```
1. Fetch YouTube Music Playlists (ytmusicapi)
   ↓
2. For each playlist:
   - Get video IDs for all tracks
   - Resolve video IDs → stream URLs (yt-dlp)
   - Cache URLs with expiration
   ↓
3. Create/update MPD playlist with "YT: " prefix
   - Clear existing "YT: [name]" playlist in MPD
   - Add all stream URLs to playlist
   ↓
4. User controls playback via mpc
   - mpc load "YT: Favorites"
   - mpc play
```

### Technology Stack

- **Language**: Python 3.11+
- **Key Libraries**:
  - ytmusicapi (YouTube Music API)
  - python-mpd2 (MPD client library)
  - yt-dlp (YouTube stream URL extraction)
  - pyyaml (configuration)
- **Testing**: pytest, pytest-asyncio, pytest-cov
- **Linting/Formatting**: ruff
- **Type Checking**: mypy

---

## Phase Breakdown

> **Note for Agents**: Only read the section for your assigned phase. Reading all phases wastes context.

---

### Phase 1: Dependencies & Configuration

**Objective**: Add new dependencies (python-mpd2, yt-dlp) and extend configuration system to support MPD connection settings and sync parameters.

**Estimated Context Budget**: ~25k tokens

#### Deliverables

1. Updated `pyproject.toml` with new dependencies
2. Extended `ytmpd/config.py` with MPD and sync settings
3. Updated default config schema
4. Tests for new configuration options

#### Detailed Requirements

**1. Update pyproject.toml**

Add to dependencies section:
```toml
dependencies = [
    "ytmusicapi>=1.0.0",
    "pyyaml>=6.0",
    "python-mpd2>=3.1.0",
    "yt-dlp>=2023.0.0",
]
```

**2. Extend ytmpd/config.py**

Add new configuration fields to the config dataclass or dict:
- `mpd_socket_path`: Path to MPD Unix socket (default: `~/.config/mpd/socket`)
- `sync_interval_minutes`: How often to sync (default: 30)
- `enable_auto_sync`: Boolean to enable/disable periodic sync (default: True)
- `playlist_prefix`: Prefix for YouTube playlists in MPD (default: "YT: ")
- `stream_cache_hours`: How long to cache stream URLs (default: 5)

Update the config loading function to:
- Expand `~` in mpd_socket_path
- Validate sync_interval_minutes > 0
- Ensure playlist_prefix is a string (can be empty)

**3. Update default config schema**

Create or update `examples/config.yaml` with the new fields and helpful comments:
```yaml
# Existing ytmpd settings
socket_path: ~/.config/ytmpd/socket
state_file: ~/.config/ytmpd/state.json
log_level: INFO
log_file: ~/.config/ytmpd/ytmpd.log

# MPD integration settings
mpd_socket_path: ~/.config/mpd/socket
sync_interval_minutes: 30
enable_auto_sync: true
playlist_prefix: "YT: "
stream_cache_hours: 5
```

**4. Migration considerations**

- Ensure backward compatibility: old configs without MPD settings should still load
- Provide sensible defaults for all new fields

#### Dependencies

**Requires**: None (this is Phase 1)

**Enables**:
- Phase 2 (MPD Client Module needs config)
- Phase 4 (Stream Resolver needs cache settings)
- Phase 5 (Sync Engine needs prefix and MPD path)
- Phase 6 (Daemon needs sync interval settings)

#### Completion Criteria

- [ ] `python-mpd2` and `yt-dlp` added to pyproject.toml dependencies
- [ ] `ytmpd/config.py` updated with all new fields
- [ ] Default values provided for all new settings
- [ ] Path expansion works for `mpd_socket_path` (handles `~`)
- [ ] Config validation ensures positive sync intervals
- [ ] `examples/config.yaml` updated with new fields and documentation
- [ ] Old configs without new fields still load successfully
- [ ] Unit tests added for new config fields
- [ ] Tests verify validation (e.g., negative sync_interval rejected)
- [ ] All tests passing

#### Testing Requirements

Create or update `tests/test_config.py`:
- Test loading config with new MPD fields
- Test default values are applied when fields missing
- Test path expansion for `mpd_socket_path`
- Test validation: sync_interval_minutes must be positive
- Test loading old config (without MPD fields) doesn't fail
- Test edge cases: empty playlist_prefix, very large sync_interval

#### Notes

- Keep existing socket_path and state_file settings - they'll be deprecated in Phase 6 but keep for now
- The `mpd_socket_path` default assumes standard MPD setup; users can override
- Stream URLs from YouTube expire after ~6 hours, so cache_hours=5 gives 1-hour buffer

---

### Phase 2: MPD Client Module

**Objective**: Create a robust MPD client module that wraps python-mpd2 and provides high-level functions for playlist management and MPD communication.

**Estimated Context Budget**: ~35k tokens

#### Deliverables

1. New file `ytmpd/mpd_client.py` with MPDClient class
2. Connection management (connect, disconnect, reconnect)
3. Playlist operations (list, create, clear, add tracks)
4. Error handling and logging
5. Unit tests with mocked MPD

#### Detailed Requirements

**1. Create ytmpd/mpd_client.py**

Implement `MPDClient` class with these methods:

```python
class MPDClient:
    def __init__(self, socket_path: str):
        """Initialize client with Unix socket path"""

    def connect(self) -> None:
        """Connect to MPD via Unix socket, raise MPDConnectionError on failure"""

    def disconnect(self) -> None:
        """Cleanly disconnect from MPD"""

    def is_connected(self) -> bool:
        """Check if currently connected"""

    def list_playlists(self) -> list[str]:
        """Return list of all playlist names in MPD"""

    def playlist_exists(self, name: str) -> bool:
        """Check if a playlist with this name exists"""

    def create_or_replace_playlist(self, name: str, urls: list[str]) -> None:
        """
        Create a new playlist or replace existing one with given URLs.
        Steps:
        1. If playlist exists, delete it
        2. For each URL:
           - Add to MPD (addid)
           - Save to named playlist
        """

    def clear_playlist(self, name: str) -> None:
        """Delete a playlist by name"""

    def add_to_playlist(self, name: str, url: str) -> None:
        """Add a single URL to an existing playlist"""
```

**2. Error Handling**

Define custom exceptions in `ytmpd/exceptions.py`:
- `MPDConnectionError`: Raised when can't connect to MPD
- `MPDPlaylistError`: Raised on playlist operation failures

Handle these scenarios:
- Socket file doesn't exist → MPDConnectionError with helpful message
- MPD not running → MPDConnectionError
- Network timeout → Retry once, then raise
- Invalid URL when adding → Log warning, skip track

**3. Logging**

Use Python's logging module:
- Log connection attempts (INFO level)
- Log connection failures (ERROR level)
- Log playlist operations (DEBUG level)
- Log skipped tracks with reason (WARNING level)

**4. Connection Management**

- Use context manager support for automatic cleanup
- Implement reconnection logic with exponential backoff
- Detect stale connections and auto-reconnect

#### Dependencies

**Requires**:
- Phase 1: Configuration system with mpd_socket_path

**Enables**:
- Phase 5: Sync Engine needs MPD client to update playlists
- Phase 6: Daemon needs MPD client for sync operations

#### Completion Criteria

- [ ] `ytmpd/mpd_client.py` created with MPDClient class
- [ ] All listed methods implemented
- [ ] Connection handling works with Unix socket
- [ ] Custom exceptions defined in `ytmpd/exceptions.py`
- [ ] Comprehensive error handling for common failure modes
- [ ] Logging added at appropriate levels
- [ ] Context manager support (`__enter__`, `__exit__`)
- [ ] Unit tests with mocked MPD client
- [ ] Tests cover success cases and error cases
- [ ] All tests passing
- [ ] Type hints on all methods
- [ ] Docstrings following Google style

#### Testing Requirements

Create `tests/test_mpd_client.py`:
- Mock the underlying python-mpd2 MPDClient
- Test successful connection to Unix socket
- Test connection failure handling (socket missing, MPD not running)
- Test list_playlists returns correct data
- Test create_or_replace_playlist creates new playlist
- Test create_or_replace_playlist replaces existing playlist
- Test playlist_exists correctly identifies existing playlists
- Test error handling for invalid URLs
- Test context manager properly disconnects
- Test reconnection logic on stale connection

Mock example:
```python
from unittest.mock import Mock, patch

@patch('ytmpd.mpd_client.MPDClient')
def test_connect_success(mock_mpd):
    client = MPDClient('/path/to/socket')
    client.connect()
    mock_mpd.return_value.connect.assert_called_once()
```

#### Notes

- python-mpd2 uses Unix sockets via `connect(socket_path)`
- MPD playlist operations: `playlist()`, `playlistid()`, `rm()`, `save()`
- Test with a real local MPD instance in integration tests (Phase 8)
- Consider connection pooling if performance issues arise (future enhancement)

---

### Phase 3: YouTube Playlist Fetcher

**Objective**: Enhance the YouTube Music module to fetch user's playlists and their track details, providing the data needed for sync operations.

**Estimated Context Budget**: ~30k tokens

#### Deliverables

1. Enhanced `ytmpd/ytmusic.py` with playlist fetching methods
2. Data structures for playlists and tracks
3. Error handling for API failures
4. Unit tests with mocked ytmusicapi responses

#### Detailed Requirements

**1. Enhance ytmpd/ytmusic.py**

Add or update the YTMusic wrapper class with these methods:

```python
class YTMusicClient:
    def __init__(self, auth_path: str):
        """Initialize with path to browser.json auth file"""

    def get_user_playlists(self) -> list[Playlist]:
        """
        Fetch all user playlists from YouTube Music.
        Returns list of Playlist objects with id, name, track_count.
        """

    def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        """
        Get all tracks for a specific playlist.
        Returns list of Track objects with video_id, title, artist.
        """
```

**2. Data Structures**

Define dataclasses or TypedDicts for clean data handling:

```python
@dataclass
class Playlist:
    id: str  # YouTube playlist ID
    name: str  # Display name
    track_count: int

@dataclass
class Track:
    video_id: str  # YouTube video ID (e.g., "dQw4w9WgXcQ")
    title: str
    artist: str
```

**3. Error Handling**

Handle these scenarios:
- Auth file missing → Raise helpful error directing to setup-browser
- API rate limiting → Log warning, return partial results
- Network errors → Retry with exponential backoff (3 attempts max)
- Malformed API responses → Log error, skip invalid entries

**4. Filtering**

- Skip playlists with 0 tracks
- Skip tracks without video_id
- Log skipped items at DEBUG level

**5. Caching Consideration**

For now, no caching (fetch fresh each time). Note in code comments that playlist caching could be added as future enhancement.

#### Dependencies

**Requires**:
- Phase 1: Configuration for auth file path (existing)

**Enables**:
- Phase 5: Sync Engine needs playlist data

#### Completion Criteria

- [ ] YTMusicClient class in `ytmpd/ytmusic.py` has new methods
- [ ] Playlist and Track dataclasses defined
- [ ] `get_user_playlists()` returns all user playlists
- [ ] `get_playlist_tracks()` returns all tracks for a playlist
- [ ] Empty playlists filtered out
- [ ] Tracks without video_id filtered out
- [ ] Error handling for auth failures
- [ ] Retry logic for network errors
- [ ] Comprehensive logging
- [ ] Unit tests with mocked ytmusicapi
- [ ] All tests passing
- [ ] Type hints on all methods
- [ ] Docstrings added

#### Testing Requirements

Create `tests/test_ytmusic.py` or extend existing:

Mock ytmusicapi responses:
```python
from unittest.mock import Mock, patch

@patch('ytmusicapi.YTMusic')
def test_get_user_playlists(mock_ytmusic):
    mock_ytmusic.return_value.get_library_playlists.return_value = [
        {'playlistId': 'PL123', 'title': 'Favorites', 'count': 50},
        {'playlistId': 'PL456', 'title': 'Workout', 'count': 30},
    ]

    client = YTMusicClient('~/.config/ytmpd/browser.json')
    playlists = client.get_user_playlists()

    assert len(playlists) == 2
    assert playlists[0].name == 'Favorites'
```

Tests to include:
- Successful fetch of playlists
- Successful fetch of tracks
- Handle empty playlist list
- Filter out playlists with 0 tracks
- Handle network errors with retry
- Handle auth failure
- Handle malformed API response

#### Notes

- ytmusicapi methods: `get_library_playlists()`, `get_playlist()`
- YouTube video IDs are typically 11 characters (e.g., "dQw4w9WgXcQ")
- Some tracks may not have video_ids (podcasts, etc.) - skip these
- Consider rate limiting in future if syncing many large playlists

---

### Phase 4: Stream URL Resolver

**Objective**: Create a module that uses yt-dlp to extract direct audio stream URLs from YouTube video IDs, with caching to avoid repeated extraction.

**Estimated Context Budget**: ~40k tokens

#### Deliverables

1. New file `ytmpd/stream_resolver.py` with StreamResolver class
2. URL extraction using yt-dlp
3. In-memory URL cache with expiration
4. Error handling for unavailable/restricted videos
5. Unit tests

#### Detailed Requirements

**1. Create ytmpd/stream_resolver.py**

```python
class StreamResolver:
    def __init__(self, cache_hours: int = 5):
        """Initialize with cache duration in hours"""
        self._cache: dict[str, CachedURL] = {}
        self._cache_hours = cache_hours

    def resolve_video_id(self, video_id: str) -> str | None:
        """
        Get streamable audio URL for a YouTube video ID.
        Returns URL string or None if unavailable.
        Checks cache first, extracts with yt-dlp if cache miss/expired.
        """

    def resolve_batch(self, video_ids: list[str]) -> dict[str, str]:
        """
        Resolve multiple video IDs efficiently.
        Returns dict mapping video_id -> URL (only successful resolutions).
        """

    def _extract_url(self, video_id: str) -> str | None:
        """
        Use yt-dlp to extract stream URL.
        Private method, not exposed to callers.
        """

    def _is_cache_valid(self, video_id: str) -> bool:
        """Check if cached URL is still valid (not expired)"""

    def clear_cache(self) -> None:
        """Clear all cached URLs"""
```

**2. Data Structures**

```python
@dataclass
class CachedURL:
    url: str
    cached_at: datetime
    video_id: str
```

**3. yt-dlp Integration**

Use yt-dlp Python API (not subprocess):

```python
import yt_dlp

ydl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(f'https://youtube.com/watch?v={video_id}', download=False)
    url = info['url']
```

**4. Error Handling**

Handle these cases gracefully:
- Video unavailable → Return None, log at INFO
- Video region locked → Return None, log at INFO
- Private/deleted video → Return None, log at INFO
- yt-dlp extraction fails → Return None, log at WARNING
- Network errors → Retry once, then return None

Never crash the sync process due to a single video failure.

**5. Caching Strategy**

- Cache in-memory (dict) for current daemon session
- Cache key: video_id
- Cache expiration: configurable hours (default 5)
- Check expiration before returning cached URL
- No persistent cache (could be future enhancement)

**6. Performance Considerations**

- `resolve_batch()` resolves in parallel using threads or async
- Limit concurrency to avoid rate limiting (10 concurrent max)
- Log progress for large batches (every 10 videos)

#### Dependencies

**Requires**:
- Phase 1: Configuration for cache_hours setting

**Enables**:
- Phase 5: Sync Engine needs stream URLs for MPD playlists

#### Completion Criteria

- [ ] `ytmpd/stream_resolver.py` created with StreamResolver class
- [ ] CachedURL dataclass defined
- [ ] `resolve_video_id()` extracts URL using yt-dlp
- [ ] Caching implemented with expiration checking
- [ ] `resolve_batch()` handles multiple video IDs efficiently
- [ ] Graceful error handling for all failure modes
- [ ] Unavailable videos return None (don't crash)
- [ ] Logging for failures and cache hits/misses
- [ ] Unit tests with mocked yt-dlp
- [ ] Performance tests for batch resolution
- [ ] All tests passing
- [ ] Type hints and docstrings

#### Testing Requirements

Create `tests/test_stream_resolver.py`:

Mock yt-dlp extraction:
```python
from unittest.mock import Mock, patch

@patch('yt_dlp.YoutubeDL')
def test_resolve_video_id_success(mock_ydl):
    mock_ydl.return_value.__enter__.return_value.extract_info.return_value = {
        'url': 'https://example.com/audio.m4a'
    }

    resolver = StreamResolver(cache_hours=5)
    url = resolver.resolve_video_id('dQw4w9WgXcQ')

    assert url == 'https://example.com/audio.m4a'
```

Tests to include:
- Successful URL extraction
- Cache hit returns cached URL
- Cache miss triggers extraction
- Expired cache triggers re-extraction
- Unavailable video returns None
- Region locked video returns None
- Batch resolution processes multiple IDs
- Cache is respected in batch operations
- Clear cache works

#### Notes

- YouTube stream URLs expire after ~6 hours
- yt-dlp is actively maintained and handles YouTube changes
- Consider persistent cache (SQLite) as future enhancement
- Batch resolution critical for performance with large playlists
- May hit YouTube rate limits if syncing 100+ playlists - log warnings

---

### Phase 5: Playlist Sync Engine

**Objective**: Create the core sync engine that orchestrates fetching YouTube playlists, resolving URLs, and updating MPD playlists with proper prefixing.

**Estimated Context Budget**: ~45k tokens

#### Deliverables

1. New file `ytmpd/sync_engine.py` with SyncEngine class
2. Full sync logic (YouTube → MPD)
3. Playlist prefixing ("YT: ")
4. Incremental sync tracking
5. Sync statistics and reporting
6. Unit and integration tests

#### Detailed Requirements

**1. Create ytmpd/sync_engine.py**

```python
class SyncEngine:
    def __init__(
        self,
        ytmusic_client: YTMusicClient,
        mpd_client: MPDClient,
        stream_resolver: StreamResolver,
        playlist_prefix: str = "YT: "
    ):
        """Initialize with dependencies"""

    def sync_all_playlists(self) -> SyncResult:
        """
        Full sync of all YouTube playlists to MPD.

        Steps:
        1. Fetch all YouTube playlists
        2. For each playlist:
           a. Get tracks
           b. Resolve video IDs to stream URLs
           c. Create/update MPD playlist with prefix
        3. Return statistics
        """

    def sync_single_playlist(self, playlist_name: str) -> SyncResult:
        """Sync a specific playlist by name"""

    def get_sync_preview(self) -> SyncPreview:
        """
        Preview what would be synced without making changes.
        Returns counts of playlists and tracks.
        """
```

**2. Data Structures**

```python
@dataclass
class SyncResult:
    success: bool
    playlists_synced: int
    playlists_failed: int
    tracks_added: int
    tracks_failed: int
    duration_seconds: float
    errors: list[str]

@dataclass
class SyncPreview:
    youtube_playlists: list[str]
    total_tracks: int
    existing_mpd_playlists: list[str]
```

**3. Sync Logic**

For each YouTube playlist:
1. Get playlist name and tracks from YTMusicClient
2. Resolve all video IDs to stream URLs using StreamResolver
3. Skip tracks that fail to resolve (log warning)
4. Create MPD playlist name: `{prefix}{playlist_name}`
5. Call `mpd_client.create_or_replace_playlist(mpd_name, urls)`
6. Track statistics

**4. Error Handling**

- If entire playlist fails (no tracks resolved), log ERROR and skip
- If some tracks fail, sync playlist with available tracks
- Never crash mid-sync - catch exceptions per playlist
- Accumulate errors in SyncResult for reporting

**5. Progress Logging**

Log at INFO level:
- "Starting sync of X playlists"
- "Syncing playlist: {name} ({n}/{total})"
- "Resolved {x}/{y} tracks for {name}"
- "Sync complete: {playlists_synced} playlists, {tracks_added} tracks"

**6. Incremental Sync (Future Enhancement)**

For now, always do full sync (replace all playlists).
Add TODO comments for tracking changes:
- Store hash of playlist contents
- Only sync if hash changed
- This can be Phase 9 if needed

#### Dependencies

**Requires**:
- Phase 1: Configuration for playlist_prefix
- Phase 2: MPD Client
- Phase 3: YouTube Playlist Fetcher
- Phase 4: Stream URL Resolver

**Enables**:
- Phase 6: Daemon needs sync engine to perform syncs

#### Completion Criteria

- [ ] `ytmpd/sync_engine.py` created with SyncEngine class
- [ ] SyncResult and SyncPreview dataclasses defined
- [ ] `sync_all_playlists()` implements full sync logic
- [ ] Playlist prefix applied to all YouTube playlists
- [ ] Failed tracks skipped gracefully
- [ ] Failed playlists logged but don't stop sync
- [ ] Comprehensive statistics tracked
- [ ] Progress logging at appropriate levels
- [ ] `get_sync_preview()` shows what would be synced
- [ ] Unit tests with mocked dependencies
- [ ] Integration tests with real components
- [ ] All tests passing
- [ ] Type hints and docstrings

#### Testing Requirements

Create `tests/test_sync_engine.py`:

```python
def test_sync_all_playlists():
    # Mock dependencies
    ytmusic = Mock()
    ytmusic.get_user_playlists.return_value = [
        Playlist(id='PL1', name='Favorites', track_count=3)
    ]
    ytmusic.get_playlist_tracks.return_value = [
        Track(video_id='vid1', title='Song 1', artist='Artist 1'),
        Track(video_id='vid2', title='Song 2', artist='Artist 2'),
    ]

    mpd = Mock()
    resolver = Mock()
    resolver.resolve_batch.return_value = {
        'vid1': 'http://example.com/1.m4a',
        'vid2': 'http://example.com/2.m4a',
    }

    engine = SyncEngine(ytmusic, mpd, resolver, prefix="YT: ")
    result = engine.sync_all_playlists()

    assert result.success
    assert result.playlists_synced == 1
    assert result.tracks_added == 2
    mpd.create_or_replace_playlist.assert_called_once_with(
        'YT: Favorites',
        ['http://example.com/1.m4a', 'http://example.com/2.m4a']
    )
```

Tests to include:
- Successful sync of single playlist
- Successful sync of multiple playlists
- Handle playlist with no resolvable tracks (skip)
- Handle playlist with some failed tracks (partial sync)
- Prefix applied correctly
- Statistics tracked accurately
- Preview mode doesn't modify MPD
- Error handling for each dependency failure

#### Notes

- Sync can be slow for large playlists (many yt-dlp extractions)
- Consider adding progress callbacks for UI feedback (future)
- Stream URL caching critical for performance on subsequent syncs
- Empty playlists (all tracks failed) should be skipped, not created in MPD

---

### Phase 6: Daemon Migration

**Objective**: Transform ytmpd from a socket-based command server to a sync daemon that periodically syncs YouTube playlists to MPD and responds to manual sync triggers.

**Estimated Context Budget**: ~35k tokens

#### Deliverables

1. Refactored `ytmpd/daemon.py` as sync daemon
2. Removed old socket server code
3. Periodic sync loop with configurable interval
4. Manual sync trigger mechanism (simple socket or signal)
5. State persistence (last sync time, errors)
6. Enhanced logging and error recovery

#### Detailed Requirements

**1. Refactor ytmpd/daemon.py**

Transform the daemon to:
- Initialize all sync components (YTMusicClient, MPDClient, StreamResolver, SyncEngine)
- Run periodic sync loop in background
- Listen for manual sync triggers
- Persist state between runs

```python
class YTMPDaemon:
    def __init__(self, config: Config):
        """Initialize with config"""
        self.config = config
        self.ytmusic_client = YTMusicClient(config.auth_file)
        self.mpd_client = MPDClient(config.mpd_socket_path)
        self.stream_resolver = StreamResolver(config.stream_cache_hours)
        self.sync_engine = SyncEngine(
            self.ytmusic_client,
            self.mpd_client,
            self.stream_resolver,
            config.playlist_prefix
        )
        self.state = self._load_state()

    def run(self) -> None:
        """Main daemon loop"""

    def _sync_loop(self) -> None:
        """Background thread for periodic sync"""

    def _perform_sync(self) -> None:
        """Execute sync and update state"""

    def _listen_for_triggers(self) -> None:
        """Listen for manual sync commands"""
```

**2. Remove Old Code**

Remove from ytmpd:
- `ytmpd/server.py` (socket server) - delete entirely
- `ytmpd/player.py` (player state) - delete entirely
- Old command handling logic from daemon.py
- References to old socket protocol

Keep:
- `ytmpd/config.py` (updated in Phase 1)
- `ytmpd/ytmusic.py` (enhanced in Phase 3)
- `ytmpd/__main__.py` (update to use new daemon)

**3. Periodic Sync**

- Run sync loop in separate thread or async task
- Sleep for `sync_interval_minutes` between syncs
- Handle exceptions in sync (log, don't crash daemon)
- Skip sync if previous one still running

**4. Manual Sync Trigger**

Simple approach - listen on Unix socket for "sync" command:
- Keep minimal socket listener (much simpler than old server)
- Accept connections on `~/.config/ytmpd/sync_socket`
- Read command: "sync", "status", or "quit"
- Respond with result
- This allows ytmpctl to trigger syncs

**5. State Persistence**

Store in `~/.config/ytmpd/sync_state.json`:
```json
{
    "last_sync": "2025-10-17T14:30:00Z",
    "last_sync_result": {
        "success": true,
        "playlists_synced": 5,
        "tracks_added": 150,
        "errors": []
    },
    "daemon_start_time": "2025-10-17T12:00:00Z"
}
```

**6. Logging**

- Log daemon startup/shutdown (INFO)
- Log each sync start/end (INFO)
- Log sync results (INFO)
- Log errors with full tracebacks (ERROR)
- Rotate log files (keep last 7 days)

**7. Signal Handling**

- SIGTERM/SIGINT → Graceful shutdown (finish current sync)
- SIGHUP → Reload config and trigger immediate sync

#### Dependencies

**Requires**:
- Phase 1: Config
- Phase 2: MPD Client
- Phase 3: YouTube Client
- Phase 4: Stream Resolver
- Phase 5: Sync Engine

**Enables**:
- Phase 7: CLI needs daemon running to trigger syncs

#### Completion Criteria

- [ ] `ytmpd/daemon.py` refactored as sync daemon
- [ ] Old server.py and player.py removed
- [ ] Periodic sync loop implemented
- [ ] Manual sync trigger works via socket
- [ ] State persisted to sync_state.json
- [ ] Graceful shutdown on signals
- [ ] Config reload on SIGHUP
- [ ] Comprehensive logging
- [ ] Error recovery (sync failures don't crash daemon)
- [ ] `ytmpd/__main__.py` updated to use new daemon
- [ ] Integration tests with real components
- [ ] All tests passing

#### Testing Requirements

Create `tests/test_daemon.py`:

```python
def test_daemon_startup():
    config = Mock()
    daemon = YTMPDaemon(config)
    # Verify components initialized
    assert daemon.sync_engine is not None

def test_perform_sync():
    daemon = YTMPDaemon(mock_config)
    daemon._perform_sync()
    # Verify state updated
    assert daemon.state['last_sync'] is not None

def test_manual_trigger():
    # Start daemon
    # Send "sync" command via socket
    # Verify sync triggered
```

Tests to include:
- Daemon initialization
- Periodic sync executes
- Manual trigger works
- State persistence
- Error recovery (failed sync doesn't crash)
- Signal handling
- Config reload

Integration test:
- Start daemon
- Wait for first sync
- Verify MPD has playlists
- Trigger manual sync
- Stop daemon gracefully

#### Notes

- First sync on daemon startup should happen immediately
- Consider systemd service file for auto-start (document in Phase 8)
- Log rotation prevents disk fill on long-running daemon
- Socket for manual trigger simpler than implementing MPD protocol commands

---

### Phase 7: CLI Migration

**Objective**: Simplify ytmpctl to focus on sync-specific commands (sync, status, list-playlists), removing playback commands that are now handled by mpc.

**Estimated Context Budget**: ~30k tokens

#### Deliverables

1. Refactored `bin/ytmpctl` with new command set
2. Removed playback commands
3. Added sync-specific commands
4. Updated help text and documentation
5. Tests for CLI commands

#### Detailed Requirements

**1. New Command Set**

```bash
ytmpctl sync              # Trigger immediate sync
ytmpctl status            # Show sync status and stats
ytmpctl list-playlists    # List YouTube playlists available
ytmpctl help              # Show help
```

**2. Remove Old Commands**

Remove these commands (users use mpc instead):
- `play <query>`
- `pause`
- `resume`
- `stop`
- `next`
- `prev`
- `queue`
- `search <query>` (may keep if useful for finding playlists)

**3. Implementation**

```python
#!/usr/bin/env python3
import socket
import json
import sys

SYNC_SOCKET = os.path.expanduser('~/.config/ytmpd/sync_socket')

def send_command(command: str) -> dict:
    """Send command to daemon via socket, return response"""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(SYNC_SOCKET)
        sock.sendall(command.encode() + b'\n')
        response = sock.recv(4096).decode()
        return json.loads(response)

def cmd_sync():
    """Trigger immediate sync"""
    print("Triggering sync...")
    result = send_command('sync')
    if result['success']:
        print(f"✓ Synced {result['playlists_synced']} playlists, {result['tracks_added']} tracks")
    else:
        print(f"✗ Sync failed: {result['errors']}")
        sys.exit(1)

def cmd_status():
    """Show sync status"""
    result = send_command('status')
    print(f"Last sync: {result['last_sync']}")
    print(f"Playlists: {result['playlists_synced']}")
    print(f"Tracks: {result['tracks_added']}")
    if result['errors']:
        print(f"Errors: {len(result['errors'])}")

def cmd_list_playlists():
    """List YouTube playlists"""
    result = send_command('list')
    for playlist in result['playlists']:
        print(f"- {playlist['name']} ({playlist['track_count']} tracks)")

def cmd_help():
    """Show help"""
    print("""ytmpctl - YouTube Music to MPD sync control

Usage:
    ytmpctl sync              Trigger immediate sync
    ytmpctl status            Show sync status
    ytmpctl list-playlists    List YouTube Music playlists
    ytmpctl help              Show this help

Playback Control:
    Use mpc for playback control:
        mpc load "YT: Favorites"    Load YouTube playlist
        mpc play                     Play
        mpc pause                    Pause
        mpc next                     Next track
        mpc prev                     Previous track
        mpc status                   Show playback status

Configuration:
    ~/.config/ytmpd/config.yaml
    ~/.config/ytmpd/browser.json (auth)

Logs:
    ~/.config/ytmpd/ytmpd.log
""")

if __name__ == '__main__':
    # Parse args and dispatch
```

**4. Error Handling**

- Socket doesn't exist → "Daemon not running. Start with: python -m ytmpd &"
- Connection refused → Same message
- Invalid command → Show help
- Timeout → "Daemon not responding"

**5. Output Formatting**

- Use color if terminal supports it (green for success, red for errors)
- Use Unicode symbols (✓, ✗) if terminal supports it
- Fall back to plain text otherwise

**6. Help Text**

Include:
- Brief description of each command
- Mention that playback is via mpc
- Example workflow:
  1. Start daemon: `python -m ytmpd &`
  2. Wait for initial sync or trigger: `ytmpctl sync`
  3. Load playlist: `mpc load "YT: Favorites"`
  4. Play: `mpc play`

#### Dependencies

**Requires**:
- Phase 6: Daemon with sync socket

**Enables**:
- Phase 8: End-to-end testing needs CLI

#### Completion Criteria

- [ ] `bin/ytmpctl` refactored with new commands
- [ ] Old playback commands removed
- [ ] `sync` command triggers immediate sync
- [ ] `status` command shows last sync info
- [ ] `list-playlists` command shows YouTube playlists
- [ ] `help` command shows comprehensive help
- [ ] Error handling for daemon not running
- [ ] Output formatting (color, symbols)
- [ ] Help text includes mpc examples
- [ ] Script executable and has shebang
- [ ] Unit tests for command parsing
- [ ] Integration tests with running daemon
- [ ] All tests passing

#### Testing Requirements

Create `tests/test_ytmpctl.py`:

```python
def test_sync_command(mock_socket):
    # Mock socket communication
    # Call cmd_sync()
    # Verify correct command sent
    # Verify output formatting

def test_daemon_not_running():
    # Mock socket connection failure
    # Verify helpful error message
```

Tests to include:
- Each command sends correct socket message
- Response parsing works
- Error messages helpful
- Help text comprehensive
- Color formatting works
- Unicode fallback works

Integration test:
- Start daemon
- Run `ytmpctl sync`
- Verify sync triggered
- Run `ytmpctl status`
- Verify correct output

#### Notes

- Keep script simple and focused
- Users transition to mpc for playback
- Consider shell completions as future enhancement
- May want to keep `search` command for finding YouTube content

---

### Phase 8: End-to-End Testing & Documentation

**Objective**: Comprehensive integration tests, update all documentation for the new architecture, and provide migration guide for existing users.

**Estimated Context Budget**: ~30k tokens

#### Deliverables

1. Integration tests with real MPD instance
2. End-to-end workflow test
3. Updated README.md with new architecture
4. Migration guide for existing users
5. Troubleshooting guide
6. Updated example configs

#### Detailed Requirements

**1. Integration Tests**

Create `tests/integration/test_full_workflow.py`:

```python
def test_full_sync_workflow():
    """
    Test complete workflow:
    1. Start MPD (test instance)
    2. Start ytmpd daemon
    3. Wait for sync
    4. Verify playlists in MPD
    5. Load playlist via mpc
    6. Verify playback works
    7. Stop daemon cleanly
    """
```

Test with:
- Local MPD instance (can be test/docker setup)
- Mock or test YouTube Music account
- Small test playlists (avoid rate limits)

**2. Update README.md**

Rewrite README with new architecture:

**Architecture section**:
```
YouTube Music Playlists
         ↓
    ytmpd sync daemon
         ↓
    MPD server
         ↓
    mpc commands (i3 keybindings)
```

**Installation section**:
- Add note about MPD requirement
- Update config.yaml example with MPD settings

**Usage section**:
```bash
# Start daemon
python -m ytmpd &

# Wait for sync or trigger manually
ytmpctl sync

# Load YouTube playlist in MPD
mpc load "YT: Favorites"

# Control playback
mpc play
mpc pause
mpc next
```

**i3 Integration section**:
- Update keybindings to use mpc instead of ytmpctl
```
bindsym $mod+Shift+p exec --no-startup-id mpc toggle
bindsym $mod+Shift+n exec --no-startup-id mpc next
bindsym $mod+Shift+b exec --no-startup-id mpc prev
```

**3. Migration Guide**

Create `docs/MIGRATION.md`:

```markdown
# Migration Guide: ytmpd v1 → v2 (MPD Integration)

## What Changed

- ytmpd is now a sync daemon (not a command server)
- Playback handled by MPD (not ytmpd)
- Use mpc for playback control (not ytmpctl)
- YouTube playlists appear as MPD playlists

## Migration Steps

1. Update dependencies: `uv pip install -e ".[dev]"`
2. Update config.yaml (add MPD settings)
3. Stop old ytmpd: `pkill -f "python -m ytmpd"`
4. Start new ytmpd: `python -m ytmpd &`
5. Update i3 keybindings to use mpc
6. Load YouTube playlist: `mpc load "YT: Favorites"`

## Breaking Changes

- ytmpctl play/pause/next removed (use mpc)
- Socket protocol changed (now sync-focused)
- State file format changed

## Backward Compatibility

- Old config.yaml still loads (new fields use defaults)
- Can run new ytmpd alongside old MPD setup
```

**4. Troubleshooting Guide**

Add to README troubleshooting section:

```markdown
## Troubleshooting

### Daemon won't start
- Check MPD is running: `mpc status`
- Check MPD socket path: `ls ~/.config/mpd/socket`
- Check logs: `tail -f ~/.config/ytmpd/ytmpd.log`

### No playlists in MPD
- Check sync status: `ytmpctl status`
- Trigger manual sync: `ytmpctl sync`
- Check YouTube auth: `ls ~/.config/ytmpd/browser.json`

### Playback not working
- Check MPD status: `mpc status`
- Check MPD outputs: `mpc outputs`
- Check MPD logs

### Stream URLs expired
- URLs expire after ~6 hours
- Daemon re-syncs periodically
- Manual sync: `ytmpctl sync`
```

**5. Example Configs**

Update `examples/config.yaml`:
```yaml
# YouTube Music auth
auth_file: ~/.config/ytmpd/browser.json

# Logging
log_level: INFO
log_file: ~/.config/ytmpd/ytmpd.log

# MPD integration
mpd_socket_path: ~/.config/mpd/socket
sync_interval_minutes: 30
enable_auto_sync: true
playlist_prefix: "YT: "
stream_cache_hours: 5
```

Update `examples/i3-config`:
```
# ytmpd + MPD playback controls
bindsym $mod+Shift+p exec --no-startup-id mpc toggle
bindsym $mod+Shift+s exec --no-startup-id mpc stop
bindsym $mod+Shift+n exec --no-startup-id mpc next
bindsym $mod+Shift+b exec --no-startup-id mpc prev

# Refresh i3blocks
bindsym $mod+Shift+p exec --no-startup-id killall -SIGUSR1 i3blocks
```

Update `examples/i3blocks-config`:
- May need to point to MPD status instead of ytmpd-status
- Or update bin/ytmpd-status to read MPD status

**6. Performance Testing**

Test with realistic scenarios:
- 10 playlists, 50 tracks each
- 50 playlists, 20 tracks each
- Measure sync time
- Monitor memory usage
- Check for memory leaks on long runs

**7. Code Coverage**

- Run pytest with coverage: `pytest --cov=ytmpd --cov-report=html`
- Ensure coverage above 80%
- Document any intentionally untested code

#### Dependencies

**Requires**:
- All previous phases (1-7)

**Enables**:
- Project complete and ready for use!

#### Completion Criteria

- [ ] Integration tests implemented and passing
- [ ] End-to-end workflow test passes
- [ ] README.md fully updated with new architecture
- [ ] Migration guide created
- [ ] Troubleshooting section comprehensive
- [ ] Example configs updated
- [ ] i3 integration examples updated
- [ ] Performance testing done
- [ ] Test coverage above 80%
- [ ] All linting passes (ruff)
- [ ] All type checking passes (mypy)
- [ ] Documentation reviewed for accuracy

#### Testing Requirements

Integration tests:
- Full workflow with real MPD
- Multi-playlist sync
- URL expiration and re-sync
- Daemon restart preserves state
- Manual sync trigger works
- Error recovery (MPD disconnect, etc.)

Performance tests:
- Large playlist (100+ tracks)
- Many playlists (50+)
- Sync time measurement
- Memory leak check (run for 24h)

#### Notes

- Integration tests may need Docker setup for MPD
- Consider CI/CD setup for automated testing
- Performance benchmarks useful for future optimization
- Documentation is critical for user adoption
- Consider adding FAQ section to README

---

## Phase Dependencies Graph

```
Phase 1 (Config & Dependencies)
    ├→ Phase 2 (MPD Client)
    ├→ Phase 3 (YouTube Fetcher)
    └→ Phase 4 (Stream Resolver)
            ↓
    Phase 5 (Sync Engine)
            ↓
    Phase 6 (Daemon Migration)
            ↓
    Phase 7 (CLI Migration)
            ↓
    Phase 8 (Testing & Docs)
```

**Critical Path**: 1 → 2,3,4 → 5 → 6 → 7 → 8

Phases 2, 3, 4 can be worked on in parallel after Phase 1 completes.

---

## Cross-Cutting Concerns

### Code Style

- Follow PEP 8 for Python
- Use type hints for all function signatures
- Maximum line length: 100 characters
- Use docstrings for all public functions (Google style)
- Format with: `ruff format ytmpd/`
- Lint with: `ruff check ytmpd/`

### Error Handling

- Use custom exceptions defined in `ytmpd/exceptions.py`
- Always log errors before raising
- Provide helpful error messages with context
- Never crash daemon due to single sync failure

### Logging

- Use Python's `logging` module
- Log level configurable via config
- Format: `[timestamp] [level] [module] message`
- Rotate log files (keep 7 days)
- Levels:
  - DEBUG: Detailed operation info
  - INFO: Sync start/end, statistics
  - WARNING: Skipped tracks, retries
  - ERROR: Failures with tracebacks

### Configuration

- All config in `~/.config/ytmpd/config.yaml`
- Loaded via `ytmpd/config.py`
- Sensible defaults for all fields
- Validate on load (fail fast)
- Support environment variable overrides

### Testing Strategy

- Unit tests for all modules (mock external dependencies)
- Integration tests for workflows (real components)
- Minimum 80% code coverage
- Use pytest with fixtures for common setups
- Test error paths as thoroughly as success paths

### Security

- Never log authentication tokens
- Validate all external inputs (API responses)
- Use secure file permissions for auth files (600)
- No arbitrary code execution

---

## Integration Points

### YTMusic ↔ Sync Engine
- Sync Engine calls YTMusicClient to fetch playlists
- Handles ytmusicapi exceptions gracefully

### Stream Resolver ↔ Sync Engine
- Sync Engine passes video IDs in batches
- Resolver returns dict of successful resolutions

### MPD Client ↔ Sync Engine
- Sync Engine calls MPDClient to create playlists
- Handles MPD connection errors

### Daemon ↔ All Components
- Daemon initializes and orchestrates all components
- Daemon handles lifecycle and error recovery

---

## Data Schemas

### Configuration Schema (config.yaml)

```yaml
# YouTube Music settings
auth_file: ~/.config/ytmpd/browser.json

# Logging
log_level: INFO
log_file: ~/.config/ytmpd/ytmpd.log

# MPD Integration
mpd_socket_path: ~/.config/mpd/socket
sync_interval_minutes: 30
enable_auto_sync: true
playlist_prefix: "YT: "
stream_cache_hours: 5
```

### Sync State Schema (sync_state.json)

```json
{
    "last_sync": "2025-10-17T14:30:00Z",
    "last_sync_result": {
        "success": true,
        "playlists_synced": 5,
        "playlists_failed": 0,
        "tracks_added": 150,
        "tracks_failed": 3,
        "duration_seconds": 45.2,
        "errors": []
    },
    "daemon_start_time": "2025-10-17T12:00:00Z"
}
```

### Socket Protocol (sync_socket)

Simple text protocol:

**Commands:**
```
sync          → Trigger sync
status        → Get status
list          → List YouTube playlists
quit          → Shutdown daemon
```

**Responses:**
```json
{
    "success": true,
    "data": { ... }
}
```

---

## Glossary

**MPD**: Music Player Daemon - A flexible, powerful server-side music player
**mpc**: MPD client - Command-line tool to control MPD
**yt-dlp**: YouTube downloader with stream URL extraction
**ytmusicapi**: Unofficial YouTube Music API library
**Stream URL**: Direct HTTP URL to audio file (expires after ~6 hours)
**Sync**: Process of fetching YouTube playlists and updating MPD
**Playlist Prefix**: Text prepended to YouTube playlists in MPD (default "YT: ")

---

## Future Enhancements

**Phase 9: Performance Optimization** (if needed)
- Persistent URL cache (SQLite)
- Incremental sync (only changed playlists)
- Parallel playlist syncing
- Playlist diff algorithm

**Phase 10: Advanced Features**
- Bidirectional sync (MPD → YouTube Music)
- Playlist creation/editing in YouTube Music
- Search command for YouTube content
- Watch for MPD events and update state

**Phase 11: UI/UX**
- TUI (textual) for monitoring sync
- Web dashboard for configuration
- Desktop notifications for sync events

---

## References

- [MPD Protocol](https://mpd.readthedocs.io/en/stable/protocol.html)
- [python-mpd2 Documentation](https://python-mpd2.readthedocs.io/)
- [yt-dlp Documentation](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp)
- [ytmusicapi Documentation](https://ytmusicapi.readthedocs.io/)

---

**Instructions for Agents**:
1. **First**: Run `pwd` and verify you're in `/home/tunc/Sync/Programs/ytmpd`
2. Read ONLY your assigned phase section
3. Check the dependencies to understand what should already exist
4. Follow the detailed requirements exactly
5. Meet all completion criteria before marking phase complete
6. Create your summary in `docs/agent/mpd-integration/summaries/PHASE_XX_SUMMARY.md`
7. Update `docs/agent/mpd-integration/STATUS.md` when complete

**Remember**: All file paths in this plan are relative to `/home/tunc/Sync/Programs/ytmpd`

**Context Budget Note**: Each phase is designed to fit within ~120k tokens total. Phases 4-6 are the largest. If any phase exceeds budget, note it in your summary and suggest splitting.
