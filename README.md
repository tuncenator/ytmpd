# ytmpd - YouTube Music to MPD Sync Daemon

A smart sync daemon that bridges YouTube Music and MPD (Music Player Daemon). Automatically sync your YouTube Music playlists to MPD, enabling playback control through standard MPD clients like `mpc` and seamless integration with your existing i3 window manager setup.

## Architecture Overview

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

**What ytmpd does:**
- Fetches your YouTube Music playlists via ytmusicapi
- Resolves video IDs to streamable audio URLs using yt-dlp
- Creates/updates MPD playlists with "YT: " prefix
- Runs periodic auto-sync (configurable interval, default 30 minutes)
- Provides manual sync triggers via `ytmpctl sync`
- Caches stream URLs for 5 hours (YouTube URLs expire after ~6 hours)

**What you control playback with:**
- Standard MPD clients: `mpc`, `ncmpcpp`, `cantata`, etc.
- Your existing i3 keybindings (now using `mpc` instead of custom ytmpctl commands)
- Any MPD-compatible mobile apps

## Features

- **Automatic playlist sync**: Periodic background sync of YouTube Music playlists to MPD
- **Manual sync trigger**: Force immediate sync with `ytmpctl sync`
- **Playlist prefixing**: YouTube playlists appear in MPD as "YT: <playlist-name>"
- **URL caching**: Stream URLs cached for 5 hours to reduce yt-dlp overhead
- **ICY metadata proxy**: Built-in HTTP proxy injects track metadata into audio streams for display in MPD clients
- **Error handling**: Failed tracks don't stop sync, errors logged clearly
- **State persistence**: Tracks last sync time and statistics across daemon restarts
- **MPD-native playback**: Leverage MPD's robust audio playback instead of custom implementation
- **i3blocks integration**: Status display shows MPD playback state

## ICY Metadata Proxy

ytmpd includes a built-in streaming proxy that enables MPD clients to display track metadata (artist, title) instead of raw YouTube URLs.

### How It Works

The ICY proxy sits between MPD and YouTube, injecting ICY/Shoutcast metadata headers into the audio stream:

```
MPD client (mpc/ncmpcpp)
         ↓
MPD server (loads proxy URLs)
         ↓
ICY Proxy (http://localhost:8080/proxy/{video_id})
         ↓ (adds ICY headers: artist, title)
YouTube stream (raw audio)
```

When you load a playlist, MPD receives proxy URLs like `http://localhost:8080/proxy/dQw4w9WgXcQ` instead of direct YouTube URLs. The proxy:
1. Fetches track metadata from its database (populated during sync)
2. Retrieves the YouTube stream
3. Injects ICY headers (`icy-name: Artist - Title`)
4. Streams the audio to MPD with metadata intact

### Configuration

The proxy is **enabled by default**. Configure in `~/.config/ytmpd/config.yaml`:

```yaml
# ICY Proxy Settings
proxy_enabled: true              # Enable/disable proxy
proxy_host: localhost            # Proxy bind address
proxy_port: 8080                 # Proxy port
proxy_track_mapping_db: ~/.config/ytmpd/track_mapping.db  # Track metadata database
```

### Viewing Metadata in MPD Clients

**ncmpcpp:**
- Track metadata appears in the playlist view
- Current track shows "Artist - Title" in status bar
- Queue view displays formatted track names

**mpc:**
```bash
$ mpc current
Rick Astley - Never Gonna Give You Up

$ mpc playlist
YT: Favorites
Rick Astley - Never Gonna Give You Up
Queen - Bohemian Rhapsody
The Beatles - Hey Jude
```

### Automatic URL Refresh

YouTube stream URLs expire after ~6 hours. The proxy automatically:
- Detects expired URLs (checks timestamp > 5 hours old)
- Refreshes URLs using yt-dlp in the background
- Continues playback without interruption
- Falls back to old URL if refresh fails

**Manual refresh:**
```bash
ytmpctl sync  # Refreshes all URLs immediately
```

### Advanced Features

- **Concurrent streams**: Supports up to 10 simultaneous streams (configurable via `max_concurrent_streams`)
- **Retry logic**: Automatically retries failed requests with exponential backoff (1s, 2s, 4s)
- **Connection limiting**: Returns HTTP 503 when connection limit reached
- **Error handling**: Gracefully handles network failures, expired URLs, and stream errors

### Troubleshooting

**Problem: ncmpcpp still shows URLs instead of metadata**

Solutions:
1. Verify proxy is enabled: Check `proxy_enabled: true` in config
2. Restart ytmpd daemon to apply config changes
3. Check proxy is running: `netstat -an | grep 8080`
4. Verify tracks are in database:
   ```bash
   sqlite3 ~/.config/ytmpd/track_mapping.db "SELECT COUNT(*) FROM tracks;"
   ```

**Problem: Proxy port 8080 already in use**

Solutions:
1. Change port in config: Set `proxy_port: 8081` (or any free port)
2. Find process using port: `lsof -i :8080`
3. Restart ytmpd daemon

**Problem: Tracks fail to play after several hours**

Cause: YouTube URLs expire after ~6 hours. The proxy automatically refreshes them, but you can force immediate refresh.

Solutions:
1. Wait a few seconds - proxy is refreshing URL automatically
2. Force immediate sync: `ytmpctl sync`
3. Check logs for refresh errors: `grep "URL refresh" ~/.config/ytmpd/ytmpd.log`

**Problem: High memory usage**

Cause: Multiple concurrent streams or connection leaks.

Solutions:
1. Check active connections: `netstat -an | grep 8080 | grep ESTABLISHED | wc -l`
2. Reduce connection limit in config: `max_concurrent_streams: 5`
3. Restart daemon to reset connections
4. Check proxy logs: `grep "\[PROXY\]" ~/.config/ytmpd/ytmpd.log`

For detailed technical documentation, see [docs/ICY_PROXY.md](docs/ICY_PROXY.md).

## Requirements

- **Python 3.11 or higher**
- **[uv](https://github.com/astral-sh/uv)** for environment management
- **MPD (Music Player Daemon)** - must be installed and running
- **mpc** - MPD command-line client
- **YouTube Music account** (free or premium)

### MPD Setup

ytmpd requires a working MPD installation:

```bash
# Install MPD and mpc (Arch/Manjaro)
sudo pacman -S mpd mpc

# Or on Ubuntu/Debian
sudo apt install mpd mpc

# Enable and start MPD
systemctl --user enable mpd
systemctl --user start mpd
```

Verify MPD is running:
```bash
mpc status
```

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd ytmpd
```

### 2. Install uv (if not already installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. Create virtual environment and install dependencies

```bash
# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate

# Install ytmpd with development dependencies
uv pip install -e ".[dev]"
```

### 4. Setup YouTube Music Authentication

ytmpd uses browser-based authentication with YouTube Music. Extract request headers from your browser:

```bash
python -m ytmpd.ytmusic setup-browser
```

Follow the instructions to:
1. Open YouTube Music in your browser and log in
2. Open browser developer tools (F12)
3. Go to Network tab and reload the page
4. Find a request to `music.youtube.com` (e.g., browse endpoint)
5. Copy the request headers (Right-click → Copy → Copy as cURL, then extract headers)
6. Paste into the ytmusicapi interactive setup

This creates `~/.config/ytmpd/browser.json` with your authentication credentials.

**Note**: Browser authentication lasts approximately 2 years before you need to refresh it.

## Usage

### Starting the daemon

Start ytmpd in the background:

```bash
source .venv/bin/activate
python -m ytmpd &
```

The daemon will:
- Perform an initial sync immediately on startup
- Listen on Unix socket at `~/.config/ytmpd/sync_socket`
- Log to `~/.config/ytmpd/ytmpd.log`
- Persist sync state to `~/.config/ytmpd/sync_state.json`
- Auto-sync every 30 minutes (configurable)

### Using ytmpctl (sync control)

`ytmpctl` is now focused on sync operations, not playback:

```bash
# Trigger immediate sync
ytmpctl sync

# Check sync status and statistics
ytmpctl status

# List YouTube Music playlists
ytmpctl list-playlists

# Show help
ytmpctl help
```

### Using mpc (playback control)

All playback control is now through standard MPD clients:

```bash
# Load a YouTube playlist
mpc load "YT: Favorites"

# Playback controls
mpc play
mpc pause
mpc stop
mpc next
mpc prev

# Check status
mpc status

# Search and play tracks
mpc search title "wonderwall"
mpc play 1

# View current playlist
mpc playlist
```

### Example workflow

```bash
# 1. Start ytmpd daemon
$ python -m ytmpd &
[2025-10-17 10:00:00] [INFO] Starting ytmpd daemon...
[2025-10-17 10:00:05] [INFO] Sync complete: 5 playlists, 150 tracks

# 2. Check sync status
$ ytmpctl status
=== ytmpd Sync Status ===

Last sync: 2025-10-17 10:00:05
Daemon started: 2025-10-17 10:00:00

Status: Last sync successful

=== Last Sync Statistics ===
Playlists synced: 5
Tracks added: 150
Tracks failed: 3

# 3. List YouTube playlists
$ ytmpctl list-playlists
=== YouTube Music Playlists ===

  • Favorites (52 tracks)
  • Workout (28 tracks)
  • Chill Vibes (41 tracks)
  • Driving (35 tracks)
  • Focus Music (67 tracks)

Total: 5 playlists

To load a playlist in MPD, use:
  mpc load "YT: <playlist-name>"

# 4. Load and play a YouTube playlist
$ mpc load "YT: Favorites"
$ mpc play
Queen - Bohemian Rhapsody
[playing] #1/52   0:12/5:55 (3%)
volume:100%   repeat: off   random: off

# 5. Control playback with mpc
$ mpc next
The Beatles - Hey Jude

$ mpc pause
[paused] #2/52   0:05/7:06 (1%)
```

## i3 Integration

### i3 Keybindings

Update your i3 config (`~/.config/i3/config`) to use `mpc` instead of `ytmpctl`:

```
# MPD playback controls (ytmpd playlists)
bindsym $mod+Shift+p exec --no-startup-id mpc toggle
bindsym $mod+Shift+s exec --no-startup-id mpc stop
bindsym $mod+Shift+n exec --no-startup-id mpc next
bindsym $mod+Shift+b exec --no-startup-id mpc prev

# Refresh i3blocks after control
bindsym $mod+Shift+p exec --no-startup-id killall -SIGUSR1 i3blocks
bindsym $mod+Shift+n exec --no-startup-id killall -SIGUSR1 i3blocks
```

See `examples/i3-config` for a complete example.

### i3blocks Status Display

The `ytmpd-status` script now shows MPD playback status.

**Add to your i3blocks config** (`~/.config/i3blocks/config`):

```ini
[ytmpd]
command=/path/to/ytmpd/bin/ytmpd-status
interval=5
separator_block_width=15
```

**Reload i3blocks:**

```bash
killall -SIGUSR1 i3blocks
```

The status block will display:
- `▶ Queen - Bohemian Rhapsody [2:34/5:55]` (green) when playing
- `⏸ The Beatles - Hey Jude [1:23/7:06]` (yellow) when paused
- `⏹ MPD` (gray) when stopped

See `examples/i3blocks-config` for a complete example.

## Configuration

Configuration is stored in `~/.config/ytmpd/config.yaml` and is created automatically with default values on first run.

**Default configuration:**

```yaml
# Logging
log_level: INFO
log_file: ~/.config/ytmpd/ytmpd.log

# MPD Integration
mpd_socket_path: ~/.config/mpd/socket
sync_interval_minutes: 30
enable_auto_sync: true
playlist_prefix: "YT: "
stream_cache_hours: 5

# Legacy paths (maintained for compatibility)
socket_path: ~/.config/ytmpd/socket
state_file: ~/.config/ytmpd/state.json
```

See `examples/config.yaml` for documentation of all options.

### Configuration Options

#### MPD Integration
- **mpd_socket_path**: Path to MPD Unix socket (default: `~/.config/mpd/socket`)
- **sync_interval_minutes**: How often to auto-sync in minutes (default: 30)
- **enable_auto_sync**: Enable/disable periodic auto-sync (default: true)
- **playlist_prefix**: Prefix for YouTube playlists in MPD (default: "YT: ")
- **stream_cache_hours**: How long to cache stream URLs in hours (default: 5)

#### Logging
- **log_level**: Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **log_file**: Path to log file

## Troubleshooting

### Daemon won't start

**Problem**: Daemon exits immediately or shows errors in log

**Solutions**:

1. **Check MPD is running:**
   ```bash
   mpc status
   ```
   If MPD isn't running:
   ```bash
   systemctl --user start mpd
   ```

2. **Check MPD socket path:**
   ```bash
   ls ~/.config/mpd/socket
   ```
   If missing, check your MPD configuration (`~/.config/mpd/mpd.conf`) for the bind address.

3. **Check YouTube authentication:**
   ```bash
   ls ~/.config/ytmpd/browser.json
   ```
   If missing, run `python -m ytmpd.ytmusic setup-browser`

4. **Check logs:**
   ```bash
   tail -f ~/.config/ytmpd/ytmpd.log
   ```

### No playlists in MPD

**Problem**: ytmpctl status shows sync succeeded but no playlists appear in MPD

**Solutions**:

1. **Trigger manual sync:**
   ```bash
   ytmpctl sync
   ```

2. **Check sync status:**
   ```bash
   ytmpctl status
   ```
   Look for errors or failed playlists.

3. **List MPD playlists:**
   ```bash
   mpc lsplaylists | grep "^YT:"
   ```

4. **Check ytmpd logs:**
   ```bash
   grep ERROR ~/.config/ytmpd/ytmpd.log
   ```

### Playback not working

**Problem**: Playlists load but tracks won't play

**Solutions**:

1. **Check MPD status:**
   ```bash
   mpc status
   ```

2. **Check MPD outputs:**
   ```bash
   mpc outputs
   ```
   Enable disabled outputs:
   ```bash
   mpc enable 1
   ```

3. **Check MPD logs:**
   ```bash
   journalctl --user -u mpd -f
   ```

### Stream URLs expired

**Problem**: Tracks fail to play after several hours

**Cause**: YouTube stream URLs expire after ~6 hours. ytmpd caches URLs for 5 hours to provide a 1-hour buffer.

**Solution**:
- **Automatic**: Daemon re-syncs periodically (default every 30 minutes)
- **Manual**: Trigger immediate sync:
  ```bash
  ytmpctl sync
  ```

### Authentication issues

**Problem**: "Failed to authenticate" or HTTP 400/401 errors in logs

**Solutions**:

1. **Refresh browser authentication:**
   ```bash
   python -m ytmpd.ytmusic setup-browser
   ```

2. Make sure you're logged in to YouTube Music in your browser before extracting headers

3. Try using a different browser or incognito mode to get fresh headers

### i3blocks not updating

**Problem**: Status block shows old information

**Solutions**:

1. **Manually refresh:**
   ```bash
   killall -SIGUSR1 i3blocks
   ```

2. **Test status script:**
   ```bash
   bin/ytmpd-status
   ```

3. **Ensure script is executable:**
   ```bash
   chmod +x bin/ytmpd-status
   ```

## Development

### Running tests

```bash
# Run all tests (unit + integration)
pytest

# Run tests with coverage report
pytest --cov=ytmpd --cov-report=term-missing

# Run only unit tests
pytest tests/ --ignore=tests/integration/

# Run only integration tests
pytest tests/integration/

# Run specific test file
pytest tests/test_sync_engine.py
```

Current test coverage: **72%** (154 tests)

### Type checking

```bash
mypy ytmpd/
```

### Linting

```bash
# Check for issues
ruff check ytmpd/

# Auto-fix issues
ruff check --fix ytmpd/
```

### Formatting

```bash
# Format code
ruff format ytmpd/
```

## Architecture

### Components

1. **ytmpd daemon** (`ytmpd/daemon.py`): Background sync service with periodic loop
2. **MPD client** (`ytmpd/mpd_client.py`): Wrapper around python-mpd2 for playlist management
3. **YouTube Music client** (`ytmpd/ytmusic.py`): Fetches playlists and tracks via ytmusicapi
4. **Stream resolver** (`ytmpd/stream_resolver.py`): Resolves video IDs to stream URLs via yt-dlp
5. **Sync engine** (`ytmpd/sync_engine.py`): Orchestrates the YouTube → MPD sync
6. **ytmpctl client** (`bin/ytmpctl`): CLI for sync control and status
7. **i3blocks script** (`bin/ytmpd-status`): Status formatter for i3blocks display

### Data Flow

```
YouTube Music Playlists
         ↓ (ytmusicapi)
   YTMusicClient.get_user_playlists()
         ↓
   SyncEngine.sync_all_playlists()
         ↓
   StreamResolver.resolve_batch(video_ids)
         ↓ (yt-dlp)
   Stream URLs (cached 5 hours)
         ↓
   MPDClient.create_or_replace_playlist()
         ↓ (python-mpd2)
   MPD Server
         ↓
   mpc / ncmpcpp / cantata
         ↓
   Audio output
```

### Socket Protocol

The daemon listens on a simple Unix socket for sync commands:

**Client commands:**
```
sync          # Trigger immediate sync
status        # Get sync status and statistics
list          # List YouTube playlists
quit          # Shutdown daemon
```

**Server responses** (JSON):
```json
{
  "success": true,
  "message": "Sync triggered",
  "playlists_synced": 5,
  "tracks_added": 150
}
```

## Project Structure

```
ytmpd/
├── ytmpd/                      # Main package
│   ├── __init__.py
│   ├── __main__.py             # Daemon entry point
│   ├── config.py               # Configuration management
│   ├── daemon.py               # Main sync daemon
│   ├── mpd_client.py           # MPD client wrapper (python-mpd2)
│   ├── ytmusic.py              # YouTube Music API wrapper
│   ├── stream_resolver.py      # Video ID → stream URL resolver
│   ├── sync_engine.py          # Sync orchestration
│   └── exceptions.py           # Custom exceptions
├── bin/
│   ├── ytmpctl                 # Sync control CLI
│   └── ytmpd-status            # i3blocks status script
├── tests/                      # Test suite
│   ├── integration/            # Integration tests
│   │   └── test_full_workflow.py
│   ├── test_config.py
│   ├── test_daemon.py
│   ├── test_mpd_client.py
│   ├── test_stream_resolver.py
│   ├── test_sync_engine.py
│   ├── test_ytmpctl.py
│   └── test_ytmusic.py
├── examples/                   # Example configurations
│   ├── config.yaml             # Example ytmpd config
│   ├── i3-config               # Example i3 keybindings (mpc)
│   └── i3blocks-config         # Example i3blocks configuration
├── docs/
│   ├── agent/                  # AI agent workflow documentation
│   └── MIGRATION.md            # Migration guide from v1
├── pyproject.toml              # Project metadata and dependencies
├── README.md
└── .gitignore
```

## Migration from v1

If you're upgrading from the old ytmpd architecture (socket-based command server), see [docs/MIGRATION.md](docs/MIGRATION.md) for a detailed migration guide.

**Key changes:**
- ytmpd is now a sync daemon, not a command server
- Playback control moved to MPD (`mpc` commands)
- YouTube playlists appear in MPD with "YT: " prefix
- `ytmpctl` now focuses on sync operations (not playback)

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

### Development workflow

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and ensure coverage stays above 70%
5. Run type checking and linting
6. Submit a pull request

## Acknowledgments

- Built with [ytmusicapi](https://github.com/sigma67/ytmusicapi) by sigma67
- Built with [python-mpd2](https://github.com/Mic92/python-mpd2) for MPD integration
- Built with [yt-dlp](https://github.com/yt-dlp/yt-dlp) for stream URL extraction
- Inspired by [MPD](https://www.musicpd.org/) (Music Player Daemon)
