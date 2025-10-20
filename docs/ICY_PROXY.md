# ICY Metadata Proxy - Technical Documentation

## Overview

The ICY Metadata Proxy is an HTTP streaming proxy that injects ICY/Shoutcast metadata headers into YouTube audio streams, enabling MPD clients to display track information (artist, title) instead of URLs.

## Architecture

### Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                        ytmpd Daemon                          │
│                                                              │
│  ┌────────────────┐        ┌──────────────┐                │
│  │  Sync Engine   │───────▶│  TrackStore  │                │
│  │                │  save  │  (SQLite)    │                │
│  │ (sync playlists│ metadata│              │                │
│  │  from YouTube) │        └──────────────┘                │
│  └────────────────┘               ▲                         │
│                                    │ read                    │
│  ┌────────────────┐                │                         │
│  │ ICYProxyServer │────────────────┘                         │
│  │ (aiohttp HTTP) │                                          │
│  │ localhost:8080 │                                          │
│  └────────────────┘                                          │
└─────────────┬────────────────────────────────────────────────┘
              │ HTTP proxy request
              ▼
┌─────────────────────────────────────────┐
│  MPD Server                             │
│  Plays: http://localhost:8080/proxy/... │
└─────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│  MPD Client (mpc/ncmpcpp)               │
│  Displays: "Artist - Title"             │
└─────────────────────────────────────────┘
```

### Data Flow

1. **Sync Phase** (ytmpd sync):
   - Sync Engine fetches playlists from YouTube Music
   - Resolves video IDs to stream URLs via yt-dlp
   - Saves mappings to TrackStore: `(video_id → stream_url, artist, title, updated_at)`
   - Creates MPD playlist with proxy URLs: `http://localhost:8080/proxy/{video_id}`

2. **Playback Phase** (MPD plays track):
   - MPD requests: `GET http://localhost:8080/proxy/dQw4w9WgXcQ`
   - ICY Proxy:
     - Looks up video_id in TrackStore → gets `(stream_url, artist, title)`
     - Checks if URL expired (> 5 hours old)
     - If expired: Refreshes URL via StreamResolver, updates TrackStore
     - Fetches YouTube stream via aiohttp
     - Creates StreamResponse with ICY headers: `icy-name: Rick Astley - Never Gonna Give You Up`
     - Streams audio chunks from YouTube → MPD
   - MPD parses ICY headers and displays metadata
   - Client (ncmpcpp/mpc) shows formatted track name

## Core Components

### TrackStore (ytmpd/track_store.py)

SQLite-backed track metadata storage.

**Schema:**
```sql
CREATE TABLE tracks (
    video_id TEXT PRIMARY KEY,
    stream_url TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT,
    updated_at REAL NOT NULL  -- Unix timestamp
);
```

**Key Methods:**
- `add_track(video_id, stream_url, title, artist)` - Insert or update track
- `get_track(video_id)` - Retrieve track metadata (returns dict or None)
- `update_stream_url(video_id, stream_url)` - Update URL and timestamp

**Thread Safety:** Uses SQLite's built-in locking. Safe for concurrent reads/writes.

**Database Location:** `~/.config/ytmpd/track_mapping.db` (configurable)

### ICYProxyServer (ytmpd/icy_proxy.py)

Async HTTP proxy server using aiohttp.

**Key Features:**
- Async/await architecture for high concurrency
- ICY metadata header injection
- Automatic URL refresh on expiry
- Retry logic with exponential backoff
- Connection limiting
- Comprehensive error handling

**Endpoints:**

1. `GET /proxy/{video_id}` - Stream audio with ICY metadata
   - Validates video_id format (11 characters, alphanumeric/-/_)
   - Returns 400: Invalid video_id format
   - Returns 404: Track not found in store
   - Returns 502: YouTube stream fetch failed
   - Returns 503: Too many concurrent connections
   - Returns 504: Stream request timeout

2. `GET /health` - Health check
   - Returns: `{"status": "ok", "service": "icy-proxy"}`

**Configuration Parameters:**
- `host` (default: "localhost") - Bind address
- `port` (default: 8080) - Bind port
- `stream_resolver` (optional) - StreamResolver instance for URL refresh
- `max_concurrent_streams` (default: 10) - Connection limit

### StreamResolver Integration

The proxy uses StreamResolver to refresh expired URLs:

```python
from ytmpd.stream_resolver import StreamResolver
from ytmpd.icy_proxy import ICYProxyServer
from ytmpd.track_store import TrackStore

track_store = TrackStore("~/.config/ytmpd/track_mapping.db")
stream_resolver = StreamResolver(cache_hours=5)

proxy = ICYProxyServer(
    track_store,
    stream_resolver=stream_resolver,
    host="localhost",
    port=8080
)

async with proxy:
    # Proxy now handles URL refresh automatically
    await asyncio.Event().wait()
```

## URL Expiry & Refresh

### Expiry Detection

YouTube stream URLs expire after ~6 hours. The proxy detects expiry by checking `updated_at` timestamp:

```python
def _is_url_expired(self, updated_at: float, expiry_hours: int = 5) -> bool:
    age_hours = (time.time() - updated_at) / 3600
    return age_hours >= expiry_hours
```

**Default threshold:** 5 hours (provides 1-hour buffer before URL actually expires)

### Refresh Flow

When expired URL detected:

1. Proxy calls `_refresh_stream_url(video_id)`
2. Runs StreamResolver in thread pool (it's synchronous):
   ```python
   loop = asyncio.get_event_loop()
   new_url = await loop.run_in_executor(
       None,
       self.stream_resolver.resolve_video_id,
       video_id
   )
   ```
3. Updates TrackStore with new URL and timestamp
4. Uses new URL for streaming

**Fallback:** If refresh fails, proxy attempts to use old URL (might still work).

### Manual Refresh

Force refresh of all URLs:
```bash
ytmpctl sync  # Triggers full playlist sync, refreshes all URLs
```

## Retry Logic & Error Handling

### Retry with Exponential Backoff

Transient errors (network timeouts, temporary failures) are retried:

```python
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds

# Retry delays: 1s, 2s, 4s (exponential: 2^attempt)
```

**Retried errors:**
- `aiohttp.ClientError` (except 403/404/410)
- `asyncio.TimeoutError`

**Not retried (permanent errors):**
- HTTP 403 (Forbidden)
- HTTP 404 (Not Found)
- HTTP 410 (Gone)

### Error Handling Hierarchy

```python
try:
    return await self._proxy_stream(request, stream_url, icy_name, video_id)
except web.HTTPException:
    raise  # Re-raise HTTP exceptions (already formatted)
except asyncio.TimeoutError:
    raise web.HTTPGatewayTimeout(...)
except YouTubeStreamError:
    raise web.HTTPBadGateway(...)
except Exception:
    logger.exception(...)
    raise web.HTTPInternalServerError(...)
finally:
    # Always decrement connection counter
    self._active_connections -= 1
```

## Connection Limiting

Prevents resource exhaustion by limiting concurrent streams:

```python
max_concurrent_streams = 10  # Configurable

async with self._connection_lock:
    if self._active_connections >= max_concurrent_streams:
        raise web.HTTPServiceUnavailable(...)
    self._active_connections += 1

try:
    return await self._proxy_stream(...)
finally:
    async with self._connection_lock:
        self._active_connections -= 1
```

**Lock:** `asyncio.Lock` ensures thread-safe counter updates.

**Behavior:** Returns HTTP 503 when limit reached.

**Tuning:** Increase limit for multiple simultaneous users, decrease to reduce memory usage.

## ICY Protocol

### ICY Headers

The proxy injects Icecast/Shoutcast metadata headers:

```http
HTTP/1.1 200 OK
Content-Type: audio/mpeg
icy-name: Rick Astley - Never Gonna Give You Up
icy-metaint: 16000
Cache-Control: no-cache, no-store
```

**Header Details:**
- `icy-name`: Formatted as "Artist - Title" (or "Unknown Artist - Title" if artist missing)
- `icy-metaint`: Metadata interval in bytes (16000 = 16KB chunks)
- `Cache-Control`: Prevents caching of streams

### MPD Compatibility

MPD parses ICY headers and makes metadata available to clients:

- **mpc current**: Shows `icy-name` value
- **ncmpcpp**: Displays artist/title in playlist and status views
- **MPD protocol**: Exposes via `Title` tag in status responses

## Performance Considerations

### Memory Usage

- **Per stream:** ~2-3 MB (buffering YouTube chunks)
- **10 concurrent streams:** ~25-30 MB
- **TrackStore:** Minimal (<1 MB for thousands of tracks)
- **Proxy server:** ~15-20 MB base overhead

**Total estimate:** 50-100 MB for proxy + daemon with moderate usage.

### Latency

- **Initial request:** <200ms overhead (database lookup + YouTube connection)
- **URL refresh:** 1-2 seconds (when triggered, happens every 5+ hours)
- **Streaming:** No additional latency (direct proxy of YouTube chunks)

### Concurrency

- **Architecture:** Fully async (asyncio + aiohttp)
- **Bottleneck:** YouTube connection speed (not proxy itself)
- **Scalability:** Tested with 10 concurrent streams without issues

## Configuration

### config.yaml Example

```yaml
# ICY Proxy Settings (add to ~/.config/ytmpd/config.yaml)
proxy_enabled: true
proxy_host: localhost
proxy_port: 8080
proxy_track_mapping_db: ~/.config/ytmpd/track_mapping.db

# Advanced (optional, set programmatically if needed)
# max_concurrent_streams: 10
# stream_timeout: 30  # seconds
```

### Disabling Proxy

To disable and use direct YouTube URLs:

```yaml
proxy_enabled: false
```

MPD playlists will contain direct YouTube URLs instead of proxy URLs.

## Debugging

### Enable Debug Logging

```yaml
log_level: DEBUG
```

### View Proxy Logs

```bash
# All proxy-related logs (tagged with [PROXY])
grep "\[PROXY\]" ~/.config/ytmpd/ytmpd.log

# URL refresh events
grep "URL refresh" ~/.config/ytmpd/ytmpd.log

# Connection limiting
grep "Connection limit" ~/.config/ytmpd/ytmpd.log

# Stream errors
grep "Stream error" ~/.config/ytmpd/ytmpd.log
```

### Check Proxy Status

```bash
# Verify proxy is listening
netstat -an | grep 8080
# Should show: tcp 0 0 127.0.0.1:8080 0.0.0.0:* LISTEN

# Count active connections
netstat -an | grep 8080 | grep ESTABLISHED | wc -l

# Test health endpoint
curl http://localhost:8080/health
# Should return: {"status":"ok","service":"icy-proxy"}
```

### Query TrackStore

```bash
# Count tracks
sqlite3 ~/.config/ytmpd/track_mapping.db "SELECT COUNT(*) FROM tracks;"

# List recent tracks
sqlite3 ~/.config/ytmpd/track_mapping.db \
  "SELECT video_id, artist, title, datetime(updated_at, 'unixepoch') FROM tracks LIMIT 10;"

# Find expired URLs (>5 hours old)
sqlite3 ~/.config/ytmpd/track_mapping.db \
  "SELECT video_id, artist, title FROM tracks WHERE (strftime('%s','now') - updated_at) > 18000;"
```

## Testing

### Unit Tests

```bash
# Run proxy tests
pytest tests/test_icy_proxy.py tests/test_track_store.py -v

# Run with coverage
pytest tests/test_icy_proxy.py tests/test_track_store.py --cov=ytmpd.icy_proxy --cov=ytmpd.track_store

# Coverage achieved: 97% (icy_proxy), 100% (track_store)
```

### Manual Testing

1. **Start ytmpd:**
   ```bash
   python -m ytmpd
   ```

2. **Verify proxy listening:**
   ```bash
   netstat -an | grep 8080
   ```

3. **Test health endpoint:**
   ```bash
   curl http://localhost:8080/health
   ```

4. **Sync playlists (populates TrackStore):**
   ```bash
   bin/ytmpctl sync
   ```

5. **Test proxy stream (replace with actual video_id):**
   ```bash
   curl -I http://localhost:8080/proxy/dQw4w9WgXcQ
   # Should return 200 OK with icy-name header
   ```

6. **Test with MPD:**
   ```bash
   mpc load "YT: Favorites"
   mpc play
   mpc current  # Should show "Artist - Title"
   ```

## Security Considerations

- **Local-only binding:** Default `host: localhost` prevents external access
- **Video ID validation:** Regex prevents injection attacks (`^[a-zA-Z0-9_-]{11}$`)
- **Connection limiting:** Prevents DoS via connection exhaustion
- **No shell commands:** StreamResolver uses Python API, not shell
- **Error message sanitization:** Internal errors don't expose paths

**Production deployment:** If exposing proxy externally, add:
- Authentication layer
- Rate limiting per IP
- HTTPS/TLS encryption
- Firewall rules

## Troubleshooting Guide

See README.md "ICY Metadata Proxy → Troubleshooting" section for common issues and solutions.

## Implementation References

- **aiohttp documentation:** https://docs.aiohttp.org/
- **ICY protocol spec:** https://cast.readme.io/docs/icy
- **MPD ICY support:** https://mpd.readthedocs.io/en/latest/protocol.html
- **SQLite threading:** https://docs.python.org/3/library/sqlite3.html#sqlite3-threadsafety

## Future Enhancements

Potential improvements (not currently implemented):

- [ ] Inline ICY metadata chunks (full Shoutcast protocol support)
- [ ] Stream transcoding (convert to different formats/bitrates)
- [ ] HTTPS support with self-signed certificates
- [ ] Prometheus metrics endpoint
- [ ] Connection pooling for YouTube requests
- [ ] Configurable URL refresh threshold per track
- [ ] Database cleanup (remove old/unused tracks)
- [ ] IPv6 support
