# ytmpd - Radio & Interactive Search Feature - Project Plan

**Feature/Initiative**: radio-search
**Type**: New Feature
**Created**: 2025-10-20
**Estimated Total Phases**: 6

---

## 📍 Project Location

**IMPORTANT: All paths in this document are relative to the project root.**

- **Project Root**: `/home/tunc/Sync/Programs/ytmpd`
- **Verify with**: `pwd` → should output `/home/tunc/Sync/Programs/ytmpd`

When you see a path like `ytmpd/daemon.py`, it means `/home/tunc/Sync/Programs/ytmpd/ytmpd/daemon.py`

---

## Project Overview

### Purpose

This feature adds two major capabilities to ytmpd:

1. **Radio from Currently Playing Song**: Generate a personalized radio playlist based on the currently playing track
2. **Interactive Search & Actions**: Search YouTube Music, select tracks, and take actions (play now, add to queue, start radio)

These features keep users in their ncmpcpp workflow - they can trigger commands via keybindings and results appear as MPD playlists or queue items that integrate seamlessly with their existing setup.

### Scope

**In Scope**:
- `ytmpctl radio --current` command to generate radio from current track
- `ytmpctl search` interactive CLI for searching YouTube Music
- Search result actions: play now, add to queue, start radio from selected track
- New daemon socket commands: radio, search, play, queue
- Configuration option for radio playlist size
- Error handling for all edge cases
- Integration tests for both features
- Documentation and i3 keybinding examples

**Out of Scope**:
- Radio from arbitrary video IDs (only from current track or search results)
- Playlist management beyond "YT: Radio"
- Search filters (genre, year, etc.) - simple text search only
- Search history or favorites
- GUI interface - terminal-only
- Batch operations (adding multiple tracks at once)

### Success Criteria

- [ ] User can generate radio playlist from currently playing YouTube Music track
- [ ] User can search YouTube Music and see formatted results
- [ ] User can play a searched track immediately (clearing queue)
- [ ] User can add searched tracks to queue without interrupting playback
- [ ] User can start radio from any searched track
- [ ] All features work with existing ncmpcpp/MPD workflow
- [ ] Error cases handled gracefully with clear messages
- [ ] Integration tests pass for both features
- [ ] README updated with new commands and i3 keybinding examples

---

## Architecture Overview

### Key Components

1. **Daemon Socket Protocol Extension**: New commands (radio, search, play, queue) handled by daemon
2. **Radio Generator**: Uses YouTube Music API's `get_watch_playlist()` with `radio=True`
3. **Search Handler**: Uses existing `YTMusicClient.search()` for YouTube Music search
4. **Interactive CLI**: Terminal UI in ytmpctl for search workflow
5. **Action Handlers**: MPD operations for play/queue/radio actions

### Data Flow

#### Radio Feature
```
ytmpctl radio --current
         ↓
Daemon socket: "radio current"
         ↓
MPDClient.get_current_song() → extract video_id
         ↓
YTMusicClient.get_watch_playlist(video_id, radio=True)
         ↓
StreamResolver.resolve_batch(video_ids)
         ↓
MPDClient.create_or_replace_playlist("YT: Radio")
         ↓
User loads "YT: Radio" in ncmpcpp
```

#### Search Feature
```
ytmpctl search
         ↓
[Interactive] User enters query
         ↓
Daemon socket: "search <query>"
         ↓
YTMusicClient.search(query) → results
         ↓
[Interactive] Display results, user selects track
         ↓
[Interactive] User selects action
         ↓
Daemon socket: "play <video_id>" | "queue <video_id>" | "radio <video_id>"
         ↓
StreamResolver.resolve(video_id)
         ↓
MPDClient: clear+add+play | add | create_radio_playlist
```

### Technology Stack

- **Language**: Python 3.11+
- **Key Libraries**:
  - ytmusicapi (YouTube Music API - already has `get_watch_playlist` and `search`)
  - python-mpd2 (MPD client)
  - yt-dlp (stream URL resolution)
  - Built-in `input()` for interactive CLI
- **Testing**: pytest, pytest-asyncio
- **Package Manager**: uv

---

## Phase Breakdown

> **Note for Agents**: Only read the section for your assigned phase. Reading all phases wastes context.

---

### Phase 1: Configuration Extension

**Objective**: Add configuration support for radio feature and prepare codebase for new features

**Estimated Context Budget**: ~30k tokens

#### Deliverables

1. Update `ytmpd/config.py` to add `radio_playlist_limit` configuration option
2. Update `examples/config.yaml` with documented default value
3. Add configuration validation tests
4. Ensure config loads correctly in daemon

#### Detailed Requirements

**File: `ytmpd/config.py`**

Add new configuration field to the Config class:
```python
@dataclass
class Config:
    # ... existing fields ...
    radio_playlist_limit: int = 25  # Number of tracks for radio playlists
```

Add validation:
- `radio_playlist_limit` must be between 10 and 50
- Raise `ConfigError` if invalid

**File: `examples/config.yaml`**

Add documentation:
```yaml
# Radio Feature Settings
radio_playlist_limit: 25  # Number of tracks to fetch for radio playlists (10-50)
```

**File: `tests/test_config.py`**

Add tests:
- `test_config_radio_playlist_limit_default()` - verify default value
- `test_config_radio_playlist_limit_valid()` - test valid range
- `test_config_radio_playlist_limit_invalid()` - test validation errors

#### Dependencies

**Requires**: None (first phase)

**Enables**: Phase 2, 3 (radio implementation needs config)

#### Completion Criteria

- [ ] `radio_playlist_limit` field added to Config class with default value 25
- [ ] Validation ensures value is between 10 and 50
- [ ] `examples/config.yaml` updated with documented example
- [ ] Tests written and passing for all validation cases
- [ ] Config loads successfully in daemon without errors

#### Testing Requirements

- Unit tests for configuration loading
- Unit tests for validation (valid and invalid values)
- Verify daemon starts with updated config

#### Notes

- Keep changes minimal - this is a setup phase
- Don't implement any radio logic yet
- Ensure backward compatibility - existing configs without this field should work

---

### Phase 2: Daemon Socket Protocol Extension

**Objective**: Extend daemon socket protocol to handle new commands (radio, search, play, queue)

**Estimated Context Budget**: ~50k tokens

#### Deliverables

1. Add new socket command handlers to `ytmpd/daemon.py`
2. Implement command parsing for: `radio <video_id>`, `search <query>`, `play <video_id>`, `queue <video_id>`
3. Add stub handlers (return success/not implemented yet messages)
4. Update socket protocol documentation
5. Add tests for new commands

#### Detailed Requirements

**File: `ytmpd/daemon.py`**

Extend the command handler in the daemon to recognize new commands:

```python
async def handle_socket_command(self, command: str) -> dict:
    """Handle commands from ytmpctl client."""
    parts = command.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else None

    if cmd == "radio":
        return await self._handle_radio(arg)
    elif cmd == "search":
        return await self._handle_search(arg)
    elif cmd == "play":
        return await self._handle_play(arg)
    elif cmd == "queue":
        return await self._handle_queue(arg)
    # ... existing commands (sync, status, list, quit) ...
```

Implement stub handlers:
- `_handle_radio(video_id: str)` - validate video_id format, return "not implemented"
- `_handle_search(query: str)` - validate query not empty, return "not implemented"
- `_handle_play(video_id: str)` - validate video_id format, return "not implemented"
- `_handle_queue(video_id: str)` - validate video_id format, return "not implemented"

Video ID validation:
- Must be exactly 11 characters (YouTube video ID format)
- Alphanumeric plus `-` and `_`
- Return error response if invalid: `{"success": false, "error": "Invalid video ID format"}`

Query validation:
- Must not be empty or whitespace-only
- Return error response if invalid: `{"success": false, "error": "Empty search query"}`

**Return format** (for stub handlers):
```python
{"success": true, "message": "Command received: radio (not yet implemented)"}
```

#### Dependencies

**Requires**: Phase 1 complete

**Enables**: Phases 3, 4, 5 (command handlers will be filled in)

#### Completion Criteria

- [ ] New command parsing added to daemon socket handler
- [ ] All four stub handlers implemented with validation
- [ ] Video ID validation works correctly
- [ ] Query validation works correctly
- [ ] Error responses return proper format
- [ ] Tests written and passing for all new commands
- [ ] Daemon starts and accepts new commands via socket

#### Testing Requirements

**File: `tests/test_daemon.py`**

Add tests:
- `test_daemon_radio_command_stub()` - sends "radio VIDEO_ID", expects stub response
- `test_daemon_radio_invalid_video_id()` - sends invalid video ID, expects error
- `test_daemon_search_command_stub()` - sends "search query", expects stub response
- `test_daemon_search_empty_query()` - sends empty query, expects error
- `test_daemon_play_command_stub()` - sends "play VIDEO_ID", expects stub response
- `test_daemon_queue_command_stub()` - sends "queue VIDEO_ID", expects stub response

#### Notes

- Focus on protocol and validation - don't implement actual functionality yet
- Ensure backward compatibility - existing commands (sync, status, list) still work
- Return consistent JSON response format
- Log all new commands at INFO level for debugging

---

### Phase 3: Radio Feature - Complete Implementation

**Objective**: Implement full radio playlist generation from currently playing track

**Estimated Context Budget**: ~60k tokens

#### Deliverables

1. Implement `_handle_radio()` in daemon with full logic
2. Add video ID extraction from MPD current track (proxy URL parsing)
3. Integrate with YouTube Music API's `get_watch_playlist()`
4. Create "YT: Radio" playlist in MPD
5. Implement `ytmpctl radio --current` CLI command
6. Error handling for all edge cases
7. Add comprehensive tests

#### Detailed Requirements

**File: `ytmpd/daemon.py`**

Implement `_handle_radio(video_id: str | None)`:

```python
async def _handle_radio(self, video_id: str | None) -> dict:
    """
    Generate radio playlist from video ID or current track.

    Args:
        video_id: YouTube video ID, or None to use current MPD track

    Returns:
        Success/error response with track count
    """
    try:
        # If no video_id provided, extract from current MPD track
        if video_id is None:
            current = self.mpd_client.current()
            if not current:
                return {"success": False, "error": "No track currently playing"}

            video_id = self._extract_video_id_from_url(current.get("file", ""))
            if not video_id:
                return {"success": False, "error": "Current track is not a YouTube track"}

        # Get radio playlist from YouTube Music
        radio_tracks = self.ytmusic_client.get_watch_playlist(
            videoId=video_id,
            radio=True,
            limit=self.config.radio_playlist_limit
        )

        if not radio_tracks:
            return {"success": False, "error": "Failed to generate radio playlist"}

        # Extract video IDs
        video_ids = [track["videoId"] for track in radio_tracks if "videoId" in track]

        # Resolve stream URLs
        resolved = await self.stream_resolver.resolve_batch(video_ids)

        # Create MPD playlist
        playlist_name = "YT: Radio"
        self.mpd_client.create_or_replace_playlist(playlist_name, resolved)

        return {
            "success": True,
            "message": f"Radio playlist created: {len(resolved)} tracks",
            "tracks": len(resolved),
            "playlist": playlist_name
        }

    except Exception as e:
        self.logger.error(f"Radio generation failed: {e}")
        return {"success": False, "error": str(e)}
```

Helper method:
```python
def _extract_video_id_from_url(self, url: str) -> str | None:
    """
    Extract YouTube video ID from proxy URL.

    Proxy URLs follow pattern: http://localhost:PORT/proxy/VIDEO_ID

    Returns:
        11-character video ID or None if not a proxy URL
    """
    if not url:
        return None

    # Match pattern: */proxy/{video_id}
    import re
    match = re.search(r'/proxy/([A-Za-z0-9_-]{11})$', url)
    return match.group(1) if match else None
```

**File: `bin/ytmpctl`**

Add radio command:

```bash
# In the main command handler
if [ "$1" = "radio" ]; then
    if [ "$2" = "--current" ] || [ -z "$2" ]; then
        send_command "radio"
    else
        echo "Usage: ytmpctl radio --current"
        echo "Generate radio playlist from currently playing track"
        exit 1
    fi
    exit 0
fi
```

Update help message to include radio command.

**Error Cases to Handle**:
1. No track playing → clear error message
2. Current track not a YouTube track → clear error message
3. YouTube API failure → log error, return failure
4. Stream resolution failures → skip failed tracks, continue with rest (at least some tracks)
5. MPD playlist creation failure → return error

#### Dependencies

**Requires**:
- Phase 1: Config with `radio_playlist_limit`
- Phase 2: Socket protocol for radio command

**Enables**:
- Phase 5: Search feature can reuse radio generation logic

#### Completion Criteria

- [ ] `_handle_radio()` fully implemented with error handling
- [ ] Video ID extraction from proxy URLs works correctly
- [ ] YouTube Music API integration working (get_watch_playlist with radio=True)
- [ ] Stream URL resolution working for batch of video IDs
- [ ] "YT: Radio" playlist created in MPD successfully
- [ ] `ytmpctl radio --current` command works end-to-end
- [ ] All error cases handled with clear messages
- [ ] Tests written and passing
- [ ] Manual testing successful with live MPD/YouTube Music

#### Testing Requirements

**File: `tests/test_daemon.py`**

Add tests:
- `test_extract_video_id_from_proxy_url()` - test URL parsing
- `test_extract_video_id_from_invalid_url()` - test with non-proxy URLs
- `test_radio_no_current_track()` - error when nothing playing
- `test_radio_non_youtube_track()` - error when current isn't YouTube
- `test_radio_generation_success()` - mock full workflow

**File: `tests/test_ytmpctl.py`**

Add test:
- `test_ytmpctl_radio_current()` - test CLI command

**Integration test** (manual or scripted):
- Start MPD with a YouTube track playing
- Run `ytmpctl radio --current`
- Verify "YT: Radio" playlist appears in MPD
- Verify playlist contains ~25 tracks

#### Notes

- Use existing `YTMusicClient.get_watch_playlist()` - no need to implement new API calls
- Reuse existing `StreamResolver.resolve_batch()` for URL resolution
- Handle partial failures gracefully - if 23/25 tracks resolve, that's acceptable
- Log radio generation at INFO level: "Generated radio from {video_id}: {count} tracks"
- Consider rate limiting if YouTube API has restrictions

---

### Phase 4: Search Feature - YouTube Music Integration

**Objective**: Implement YouTube Music search and track-level stream resolution, plus daemon handlers for play/queue actions

**Estimated Context Budget**: ~50k tokens

#### Deliverables

1. Implement search logic in daemon using existing `YTMusicClient`
2. Implement play and queue handlers in daemon
3. Add stream URL resolution for individual tracks
4. Add MPD operations: clear+add+play, add to queue
5. Add comprehensive tests

#### Detailed Requirements

**File: `ytmpd/daemon.py`**

Implement `_handle_search(query: str)`:

```python
async def _handle_search(self, query: str) -> dict:
    """
    Search YouTube Music and return formatted results.

    Args:
        query: Search query string

    Returns:
        Success response with search results or error
    """
    try:
        if not query or not query.strip():
            return {"success": False, "error": "Empty search query"}

        # Search YouTube Music (limit to 10 results)
        results = self.ytmusic_client.search(query, filter="songs", limit=10)

        if not results:
            return {"success": True, "results": [], "count": 0}

        # Format results
        formatted = []
        for idx, track in enumerate(results, 1):
            formatted.append({
                "number": idx,
                "video_id": track.get("videoId", ""),
                "title": track.get("title", "Unknown"),
                "artist": self._format_artists(track.get("artists", [])),
                "duration": self._format_duration(track.get("duration_seconds", 0))
            })

        return {
            "success": True,
            "results": formatted,
            "count": len(formatted)
        }

    except Exception as e:
        self.logger.error(f"Search failed: {e}")
        return {"success": False, "error": str(e)}

def _format_artists(self, artists: list) -> str:
    """Format artist list as comma-separated string."""
    if not artists:
        return "Unknown Artist"
    return ", ".join(artist.get("name", "") for artist in artists)

def _format_duration(self, seconds: int) -> str:
    """Format duration in seconds as MM:SS."""
    if not seconds:
        return "Unknown"
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins}:{secs:02d}"
```

Implement `_handle_play(video_id: str)`:

```python
async def _handle_play(self, video_id: str) -> dict:
    """
    Play a track immediately (clear queue, add track, start playback).

    Args:
        video_id: YouTube video ID

    Returns:
        Success/error response
    """
    try:
        # Resolve stream URL
        stream_url = await self.stream_resolver.resolve(video_id)
        if not stream_url:
            return {"success": False, "error": "Failed to resolve stream URL"}

        # Get track metadata for display
        track_info = await self._get_track_info(video_id)

        # Clear queue, add track, play
        self.mpd_client.clear()
        self.mpd_client.add(stream_url)
        self.mpd_client.play()

        return {
            "success": True,
            "message": f"Now playing: {track_info['title']} - {track_info['artist']}"
        }

    except Exception as e:
        self.logger.error(f"Play failed: {e}")
        return {"success": False, "error": str(e)}
```

Implement `_handle_queue(video_id: str)`:

```python
async def _handle_queue(self, video_id: str) -> dict:
    """
    Add track to MPD queue without interrupting playback.

    Args:
        video_id: YouTube video ID

    Returns:
        Success/error response
    """
    try:
        # Resolve stream URL
        stream_url = await self.stream_resolver.resolve(video_id)
        if not stream_url:
            return {"success": False, "error": "Failed to resolve stream URL"}

        # Get track metadata
        track_info = await self._get_track_info(video_id)

        # Add to queue (doesn't interrupt current playback)
        self.mpd_client.add(stream_url)

        return {
            "success": True,
            "message": f"Added to queue: {track_info['title']} - {track_info['artist']}"
        }

    except Exception as e:
        self.logger.error(f"Queue failed: {e}")
        return {"success": False, "error": str(e)}

async def _get_track_info(self, video_id: str) -> dict:
    """
    Get track metadata from YouTube Music.

    Returns dict with 'title' and 'artist' keys.
    """
    try:
        # Use YTMusicClient to get track info
        info = self.ytmusic_client.get_song(video_id)
        return {
            "title": info.get("title", "Unknown"),
            "artist": self._format_artists(info.get("artists", []))
        }
    except:
        return {"title": "Unknown", "artist": "Unknown Artist"}
```

**File: `ytmpd/mpd_client.py`**

Add helper methods if needed:

```python
def clear(self) -> None:
    """Clear the current MPD queue."""
    self.client.clear()

def add(self, url: str) -> None:
    """Add a URL to the MPD queue."""
    self.client.add(url)

def play(self, position: int | None = None) -> None:
    """Start playback (optionally at specific position)."""
    if position is not None:
        self.client.play(position)
    else:
        self.client.play()
```

#### Dependencies

**Requires**:
- Phase 2: Socket protocol for search, play, queue commands

**Enables**:
- Phase 5: Interactive CLI will use these daemon handlers

#### Completion Criteria

- [ ] `_handle_search()` implemented with YouTube Music API
- [ ] Search results formatted correctly (number, title, artist, duration)
- [ ] `_handle_play()` implemented (clear + add + play)
- [ ] `_handle_queue()` implemented (add without interrupting)
- [ ] Stream URL resolution working for single tracks
- [ ] Track metadata retrieval working
- [ ] All error cases handled
- [ ] Tests written and passing

#### Testing Requirements

**File: `tests/test_daemon.py`**

Add tests:
- `test_search_success()` - mock search with results
- `test_search_empty_query()` - error handling
- `test_search_no_results()` - handle empty results
- `test_format_artists()` - test artist formatting
- `test_format_duration()` - test duration formatting
- `test_play_success()` - mock full play workflow
- `test_play_resolution_failure()` - handle resolution errors
- `test_queue_success()` - mock queue workflow
- `test_get_track_info()` - test metadata retrieval

**File: `tests/test_mpd_client.py`**

Add tests (if new methods added):
- `test_mpd_clear()` - test queue clearing
- `test_mpd_add()` - test adding URL
- `test_mpd_play()` - test starting playback

#### Notes

- Use existing `YTMusicClient.search()` with `filter="songs"` for best results
- Handle missing metadata gracefully (fallback to "Unknown")
- Stream resolution may take a few seconds - log progress
- Don't implement CLI yet - focus on daemon-side logic
- Ensure operations don't block the daemon event loop (use async properly)

---

### Phase 5: Search Feature - Interactive CLI

**Objective**: Implement interactive terminal UI in ytmpctl for search workflow

**Estimated Context Budget**: ~70k tokens

#### Deliverables

1. Implement `ytmpctl search` command with interactive flow
2. Search input prompt
3. Results display (numbered list with title, artist, duration)
4. Track selection prompt
5. Action menu (play now, add to queue, start radio, cancel)
6. Integration with daemon socket for all actions
7. Input validation and error handling
8. Ctrl+C handling (clean exit)
9. Add comprehensive tests

#### Detailed Requirements

**File: `bin/ytmpctl`**

Add search command handler:

```bash
# In main command handler
if [ "$1" = "search" ]; then
    python3 <<'PYTHON_SCRIPT'
import socket
import json
import sys
import os

# Configuration
SOCKET_PATH = os.path.expanduser("~/.config/ytmpd/sync_socket")

def send_daemon_command(cmd):
    """Send command to daemon and return response."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(SOCKET_PATH)
        sock.sendall(cmd.encode('utf-8'))
        response = sock.recv(4096).decode('utf-8')
        sock.close()
        return json.loads(response)
    except Exception as e:
        print(f"Error communicating with daemon: {e}", file=sys.stderr)
        sys.exit(1)

def interactive_search():
    """Interactive search workflow."""
    try:
        # Step 1: Get search query
        print("Search YouTube Music:")
        query = input().strip()

        if not query:
            print("Empty query. Exiting.")
            sys.exit(0)

        # Step 2: Send search command to daemon
        response = send_daemon_command(f"search {query}")

        if not response.get("success"):
            print(f"Search failed: {response.get('error', 'Unknown error')}")
            sys.exit(1)

        results = response.get("results", [])
        if not results:
            print("No results found.")
            sys.exit(0)

        # Step 3: Display results
        print(f"\nSearch results for \"{query}\":\n")
        for track in results:
            print(f"  {track['number']}. {track['title']} - {track['artist']} ({track['duration']})")

        # Step 4: Get track selection
        print(f"\nEnter number (1-{len(results)}), or 'q' to quit:")
        selection = input().strip().lower()

        if selection == 'q':
            print("Cancelled.")
            sys.exit(0)

        try:
            track_num = int(selection)
            if track_num < 1 or track_num > len(results):
                print(f"Invalid selection. Must be between 1 and {len(results)}.")
                sys.exit(1)
        except ValueError:
            print("Invalid input. Must be a number or 'q'.")
            sys.exit(1)

        selected_track = results[track_num - 1]

        # Step 5: Display action menu
        print(f"\nSelected: {selected_track['title']} - {selected_track['artist']}\n")
        print("Actions:")
        print("  1. Play now")
        print("  2. Add to queue")
        print("  3. Start radio from this song")
        print("  4. Cancel")
        print("\nEnter choice (1-4):")

        action = input().strip()

        if action == '4':
            print("Cancelled.")
            sys.exit(0)

        video_id = selected_track['video_id']

        # Step 6: Execute action
        if action == '1':
            # Play now
            resp = send_daemon_command(f"play {video_id}")
            if resp.get("success"):
                print(resp.get("message", "Playing..."))
            else:
                print(f"Error: {resp.get('error', 'Failed to play')}")
                sys.exit(1)

        elif action == '2':
            # Add to queue
            resp = send_daemon_command(f"queue {video_id}")
            if resp.get("success"):
                print(resp.get("message", "Added to queue."))
            else:
                print(f"Error: {resp.get('error', 'Failed to add to queue')}")
                sys.exit(1)

        elif action == '3':
            # Start radio
            resp = send_daemon_command(f"radio {video_id}")
            if resp.get("success"):
                print(resp.get("message", "Radio playlist created."))
            else:
                print(f"Error: {resp.get('error', 'Failed to generate radio')}")
                sys.exit(1)

        else:
            print("Invalid choice. Must be 1-4.")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)

# Run interactive search
interactive_search()
PYTHON_SCRIPT
    exit 0
fi
```

Update help message to include search command:

```bash
if [ "$1" = "help" ] || [ "$1" = "--help" ] || [ -z "$1" ]; then
    echo "ytmpctl - Control ytmpd daemon"
    echo ""
    echo "Commands:"
    echo "  sync              Trigger immediate playlist sync"
    echo "  status            Show sync status and statistics"
    echo "  list              List YouTube Music playlists"
    echo "  radio --current   Generate radio from currently playing track"
    echo "  search            Interactive search for YouTube Music tracks"
    echo "  help              Show this help message"
    exit 0
fi
```

#### Error Handling Requirements

All error cases must be handled gracefully:

1. **Empty query**: Exit with message "Empty query. Exiting."
2. **No results**: Display "No results found." and exit cleanly
3. **Invalid track selection**:
   - Non-number → "Invalid input. Must be a number or 'q'."
   - Out of range → "Invalid selection. Must be between 1 and N."
4. **Invalid action**: "Invalid choice. Must be 1-4."
5. **Daemon communication error**: Display error and exit with code 1
6. **Ctrl+C at any point**: Print "\nCancelled." and exit with code 0

#### Dependencies

**Requires**:
- Phase 2: Socket protocol
- Phase 3: Radio implementation (for action 3)
- Phase 4: Search/play/queue handlers (for all actions)

**Enables**:
- Phase 6: Integration testing

#### Completion Criteria

- [ ] `ytmpctl search` command implemented
- [ ] Interactive flow works end-to-end
- [ ] Search query prompt works
- [ ] Results display formatted correctly
- [ ] Track selection validates input
- [ ] Action menu displays and validates choices
- [ ] All 4 actions work correctly (play, queue, radio, cancel)
- [ ] Error handling for all edge cases
- [ ] Ctrl+C handled gracefully at all prompts
- [ ] Help message updated with search command
- [ ] Manual testing successful

#### Testing Requirements

**File: `tests/test_ytmpctl.py`**

Add tests (using mock input/output):
- `test_ytmpctl_search_flow()` - mock full workflow
- `test_ytmpctl_search_empty_query()` - test empty input
- `test_ytmpctl_search_no_results()` - test with no results
- `test_ytmpctl_search_invalid_selection()` - test invalid track number
- `test_ytmpctl_search_cancel()` - test 'q' to quit
- `test_ytmpctl_search_play_action()` - test play now action
- `test_ytmpctl_search_queue_action()` - test add to queue action
- `test_ytmpctl_search_radio_action()` - test radio action

**Manual Testing Checklist**:
- [ ] Start daemon
- [ ] Run `ytmpctl search`
- [ ] Enter query "miles davis"
- [ ] Verify results display correctly
- [ ] Select a track (e.g., "2")
- [ ] Try action 1 (play now) - verify track plays in MPD
- [ ] Run search again, try action 2 (add to queue) - verify added without interrupting
- [ ] Run search again, try action 3 (start radio) - verify "YT: Radio" playlist created
- [ ] Run search again, try action 4 (cancel) - verify exits cleanly
- [ ] Test Ctrl+C at each prompt - verify clean exit
- [ ] Test invalid inputs at each step - verify error messages

#### Notes

- Use Python inline script in bash for easier interactive I/O handling
- Keep the UI simple - no fancy colors or libraries, just plain text
- Input validation is critical - users will make typos
- Ensure socket communication errors are user-friendly
- Log all search actions at INFO level in daemon
- Consider adding a config option for search result limit in future phases

---

### Phase 6: Integration Testing & Documentation

**Objective**: Comprehensive integration tests, manual testing workflow, documentation updates

**Estimated Context Budget**: ~40k tokens

#### Deliverables

1. End-to-end integration tests for both features
2. Manual testing workflow and verification
3. Update README.md with new features
4. Add i3 keybinding examples
5. Update examples/config.yaml with complete documentation
6. Final verification that all completion criteria met

#### Detailed Requirements

**File: `tests/integration/test_radio_search.py`**

Create comprehensive integration tests:

```python
import pytest
from ytmpd.daemon import Daemon
from ytmpd.config import Config

class TestRadioIntegration:
    """Integration tests for radio feature."""

    async def test_radio_from_current_track(self):
        """Test radio generation from currently playing track."""
        # Setup: Start MPD with a YouTube track
        # Execute: Generate radio
        # Verify: "YT: Radio" playlist exists with ~25 tracks
        pass

    async def test_radio_no_current_track(self):
        """Test radio when nothing is playing."""
        # Verify proper error message
        pass

    async def test_radio_non_youtube_track(self):
        """Test radio when current track is local file."""
        # Verify proper error message
        pass

class TestSearchIntegration:
    """Integration tests for search feature."""

    async def test_search_and_play(self):
        """Test search -> select -> play now workflow."""
        # Execute: Search, get results, play a track
        # Verify: Track is playing in MPD
        pass

    async def test_search_and_queue(self):
        """Test search -> select -> add to queue workflow."""
        # Setup: Start playback
        # Execute: Search and add to queue
        # Verify: Queue has new track, playback not interrupted
        pass

    async def test_search_and_radio(self):
        """Test search -> select -> start radio workflow."""
        # Execute: Search and start radio
        # Verify: "YT: Radio" playlist created
        pass
```

**File: `README.md`**

Add new section after "Usage" section:

```markdown
### Radio and Search Features

#### Generate Radio from Current Track

Generate a personalized radio playlist based on the currently playing song:

```bash
ytmpctl radio --current
```

The daemon will:
1. Detect the currently playing YouTube Music track
2. Generate a ~25 track radio playlist using YouTube Music's recommendation algorithm
3. Create/update the "YT: Radio" playlist in MPD

Then load and play it:
```bash
mpc load "YT: Radio"
mpc play
```

**Error cases:**
- No track playing: "No track currently playing"
- Current track is not from YouTube Music: "Current track is not a YouTube track"

#### Interactive Search

Search YouTube Music and take actions on results:

```bash
ytmpctl search
```

**Workflow:**
1. Enter your search query (e.g., "miles davis kind of blue")
2. Browse results (shows title, artist, duration)
3. Select a track by number
4. Choose an action:
   - **Play now**: Clear queue, play this track immediately
   - **Add to queue**: Append to queue without interrupting playback
   - **Start radio**: Generate radio playlist from this track
   - **Cancel**: Exit without action

**Example:**
```bash
$ ytmpctl search
Search YouTube Music:
miles davis kind of blue

Search results for "miles davis kind of blue":

  1. So What - Miles Davis (9:22)
  2. Freddie Freeloader - Miles Davis (9:33)
  3. Blue in Green - Miles Davis (5:37)
  4. All Blues - Miles Davis (11:33)
  5. Flamenco Sketches - Miles Davis (9:26)

Enter number (1-5), or 'q' to quit:
2

Selected: Freddie Freeloader - Miles Davis

Actions:
  1. Play now
  2. Add to queue
  3. Start radio from this song
  4. Cancel

Enter choice (1-4):
1
Now playing: Freddie Freeloader - Miles Davis
```
```

**File: `examples/i3-config`**

Add new keybindings section:

```
# Radio and Search features
bindsym $mod+Shift+r exec --no-startup-id ytmpctl radio --current  # Generate radio from current
bindsym $mod+Shift+f exec --no-startup-id alacritty -e ytmpctl search  # Open search in terminal
```

**File: `examples/config.yaml`**

Ensure radio config is documented:

```yaml
# Radio Feature Settings
radio_playlist_limit: 25  # Number of tracks to fetch for radio playlists (10-50)
                          # Higher values give more variety but take longer to resolve
```

#### Manual Testing Workflow

Create comprehensive manual test checklist:

**Radio Feature:**
- [ ] Start MPD and load a YouTube Music playlist
- [ ] Play a track
- [ ] Run `ytmpctl radio --current`
- [ ] Verify success message with track count
- [ ] Check `mpc lsplaylists | grep "YT: Radio"` shows the playlist
- [ ] Load and play "YT: Radio" playlist
- [ ] Verify tracks play correctly
- [ ] Test error: run radio when nothing is playing
- [ ] Test error: play a local file (not YouTube), try radio

**Search Feature - Play Now:**
- [ ] Run `ytmpctl search`
- [ ] Enter a query (e.g., "beatles")
- [ ] Select a track
- [ ] Choose action 1 (Play now)
- [ ] Verify track starts playing immediately
- [ ] Verify queue was cleared

**Search Feature - Add to Queue:**
- [ ] Start playing a track
- [ ] Run search, select track, choose action 2 (Add to queue)
- [ ] Verify current track keeps playing
- [ ] Verify new track appears in queue (`mpc playlist`)

**Search Feature - Start Radio:**
- [ ] Run search, select track, choose action 3 (Start radio)
- [ ] Verify "YT: Radio" playlist created
- [ ] Load and play it

**Search Feature - Error Handling:**
- [ ] Test empty query (just press Enter)
- [ ] Test query with no results (gibberish)
- [ ] Test invalid track selection (0, 999, "abc")
- [ ] Test invalid action choice (0, 5, "xyz")
- [ ] Test Ctrl+C at each prompt

#### Dependencies

**Requires**: All previous phases (1-5) complete

**Enables**: Feature is complete and ready for merge

#### Completion Criteria

- [ ] Integration tests written and passing
- [ ] Manual testing completed with all scenarios passing
- [ ] README updated with radio and search documentation
- [ ] i3 keybinding examples added
- [ ] examples/config.yaml fully documented
- [ ] All project success criteria met
- [ ] No known critical bugs
- [ ] Ready for code review and merge

#### Testing Requirements

- Complete all integration tests in `tests/integration/test_radio_search.py`
- Execute manual testing workflow checklist
- Ensure test coverage >70% overall
- Run full test suite: `pytest --cov=ytmpd`
- Run type checking: `mypy ytmpd/`
- Run linting: `ruff check ytmpd/`

#### Notes

- This is the final phase - ensure everything is polished
- Update any documentation that was affected by changes
- Consider edge cases that might not have been covered
- Test with real YouTube Music API (not just mocks)
- Verify nothing broke existing functionality (sync, status, list)
- Consider performance with large search results or long radio playlists

---

## Phase Dependencies Graph

```
Phase 1 (Config Extension)
    ↓
Phase 2 (Socket Protocol) ←──────┐
    ↓                             │
Phase 3 (Radio Feature) ──────────┤
    ↓                             │
Phase 4 (Search Backend) ─────────┤
    ↓                             │
Phase 5 (Search CLI) ─────────────┘
    ↓
Phase 6 (Integration & Docs)
```

---

## Cross-Cutting Concerns

### Code Style

- Follow existing ytmpd code style
- Type hints for all function signatures
- Docstrings (Google style) for all public functions
- Maximum line length: 100 characters (per ruff config)
- Use async/await properly - don't block event loop

### Error Handling

- Use descriptive error messages
- Log all errors at ERROR level
- Return user-friendly error messages via socket protocol
- Don't expose internal errors to users (log them instead)

### Logging

- INFO level: User-triggered actions (search, radio generation, play/queue)
- ERROR level: Failures and exceptions
- DEBUG level: Detailed flow (API calls, stream resolution progress)
- Format: Use existing logging setup in daemon

### Testing Strategy

- Unit tests for all new functions
- Integration tests for end-to-end workflows
- Mock external APIs (YouTube Music, MPD) in unit tests
- Use real APIs in integration tests (optional, can be manual)
- Minimum 70% code coverage

### Configuration

- All new config in `~/.config/ytmpd/config.yaml`
- Provide sensible defaults
- Validate all config values
- Document all options in examples/config.yaml

---

## Integration Points

### Radio Feature ↔ YouTube Music API

- Uses existing `YTMusicClient.get_watch_playlist(videoId, radio=True)`
- Radio playlist generation is YouTube Music's algorithm
- No custom logic needed - just pass the video ID

### Search Feature ↔ YouTube Music API

- Uses existing `YTMusicClient.search(query, filter="songs")`
- Filter by "songs" gives best results (vs "videos" or "albums")
- Limit to 10 results for usability

### Both Features ↔ Stream Resolver

- Reuse existing `StreamResolver.resolve()` and `resolve_batch()`
- Handles yt-dlp integration and caching
- Retries and error handling already implemented

### Both Features ↔ MPD Client

- Reuse existing `MPDClient` for all MPD operations
- May need to add helper methods: clear(), add(), play()
- ICY proxy handles metadata injection automatically

---

## Data Schemas

### Socket Command Format

```
radio [video_id]       # video_id optional, uses current track if omitted
search <query>         # query is freeform text
play <video_id>        # play track immediately
queue <video_id>       # add to queue
```

### Socket Response Format

```json
{
  "success": true|false,
  "message": "Human-readable message",
  "error": "Error message if success=false",
  "results": [...],  // For search command
  "count": 10,       // For search command
  "tracks": 25,      // For radio command
  "playlist": "YT: Radio"  // For radio command
}
```

### Search Result Format

```json
{
  "number": 1,
  "video_id": "dQw4w9WgXcQ",
  "title": "Never Gonna Give You Up",
  "artist": "Rick Astley",
  "duration": "3:32"
}
```

---

## Glossary

**Radio**: YouTube Music's algorithm for generating a playlist based on a seed track
**video_id**: YouTube's 11-character unique identifier for videos
**Proxy URL**: Format used by ytmpd ICY proxy: `http://localhost:PORT/proxy/VIDEO_ID`
**MPD**: Music Player Daemon
**ncmpcpp**: Terminal-based MPD client
**ytmpctl**: CLI tool for controlling ytmpd daemon
**Socket protocol**: Unix socket communication between ytmpctl and ytmpd daemon

---

## Future Enhancements

(Not in current scope but potentially valuable later)

- [ ] Search filters (genre, year, album)
- [ ] Save radio playlists with custom names
- [ ] Search history and favorites
- [ ] Batch operations (add multiple tracks at once)
- [ ] Fuzzy search / autocomplete
- [ ] Radio from playlist (not just single track)
- [ ] GUI interface for search

---

## References

- [ytmusicapi Documentation](https://ytmusicapi.readthedocs.io/)
- [python-mpd2 Documentation](https://python-mpd2.readthedocs.io/)
- [MPD Protocol Reference](https://mpd.readthedocs.io/en/latest/protocol.html)

---

**Instructions for Agents**:
1. **First**: Run `pwd` and verify you're in `/home/tunc/Sync/Programs/ytmpd`
2. Read ONLY your assigned phase section
3. Check the dependencies to understand what should already exist
4. Follow the detailed requirements exactly
5. Meet all completion criteria before marking phase complete
6. Create your summary in `summaries/PHASE_XX_SUMMARY.md`
7. Update `STATUS.md` when complete

**Remember**: All file paths in this plan are relative to `/home/tunc/Sync/Programs/ytmpd`

**Context Budget Note**: Each phase is designed to fit within ~30-70k tokens. If a phase exceeds this, note it in your summary and suggest splitting.
