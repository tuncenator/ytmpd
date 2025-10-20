# ytmpd ICY Metadata Proxy - Project Plan

**Feature/Initiative**: track-metadata
**Type**: New Feature
**Created**: 2025-10-19
**Estimated Total Phases**: 4

---

## 📍 Project Location

**IMPORTANT: All paths in this document are relative to the project root.**

- **Project Root**: `/home/tunc/Sync/Programs/ytmpd`
- **Verify with**: `pwd` → should output `/home/tunc/Sync/Programs/ytmpd`

When you see a path like `ytmpd/icy_proxy.py`, it means `/home/tunc/Sync/Programs/ytmpd/ytmpd/icy_proxy.py`

---

## Project Overview

### Purpose

Implement an ICY metadata proxy server to display track metadata (artist, title) in MPD clients when playing YouTube Music streams.

**The Problem:**
- ytmpd successfully syncs YouTube Music playlists to MPD and playback works perfectly
- However, MPD clients (ncmpcpp, mpc) display raw YouTube stream URLs instead of track metadata
- MPD expects metadata from ICY/Shoutcast headers, ID3 tags, or local file database
- YouTube streams provide none of these

**The Solution:**
- Build a local HTTP streaming proxy that sits between MPD and YouTube
- Proxy intercepts MPD's stream requests and injects ICY metadata headers
- M3U playlists contain proxy URLs (e.g., `http://localhost:8080/proxy/dQw4w9WgXcQ`) instead of direct YouTube URLs
- Proxy maintains mapping: `video_id → (youtube_url, artist, title)`
- When MPD requests the stream, proxy fetches from YouTube and adds ICY headers with metadata

### Scope

**In Scope**:
- HTTP streaming proxy server with ICY metadata injection
- Track ID mapping storage (SQLite database)
- Integration with existing MPD client and sync engine
- M3U generation with proxy URLs instead of direct YouTube URLs
- Error handling for expired URLs, stream failures, connection errors
- Concurrent stream support (multiple MPD clients/tracks)
- Configuration for proxy settings (port, host, database path)
- Testing (unit tests, integration tests, manual validation)

**Out of Scope**:
- Caching audio streams (proxy is pass-through only)
- Transcoding or format conversion
- Authentication/access control for proxy
- Web UI for proxy management
- Analytics or listening history tracking (may be future enhancement)
- Modification of existing ytmpd sync logic (only M3U URL generation changes)

### Success Criteria

- [ ] Load playlist in MPD: `mpc -p 6601 load "YT: chilax"`
- [ ] View queue in ncmpcpp and see `Artist - Title` instead of raw YouTube URLs
- [ ] Audio playback continues working normally (no degradation)
- [ ] Metadata updates correctly when playing different tracks
- [ ] Proxy handles concurrent streams (multiple tracks playing simultaneously)
- [ ] Expired YouTube URLs are refreshed automatically
- [ ] Tests achieve 70%+ coverage for new code
- [ ] Documentation updated (README, configuration examples)

---

## Architecture Overview

### Current Flow (Before Proxy)

```
YouTube Music API → ytmpd sync daemon → M3U files (with direct YouTube URLs)
                          ↓
                    StreamResolver (yt-dlp)
                          ↓
                    YouTube stream URLs
                          ↓
                    MPD loads M3U → MPD plays from YouTube directly
                          ↓
                    ncmpcpp shows: https://rr4---sn-u0g3n5u-pnue.googlevideo.com/... ❌
```

### New Flow (With Proxy)

```
YouTube Music API → ytmpd sync daemon → M3U files (with proxy URLs)
                          ↓
                    StreamResolver (yt-dlp)
                          ↓
                    Store mapping: video_id → (youtube_url, artist, title)
                          ↓
                    MPD loads M3U → MPD requests http://localhost:8080/proxy/{video_id}
                          ↓
                    ICY Proxy Server
                          ↓
                    Lookup video_id → fetch YouTube stream → inject ICY headers
                          ↓
                    Stream to MPD with metadata
                          ↓
                    ncmpcpp shows: Tommy Guerrero - Thin Brown Layer ✅
```

### Key Components

1. **ICY Proxy Server** (`ytmpd/icy_proxy.py`): Async HTTP server that handles stream requests, injects ICY metadata
2. **Track Mapping Storage** (`ytmpd/track_store.py`): SQLite database for `video_id → (url, artist, title)` mapping
3. **MPD Client Modification** (`ytmpd/mpd_client.py`): Update `create_or_replace_playlist()` to generate proxy URLs
4. **Daemon Integration** (`ytmpd/daemon.py`): Start/stop proxy server alongside sync daemon
5. **Configuration** (`~/.config/ytmpd/config.yaml`): Proxy settings (port, host, database path)

### Data Flow

```
1. Sync Phase:
   YouTube API → get playlists/tracks
                    ↓
   Extract: video_id, title, artist
                    ↓
   StreamResolver → resolve video_id to stream URL
                    ↓
   TrackStore → save mapping to SQLite
                    ↓
   MPDClient → create M3U with proxy URLs (http://localhost:8080/proxy/{video_id})

2. Playback Phase:
   MPD → request http://localhost:8080/proxy/dQw4w9WgXcQ
            ↓
   ICY Proxy → lookup dQw4w9WgXcQ in TrackStore
            ↓
   Get (youtube_url, artist, title)
            ↓
   Fetch stream from YouTube
            ↓
   Add ICY headers: icy-name, icy-metadata, StreamTitle
            ↓
   Stream data to MPD (with injected metadata)
            ↓
   MPD clients display: "Artist - Title"
```

### Technology Stack

- **Language**: Python 3.11+
- **Proxy Server**: aiohttp (async HTTP server and client)
- **Database**: SQLite (via Python's sqlite3 module)
- **Existing Libraries**: ytmusicapi, yt-dlp, python-mpd2, pyyaml
- **Testing**: pytest, pytest-asyncio
- **Environment Manager**: uv

---

## Phase Breakdown

> **Note for Agents**: Only read the section for your assigned phase. Reading all phases wastes context.

---

### Phase 1: ICY Proxy Server - Core Implementation

**Objective**: Build HTTP streaming proxy with ICY metadata injection capability

**Estimated Context Budget**: ~60k tokens

#### Deliverables

1. `ytmpd/icy_proxy.py` - Async HTTP proxy server using aiohttp
2. `ytmpd/track_store.py` - SQLite-backed track metadata storage
3. ICY/Shoutcast protocol implementation (header injection)
4. Basic stream proxying (fetch YouTube stream, pipe to MPD with metadata)

#### Detailed Requirements

**File 1: `ytmpd/track_store.py`**

Create a SQLite-backed storage system for track metadata:

```python
class TrackStore:
    """
    Manages persistent storage of track metadata.

    Schema:
    - video_id (TEXT PRIMARY KEY): YouTube video ID
    - stream_url (TEXT NOT NULL): Current YouTube stream URL
    - artist (TEXT): Track artist name
    - title (TEXT NOT NULL): Track title
    - updated_at (REAL): Unix timestamp of last update
    """

    def __init__(self, db_path: str):
        """Initialize database connection and create schema if needed."""

    def add_track(self, video_id: str, stream_url: str, title: str, artist: str | None = None) -> None:
        """Add or update a track in the database."""

    def get_track(self, video_id: str) -> dict[str, Any] | None:
        """Retrieve track metadata by video_id. Returns None if not found."""

    def update_stream_url(self, video_id: str, stream_url: str) -> None:
        """Update the stream URL for an existing track (for URL refresh)."""

    def close(self) -> None:
        """Close database connection."""
```

**File 2: `ytmpd/icy_proxy.py`**

Create an async HTTP proxy server with ICY metadata support:

```python
class ICYProxyServer:
    """
    HTTP streaming proxy that injects ICY metadata for MPD clients.

    Handles requests like: http://localhost:8080/proxy/{video_id}
    Fetches stream from YouTube and adds ICY headers with track metadata.
    """

    def __init__(
        self,
        track_store: TrackStore,
        host: str = "localhost",
        port: int = 8080
    ):
        """Initialize proxy server."""

    async def start(self) -> None:
        """Start the aiohttp server."""

    async def stop(self) -> None:
        """Stop the aiohttp server gracefully."""

    async def _handle_proxy_request(self, request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
        """
        Handle proxy requests for video streams.

        URL format: /proxy/{video_id}

        Steps:
        1. Extract video_id from path
        2. Lookup track in TrackStore
        3. If not found, return 404
        4. Fetch stream from YouTube URL using aiohttp.ClientSession
        5. Create StreamResponse with ICY headers
        6. Stream data from YouTube to MPD client
        """
```

**ICY Protocol Implementation:**

ICY (Icecast/Shoutcast) metadata headers to inject:

```
HTTP/1.1 200 OK
Content-Type: audio/mpeg
icy-name: Artist - Title
icy-metaint: 16000
```

For inline metadata updates (if supported by MPD client):
- Insert metadata frames every `icy-metaint` bytes
- Format: `StreamTitle='Artist - Title';`

**Stream Proxying Logic:**

1. Receive request for `/proxy/{video_id}`
2. Validate video_id format (alphanumeric, length check)
3. Lookup in TrackStore → get (stream_url, artist, title)
4. Create aiohttp.ClientSession and fetch stream_url
5. Check YouTube response status (200 OK)
6. Create aiohttp.web.StreamResponse
7. Add ICY headers to response
8. Stream data in chunks (8KB chunks) from YouTube to MPD
9. Handle errors: connection timeout, YouTube 403/404, network errors
10. Clean up resources on completion or error

**Error Handling:**

- Invalid video_id → 400 Bad Request
- Video not found in store → 404 Not Found
- YouTube URL fetch fails → 502 Bad Gateway
- Connection timeout → 504 Gateway Timeout
- Log all errors with context (video_id, error type)

#### Dependencies

**Requires**: None (this is Phase 1, foundational work)

**Enables**:
- Phase 2: M3U Integration (needs proxy server to generate URLs for)
- Phase 3: Error Handling (builds on proxy functionality)

#### Completion Criteria

- [ ] `ytmpd/track_store.py` created with TrackStore class
- [ ] SQLite schema created and tested (CRUD operations work)
- [ ] `ytmpd/icy_proxy.py` created with ICYProxyServer class
- [ ] aiohttp server starts and listens on configured port
- [ ] Proxy handles `/proxy/{video_id}` requests correctly
- [ ] ICY headers injected into stream responses
- [ ] Stream data proxied from YouTube to client successfully
- [ ] Error handling for invalid requests and failed streams
- [ ] Code follows project style (type hints, docstrings, PEP 8)
- [ ] Unit tests written for TrackStore (CRUD operations)
- [ ] Unit tests written for ICYProxyServer (request handling, error cases)

#### Testing Requirements

**Unit Tests** (`tests/test_track_store.py`):
- Test TrackStore initialization and schema creation
- Test add_track (insert and update)
- Test get_track (found and not found)
- Test update_stream_url
- Test database persistence (close and reopen)

**Unit Tests** (`tests/test_icy_proxy.py`):
- Test proxy server startup and shutdown
- Test valid proxy request (mock YouTube stream)
- Test ICY header injection
- Test invalid video_id handling (400)
- Test video not found handling (404)
- Test YouTube fetch failure handling (502)
- Use pytest-aiohttp for async testing
- Mock aiohttp.ClientSession for YouTube requests

**Manual Testing:**
- Start proxy server standalone
- Add test track to TrackStore
- Request stream using curl: `curl http://localhost:8080/proxy/test_video_id`
- Verify ICY headers in response
- Verify stream data flows correctly

#### Notes

- **ICY metadata format**: Research Icecast/Shoutcast protocol for proper header format
- **Chunk size**: 8KB chunks balance memory usage and performance
- **Connection handling**: Use async context managers for proper cleanup
- **Database path**: Default to `~/.config/ytmpd/track_mapping.db`
- **Port conflicts**: Server should fail gracefully if port already in use
- **Future phases** will integrate this with the daemon lifecycle and sync engine

---

### Phase 2: M3U Integration & Daemon Lifecycle

**Objective**: Integrate proxy URLs into M3U generation and manage proxy server lifecycle within ytmpd daemon

**Estimated Context Budget**: ~40k tokens

#### Deliverables

1. Modified `ytmpd/mpd_client.py` - Update `create_or_replace_playlist()` to use proxy URLs
2. Modified `ytmpd/daemon.py` - Start/stop ICY proxy alongside sync daemon
3. Modified `~/.config/ytmpd/config.yaml` - Add proxy configuration
4. Integration between sync engine and TrackStore (save mappings during sync)

#### Detailed Requirements

**Modification 1: `ytmpd/mpd_client.py`**

Current behavior (around line 205 in `create_or_replace_playlist()`):
- Generates M3U files with direct YouTube stream URLs
- Uses `#EXTINF` tags with artist/title metadata

New behavior:
- Generate proxy URLs instead: `http://{proxy_host}:{proxy_port}/proxy/{video_id}`
- Extract video_id from YouTube stream URL (parse query param or use known video_id)
- Keep `#EXTINF` tags for playlist browsing

Changes needed:
```python
def create_or_replace_playlist(
    self,
    playlist_name: str,
    tracks: list[Track],
    proxy_config: dict | None = None  # NEW parameter
) -> None:
    """
    Create or replace MPD playlist with tracks.

    If proxy_config is provided, generates proxy URLs.
    Otherwise, uses direct YouTube URLs (backward compatibility).
    """

    # Inside M3U generation loop:
    if proxy_config:
        # Extract video_id from track (Track dataclass needs video_id field)
        proxy_url = f"http://{proxy_config['host']}:{proxy_config['port']}/proxy/{track.video_id}"
        m3u_content += f"{proxy_url}\n"
    else:
        # Legacy behavior: direct YouTube URL
        m3u_content += f"{track.url}\n"
```

**Modification 2: `ytmpd/sync_engine.py`**

Current behavior:
- Orchestrates sync: fetch playlists, resolve URLs, create M3U files

New behavior:
- Accept `track_store` and `proxy_config` as dependencies
- After resolving stream URL, save mapping to TrackStore
- Pass proxy_config to MPDClient.create_or_replace_playlist()

Changes needed:
```python
class SyncEngine:
    def __init__(
        self,
        ytmusic_client: YTMusicClient,
        stream_resolver: StreamResolver,
        mpd_client: MPDClient,
        track_store: TrackStore | None = None,  # NEW
        proxy_config: dict | None = None  # NEW
    ):
        """Initialize sync engine with optional proxy support."""

    async def sync_playlist(self, playlist_id: str, playlist_name: str) -> SyncResult:
        """
        Sync a single playlist.

        For each track:
        1. Resolve stream URL (existing logic)
        2. If track_store provided, save mapping:
           track_store.add_track(video_id, stream_url, title, artist)
        3. Pass tracks to mpd_client.create_or_replace_playlist(proxy_config=proxy_config)
        """
```

**Modification 3: `ytmpd/daemon.py`**

Current behavior:
- Starts sync daemon
- Listens on Unix socket for sync commands
- Performs periodic auto-sync

New behavior:
- Initialize TrackStore and ICYProxyServer on startup
- Start proxy server alongside socket server
- Pass track_store and proxy_config to SyncEngine
- Stop proxy server on daemon shutdown

Changes needed:
```python
class YTMPDaemon:
    def __init__(self, config: Config):
        """
        Initialize daemon components.

        NEW:
        - Initialize TrackStore(config.proxy_track_mapping_db)
        - Initialize ICYProxyServer(track_store, config.proxy_host, config.proxy_port)
        """

    async def start(self) -> None:
        """
        Start daemon services.

        1. Start ICY proxy server (await proxy_server.start())
        2. Start sync socket server (existing)
        3. Schedule periodic sync (existing)
        """

    async def stop(self) -> None:
        """
        Stop daemon services.

        1. Stop sync socket server (existing)
        2. Stop ICY proxy server (await proxy_server.stop())
        3. Close TrackStore database connection
        """
```

**Modification 4: `ytmpd/config.py` and `~/.config/ytmpd/config.yaml`**

Add proxy configuration fields:

```yaml
# ICY Proxy Settings
proxy_enabled: true
proxy_host: localhost
proxy_port: 8080
proxy_track_mapping_db: ~/.config/ytmpd/track_mapping.db
```

Update Config dataclass:
```python
@dataclass
class Config:
    # Existing fields...

    # NEW proxy fields
    proxy_enabled: bool = True
    proxy_host: str = "localhost"
    proxy_port: int = 8080
    proxy_track_mapping_db: str = "~/.config/ytmpd/track_mapping.db"
```

**Data Model Update: `Track` dataclass**

Add `video_id` field to Track:
```python
@dataclass
class Track:
    video_id: str  # NEW: YouTube video ID (e.g., "dQw4w9WgXcQ")
    title: str
    artist: str | None
    url: str  # Stream URL from yt-dlp
    duration: int | None = None
```

Update all places where Track objects are created to include video_id.

#### Dependencies

**Requires**:
- Phase 1: ICY Proxy Server must be complete (TrackStore, ICYProxyServer classes exist)

**Enables**:
- Phase 3: Error Handling (proxy is now integrated and running)
- Phase 4: Testing (full workflow can be tested end-to-end)

#### Completion Criteria

- [ ] `ytmpd/mpd_client.py` modified to generate proxy URLs when proxy_config provided
- [ ] `ytmpd/sync_engine.py` modified to save track mappings to TrackStore
- [ ] `ytmpd/daemon.py` modified to start/stop proxy server
- [ ] `ytmpd/config.py` updated with proxy configuration fields
- [ ] Example config added to `examples/config.yaml`
- [ ] Track dataclass updated with video_id field
- [ ] All Track instantiations updated to include video_id
- [ ] Backward compatibility maintained (works without proxy if proxy_enabled=false)
- [ ] Proxy server starts successfully when daemon starts
- [ ] M3U files contain proxy URLs (verified by manual inspection)
- [ ] Code follows project style (type hints, docstrings)

#### Testing Requirements

**Unit Tests** (`tests/test_mpd_client.py`):
- Test create_or_replace_playlist with proxy_config (generates proxy URLs)
- Test create_or_replace_playlist without proxy_config (generates direct URLs)
- Verify M3U content format matches expected output

**Unit Tests** (`tests/test_sync_engine.py`):
- Test sync_playlist saves tracks to TrackStore
- Mock TrackStore.add_track and verify calls

**Integration Tests** (`tests/integration/test_proxy_integration.py`):
- Start daemon with proxy enabled
- Trigger sync
- Verify TrackStore contains track mappings
- Verify M3U files contain proxy URLs
- Verify proxy responds to requests for synced tracks

**Manual Testing:**
- Start ytmpd daemon
- Run `ytmpctl sync`
- Check M3U files in `~/.config/mpd/playlists/` for proxy URLs
- Check TrackStore database contains mappings
- Test proxy request: `curl http://localhost:8080/proxy/{video_id}`

#### Notes

- **Video ID extraction**: ytmusicapi provides video_id in playlist track objects, use this
- **Backward compatibility**: If proxy_enabled=false, system should work as before (direct URLs)
- **Configuration migration**: Existing users need to know about new proxy settings
- **Port conflicts**: Document how to change proxy_port if 8080 is in use
- **Database location**: Ensure ~/.config/ytmpd/ directory exists before creating database

---

### Phase 3: Error Handling & Persistence

**Objective**: Make proxy robust with error handling for expired URLs, stream failures, and concurrent connections

**Estimated Context Budget**: ~45k tokens

#### Deliverables

1. URL refresh mechanism (handle expired YouTube URLs)
2. Stream failure handling (connection errors, timeouts, retries)
3. Concurrent connection support (handle multiple MPD streams)
4. Graceful degradation (fallback to direct URLs if proxy fails)
5. Logging and error reporting improvements

#### Detailed Requirements

**Feature 1: Expired URL Refresh**

Problem: YouTube stream URLs expire after ~6 hours. Current cache is 5 hours.

Solution:
```python
# In ytmpd/icy_proxy.py

async def _handle_proxy_request(self, request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
    """
    Enhanced request handling with URL refresh.

    Steps:
    1. Lookup track in TrackStore
    2. Check if stream_url is expired (based on updated_at timestamp)
    3. If expired (>5 hours old), refresh URL:
       - Call StreamResolver to get new URL for video_id
       - Update TrackStore with new URL
    4. Proceed with stream proxying
    """

    track = self.track_store.get_track(video_id)

    if track and self._is_url_expired(track['updated_at']):
        logger.info(f"Stream URL expired for {video_id}, refreshing...")
        new_url = await self._refresh_stream_url(video_id)
        self.track_store.update_stream_url(video_id, new_url)
        track['stream_url'] = new_url
```

Add helper methods:
```python
def _is_url_expired(self, updated_at: float, expiry_hours: int = 5) -> bool:
    """Check if URL is older than expiry_hours."""
    age_seconds = time.time() - updated_at
    return age_seconds > (expiry_hours * 3600)

async def _refresh_stream_url(self, video_id: str) -> str:
    """
    Use yt-dlp to get fresh stream URL for video_id.

    This requires access to StreamResolver.
    Inject StreamResolver as dependency in ICYProxyServer.__init__.
    """
    return await self.stream_resolver.resolve_single(video_id)
```

Update ICYProxyServer.__init__ to accept StreamResolver.

**Feature 2: Stream Failure Handling**

Implement retry logic and error handling:

```python
async def _fetch_and_stream(
    self,
    stream_url: str,
    response: aiohttp.web.StreamResponse,
    max_retries: int = 3
) -> None:
    """
    Fetch stream from YouTube and pipe to MPD with retry logic.

    Error handling:
    - Connection timeout (10s): Retry up to max_retries
    - HTTP 403/404: Don't retry, return error
    - Network errors: Retry with exponential backoff
    - Chunk read timeout: Log warning, continue
    """

    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    stream_url,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as yt_response:
                    if yt_response.status != 200:
                        raise YouTubeStreamError(f"Status {yt_response.status}")

                    # Stream chunks
                    async for chunk in yt_response.content.iter_chunked(8192):
                        await response.write(chunk)
                    break  # Success

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Stream failed, retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Stream failed after {max_retries} attempts: {e}")
                raise
```

Add custom exceptions in `ytmpd/exceptions.py`:
```python
class ProxyError(Exception):
    """Base exception for proxy errors."""

class YouTubeStreamError(ProxyError):
    """YouTube stream fetch failed."""

class TrackNotFoundError(ProxyError):
    """Track not found in store."""
```

**Feature 3: Concurrent Connection Support**

Ensure proxy can handle multiple simultaneous streams:

- Use aiohttp's built-in connection pooling (no special handling needed)
- Test with multiple concurrent requests
- Add connection limiting (max 10 concurrent streams) to prevent resource exhaustion

```python
class ICYProxyServer:
    def __init__(self, ...):
        self._active_connections = 0
        self._max_connections = 10

    async def _handle_proxy_request(self, request):
        if self._active_connections >= self._max_connections:
            return aiohttp.web.Response(status=503, text="Too many concurrent streams")

        self._active_connections += 1
        try:
            # Handle request
            ...
        finally:
            self._active_connections -= 1
```

**Feature 4: Graceful Degradation**

If proxy fails during sync, fall back to direct URLs:

```python
# In ytmpd/sync_engine.py

async def sync_playlist(self, ...):
    """
    Sync playlist with graceful proxy degradation.

    Try to save to TrackStore. If fails, log warning and continue.
    Try to use proxy URLs. If proxy unreachable, use direct URLs.
    """

    use_proxy = False
    if self.proxy_config and self.track_store:
        try:
            # Test proxy connectivity
            await self._test_proxy_connectivity()
            use_proxy = True
        except ProxyError:
            logger.warning("Proxy unreachable, falling back to direct URLs")
            use_proxy = False

    for track in tracks:
        if use_proxy:
            try:
                self.track_store.add_track(...)
            except Exception as e:
                logger.error(f"Failed to save track {track.video_id}: {e}")
                # Continue anyway
```

**Feature 5: Enhanced Logging**

Add structured logging throughout proxy:

```python
# Log levels:
# INFO: Normal operations (proxy start, stream requests, URL refresh)
# WARNING: Recoverable errors (retry attempts, fallback to direct URLs)
# ERROR: Failures (stream failed after retries, database errors)

logger.info(f"[PROXY] Starting server on {self.host}:{self.port}")
logger.info(f"[PROXY] Stream request: video_id={video_id}, client={request.remote}")
logger.warning(f"[PROXY] URL expired for {video_id}, refreshing")
logger.error(f"[PROXY] Failed to fetch stream for {video_id}: {error}")
```

#### Dependencies

**Requires**:
- Phase 1: ICY Proxy Server (base implementation exists)
- Phase 2: M3U Integration (proxy is integrated into daemon)

**Enables**:
- Phase 4: Testing (robust proxy ready for comprehensive testing)

#### Completion Criteria

- [ ] URL expiry detection implemented
- [ ] Automatic URL refresh on expiry (using yt-dlp)
- [ ] Stream failure retry logic with exponential backoff
- [ ] Custom exceptions defined (ProxyError, YouTubeStreamError, TrackNotFoundError)
- [ ] Concurrent connection support (tested with 5+ simultaneous streams)
- [ ] Connection limiting (max 10 concurrent streams)
- [ ] Graceful degradation (falls back to direct URLs if proxy fails)
- [ ] Enhanced logging throughout proxy code
- [ ] Error handling tested (expired URLs, failed streams, network errors)
- [ ] Code follows project style

#### Testing Requirements

**Unit Tests** (`tests/test_icy_proxy.py` additions):
- Test _is_url_expired (with mock timestamps)
- Test _refresh_stream_url (mock StreamResolver)
- Test retry logic (mock failing then succeeding request)
- Test connection limiting (mock 11 concurrent requests, 11th gets 503)
- Test custom exceptions are raised correctly

**Integration Tests** (`tests/integration/test_proxy_error_handling.py`):
- Test expired URL refresh (create track with old timestamp, request stream)
- Test stream failure recovery (mock YouTube timeout, verify retry)
- Test concurrent streams (start 5 streams simultaneously, all succeed)
- Test graceful degradation (stop proxy, sync should use direct URLs)

**Manual Testing:**
- Create track with expired URL (set updated_at to 6 hours ago)
- Request stream, verify URL refresh happens
- Start multiple streams (play 3 tracks simultaneously in MPD)
- Simulate network failure (disconnect internet briefly), verify retry

#### Notes

- **StreamResolver integration**: Proxy needs access to StreamResolver for URL refresh
- **Performance**: URL refresh adds latency (~1-2s), acceptable for expired URLs
- **Database locking**: SQLite may lock on concurrent writes, use WAL mode
- **Connection pool**: aiohttp handles connection pooling automatically
- **Retry strategy**: Exponential backoff (1s, 2s, 4s) balances responsiveness and load

---

### Phase 4: Testing & Validation

**Objective**: Comprehensive testing and validation with MPD clients, documentation updates

**Estimated Context Budget**: ~40k tokens

#### Deliverables

1. Comprehensive unit test suite (70%+ coverage for new code)
2. Integration tests (full workflow: sync → M3U → proxy → MPD)
3. Manual validation with ncmpcpp/mpc
4. Performance testing (concurrent streams, memory usage, latency)
5. Documentation updates (README, configuration guide)
6. Example configurations and troubleshooting guide

#### Detailed Requirements

**Testing 1: Unit Test Coverage**

Ensure all new modules have comprehensive unit tests:

**`tests/test_track_store.py`** (Complete coverage of TrackStore):
- Test database initialization (schema creation)
- Test add_track (insert new, update existing)
- Test get_track (found, not found)
- Test update_stream_url
- Test database persistence (write, close, reopen, read)
- Test concurrent access (multiple threads/processes)
- Test edge cases (empty strings, very long URLs, special characters)

**`tests/test_icy_proxy.py`** (Complete coverage of ICYProxyServer):
- Test server start/stop
- Test valid proxy request (mock YouTube stream)
- Test ICY header injection (verify headers in response)
- Test invalid video_id (400 error)
- Test track not found (404 error)
- Test YouTube fetch failure (502 error)
- Test URL expiry detection
- Test URL refresh (mock StreamResolver)
- Test retry logic (mock transient failures)
- Test connection limiting (503 when too many connections)
- Test concurrent requests (multiple simultaneous streams)
- Use pytest-aiohttp for async testing
- Use pytest fixtures for server setup/teardown

**`tests/test_mpd_client.py` additions**:
- Test M3U generation with proxy URLs
- Test M3U generation with direct URLs (proxy disabled)
- Test EXTINF tag format

**`tests/test_sync_engine.py` additions**:
- Test track mapping saved to TrackStore during sync
- Test graceful degradation when proxy unavailable

**Code Coverage Target**: 70%+ for new code (icy_proxy.py, track_store.py)

**Testing 2: Integration Tests**

**`tests/integration/test_full_workflow.py`**:

Test complete workflow from sync to playback:

```python
async def test_full_sync_to_proxy_workflow():
    """
    Integration test: sync playlist and request stream via proxy.

    Steps:
    1. Start mock YouTube Music API (return sample playlist)
    2. Start ytmpd daemon with proxy enabled
    3. Trigger sync
    4. Verify M3U file created with proxy URLs
    5. Verify TrackStore contains track mappings
    6. Request stream via proxy
    7. Verify ICY headers in response
    8. Verify stream data flows correctly
    """
```

**`tests/integration/test_mpd_playback.py`**:

Test actual MPD playback (requires MPD running):

```python
async def test_mpd_playback_with_proxy():
    """
    Integration test: load playlist in MPD and verify metadata.

    Prerequisites: MPD running on localhost:6601

    Steps:
    1. Start ytmpd daemon
    2. Sync a test playlist
    3. Load playlist in MPD: mpc load "YT: test"
    4. Query MPD for current queue
    5. Verify queue shows artist/title (not URLs)
    """
```

**Testing 3: Manual Validation**

Create a manual testing checklist:

**Checklist: Manual Validation with ncmpcpp**

Environment:
- [ ] MPD running on port 6601
- [ ] ytmpd daemon started with proxy enabled
- [ ] YouTube Music authentication configured

Test Cases:
- [ ] TC1: Sync playlists (`ytmpctl sync`)
  - Expected: Sync completes successfully
  - Expected: M3U files in ~/.config/mpd/playlists/ contain proxy URLs

- [ ] TC2: Load playlist in ncmpcpp
  - Command: `mpc -p 6601 load "YT: chilax"`
  - Expected: Playlist loads successfully

- [ ] TC3: View queue in ncmpcpp
  - Command: Open ncmpcpp, navigate to playlist view
  - Expected: See "Artist - Title" instead of URLs

- [ ] TC4: Play track
  - Command: `mpc -p 6601 play`
  - Expected: Audio plays successfully
  - Expected: ncmpcpp shows current track metadata

- [ ] TC5: Next/previous tracks
  - Command: `mpc -p 6601 next`, `mpc -p 6601 prev`
  - Expected: Metadata updates correctly

- [ ] TC6: Multiple simultaneous tracks
  - Setup: Open 2 MPD clients, play different playlists
  - Expected: Both play successfully with correct metadata

- [ ] TC7: URL expiry handling
  - Setup: Wait 6 hours OR manually set updated_at to old timestamp
  - Command: Play track with expired URL
  - Expected: Track plays after brief delay (URL refresh)
  - Expected: Log shows "URL expired, refreshing"

**Testing 4: Performance Testing**

**Performance Test 1: Concurrent Streams**

```python
async def test_concurrent_streams_performance():
    """
    Test proxy performance with multiple simultaneous streams.

    Test: 5 concurrent stream requests
    Measure: Response time, memory usage, success rate
    Expected: All streams succeed, <100MB memory increase
    """
```

**Performance Test 2: Latency**

```python
async def test_proxy_latency():
    """
    Measure latency added by proxy.

    Test: Time to first byte for proxy vs direct YouTube URL
    Expected: Proxy adds <200ms overhead
    """
```

**Performance Test 3: Memory Usage**

```python
async def test_memory_usage_over_time():
    """
    Test for memory leaks during extended operation.

    Test: Stream 100 tracks sequentially, measure memory
    Expected: Memory usage stable (no leaks)
    """
```

**Testing 5: Documentation Updates**

**Update `README.md`:**

Add section on ICY Proxy feature:

```markdown
## ICY Metadata Proxy

ytmpd includes a built-in streaming proxy that enables MPD clients to display
track metadata (artist, title) instead of raw YouTube URLs.

### How It Works

The proxy sits between MPD and YouTube, injecting ICY/Shoutcast metadata headers
into the audio stream. When you load a playlist, MPD receives proxy URLs like
`http://localhost:8080/proxy/dQw4w9WgXcQ` instead of direct YouTube URLs.

### Configuration

The proxy is enabled by default. Configure in `~/.config/ytmpd/config.yaml`:

```yaml
# ICY Proxy Settings
proxy_enabled: true
proxy_host: localhost
proxy_port: 8080
proxy_track_mapping_db: ~/.config/ytmpd/track_mapping.db
```

### Troubleshooting

**Q: ncmpcpp still shows URLs instead of metadata**
A: Ensure proxy_enabled: true in config and restart ytmpd daemon.

**Q: Proxy port 8080 already in use**
A: Change proxy_port in config to an available port (e.g., 8081).

**Q: Tracks fail to play after several hours**
A: YouTube URLs expire after 6 hours. The proxy automatically refreshes them.
   Run `ytmpctl sync` to manually refresh all URLs.

**Q: High memory usage**
A: The proxy streams data without caching, memory usage should be low (<50MB).
   If high, check for zombie connections: `netstat -an | grep 8080`
```

**Create `docs/ICY_PROXY.md`:**

Detailed technical documentation:
- Architecture diagram
- ICY protocol explanation
- How URL refresh works
- Troubleshooting guide
- Performance tuning tips

**Update `examples/config.yaml`:**

Add commented proxy configuration with explanations.

#### Dependencies

**Requires**:
- Phase 1: ICY Proxy Server (complete)
- Phase 2: M3U Integration (complete)
- Phase 3: Error Handling (complete)

**Enables**:
- Feature is complete and ready for production use

#### Completion Criteria

- [ ] Unit tests written for all new modules (track_store, icy_proxy)
- [ ] Code coverage ≥70% for new code
- [ ] Integration tests cover full workflow (sync → proxy → MPD)
- [ ] Manual testing checklist completed (all test cases pass)
- [ ] Performance tests run (concurrent streams, latency, memory)
- [ ] README.md updated with proxy feature documentation
- [ ] Technical documentation created (docs/ICY_PROXY.md)
- [ ] Example configuration updated
- [ ] Troubleshooting guide written
- [ ] All tests passing (pytest returns 0)
- [ ] No regressions (existing tests still pass)

#### Testing Requirements

This phase IS the testing phase. All requirements are testing-related (see Detailed Requirements above).

**Final Test Run:**

```bash
# Run all tests with coverage
pytest --cov=ytmpd --cov-report=term-missing --cov-report=html

# Expected output:
# ===== XX passed in X.XXs =====
# Coverage: ≥70% for ytmpd/icy_proxy.py and ytmpd/track_store.py
```

#### Notes

- **Test data**: Create fixture playlists for testing (small datasets)
- **Mock MPD**: Use python-mpd2 test utilities or Docker MPD container
- **Mock YouTube**: Use pytest-httpserver to mock YouTube stream responses
- **CI/CD**: Consider adding GitHub Actions workflow for automated testing
- **Documentation review**: Have someone unfamiliar with the code review docs for clarity
- **Performance baseline**: Document baseline performance for future comparison

---

## Phase Dependencies Graph

```
Phase 1 (ICY Proxy Server - Core)
    ↓
Phase 2 (M3U Integration & Daemon Lifecycle)
    ↓
Phase 3 (Error Handling & Persistence)
    ↓
Phase 4 (Testing & Validation)
```

Linear dependency chain - each phase builds on the previous.

---

## Cross-Cutting Concerns

### Code Style

- Follow PEP 8 for Python
- Use type hints for all function signatures
- Maximum line length: 100 characters (consistent with existing ytmpd code)
- Use docstrings for all public functions (Google style)
- Use async/await for all I/O operations (aiohttp, database)

### Error Handling

- Use custom exceptions defined in `ytmpd/exceptions.py`
- Always log errors before raising (include context: video_id, operation)
- Provide helpful error messages (e.g., "Track abc123 not found in database")
- Use try/except for I/O operations (network, database)
- Don't catch generic Exception unless re-raising with context

### Logging

- Use Python's `logging` module (configured by existing ytmpd config)
- Log levels:
  - **DEBUG**: Detailed trace (chunk sizes, headers, timing)
  - **INFO**: Normal operations (proxy start, stream requests, sync complete)
  - **WARNING**: Recoverable issues (URL refresh, retry attempts)
  - **ERROR**: Failures (stream failed after retries, database errors)
  - **CRITICAL**: Fatal errors (proxy can't start, database corruption)
- Format: `[timestamp] [level] [module] message` (existing ytmpd format)
- Include context in log messages: `logger.info(f"[PROXY] Stream request: {video_id}")`

### Configuration

- All config in `~/.config/ytmpd/config.yaml` (existing file)
- New proxy config section (see Phase 2)
- Use Config dataclass (existing pattern in ytmpd/config.py)
- Validate configuration on load (check port range, paths exist)
- Provide sensible defaults (proxy_port=8080, proxy_enabled=true)

### Testing Strategy

- **Unit tests**: Test individual functions/classes in isolation
- **Integration tests**: Test component interactions (sync → proxy → MPD)
- **Manual tests**: Real-world validation with ncmpcpp/mpc
- **Performance tests**: Measure latency, throughput, memory usage
- Minimum 70% code coverage for new code
- Use pytest with fixtures for common setups (database, server, config)
- Use pytest-asyncio for async tests
- Use pytest-cov for coverage reporting
- Mock external dependencies (YouTube, MPD) in unit tests
- Use real dependencies in integration tests (where feasible)

### Database Strategy

- **SQLite**: Simple, embedded, no external dependencies
- **Schema**: Single table `tracks` with video_id as primary key
- **WAL mode**: Enable Write-Ahead Logging for better concurrent access
- **Connection management**: One connection per TrackStore instance, close on daemon shutdown
- **Migrations**: Not needed for Phase 1 (new feature), but consider for future schema changes
- **Backup**: Document how to backup track_mapping.db for users

---

## Integration Points

### ICY Proxy ↔ Track Store

- Proxy reads track metadata from TrackStore on every stream request
- Proxy updates TrackStore when refreshing expired URLs
- Thread-safe: TrackStore uses SQLite (automatically handles concurrent access)

### Sync Engine ↔ Track Store

- SyncEngine writes track mappings to TrackStore during sync
- SyncEngine passes proxy_config to MPDClient for M3U generation
- One-way data flow: SyncEngine → TrackStore (no reads during sync)

### MPD Client ↔ Proxy

- MPDClient generates M3U files with proxy URLs (http://localhost:8080/proxy/{video_id})
- MPD reads M3U files and requests streams from proxy
- No direct communication between MPDClient and ICYProxyServer

### Daemon ↔ All Components

- Daemon owns lifecycle of all components (start, stop)
- Daemon passes shared dependencies (Config, TrackStore) to components
- Daemon coordinates graceful shutdown (stop proxy, close database)

---

## Data Schemas

### Track Mapping Database Schema

```sql
CREATE TABLE tracks (
    video_id TEXT PRIMARY KEY,
    stream_url TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT,
    updated_at REAL NOT NULL  -- Unix timestamp
);

CREATE INDEX idx_updated_at ON tracks(updated_at);  -- For expiry queries
```

### Configuration Schema (Proxy Section)

```yaml
# ICY Proxy Settings
proxy_enabled: true          # Enable/disable proxy (bool)
proxy_host: localhost        # Bind host (string)
proxy_port: 8080             # Bind port (int, 1024-65535)
proxy_track_mapping_db: ~/.config/ytmpd/track_mapping.db  # Database path (string)
```

### Track Dataclass

```python
@dataclass
class Track:
    video_id: str              # YouTube video ID (e.g., "dQw4w9WgXcQ")
    title: str                 # Track title
    artist: str | None         # Track artist (may be None)
    url: str                   # Stream URL from yt-dlp
    duration: int | None       # Duration in seconds (optional)
```

### ICY Headers

```
HTTP/1.1 200 OK
Content-Type: audio/mpeg
icy-name: Artist - Title
icy-metaint: 16000
```

---

## Glossary

**ICY Protocol**: Icecast/Shoutcast streaming protocol for metadata in HTTP streams
**MPD**: Music Player Daemon - server-side music player
**M3U**: Playlist file format used by MPD
**EXTINF**: M3U tag for track metadata (used for playlist browsing)
**Proxy URL**: URL pointing to local proxy instead of direct YouTube stream
**Video ID**: YouTube's unique identifier for a video (e.g., "dQw4w9WgXcQ")
**Stream URL**: Direct HTTPS URL to YouTube audio stream (from yt-dlp)
**Track Mapping**: Association between video_id and (stream_url, artist, title)
**URL Expiry**: YouTube stream URLs expire after ~6 hours
**WAL Mode**: Write-Ahead Logging for SQLite (better concurrent access)

---

## Future Enhancements

Items not in current scope but potentially valuable:

- [ ] Analytics/listening history tracking (play counts, last played timestamps)
- [ ] Smart playlist generation based on listening patterns
- [ ] Lyrics fetching and display
- [ ] Album art/thumbnail proxy
- [ ] Web UI for proxy management and statistics
- [ ] Caching popular streams (reduce yt-dlp calls)
- [ ] Support for other streaming services (SoundCloud, Spotify)
- [ ] Authentication/access control for proxy (multi-user support)
- [ ] Playlist recommendations based on listening history

---

## References

- [Icecast Protocol Specification](http://www.icecast.org/docs/)
- [MPD Protocol Documentation](https://www.musicpd.org/doc/protocol/)
- [aiohttp Documentation](https://docs.aiohttp.org/)
- [yt-dlp Documentation](https://github.com/yt-dlp/yt-dlp)
- [python-mpd2 Documentation](https://python-mpd2.readthedocs.io/)

---

**Instructions for Agents**:
1. **First**: Run `pwd` and verify you're in `/home/tunc/Sync/Programs/ytmpd`
2. Read ONLY your assigned phase section
3. Check the dependencies to understand what should already exist
4. Follow the detailed requirements exactly
5. Meet all completion criteria before marking phase complete
6. Create your summary in `docs/agent/track-metadata/summaries/PHASE_XX_SUMMARY.md`
7. Update `docs/agent/track-metadata/STATUS.md` when complete

**Remember**: All file paths in this plan are relative to `/home/tunc/Sync/Programs/ytmpd`

**Context Budget Note**: Each phase is designed to fit within ~40-60k tokens of reading plus implementation, leaving buffer for thinking and output. If a phase exceeds 120k total, note it in your summary and suggest splitting the phase.
