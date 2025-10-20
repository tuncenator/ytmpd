# ytmpd - Project Plan

**Feature/Initiative**: project-initiation
**Type**: New Project
**Created**: 2025-10-17
**Estimated Total Phases**: 9

---

## Project Overview

### Purpose

**ytmpd** (YouTube Music MPD) is an MPD/MPC-like daemon and client for YouTube Music. It enables controlling YouTube Music playback through command-line tools and i3 window manager hotkeys, with status display integration for i3blocks.

The project solves the problem of controlling YouTube Music in a keyboard-driven Linux workflow, similar to how MPD/MPC work for local music libraries.

### Scope

**In Scope**:
- Daemon process that manages YouTube Music playback state
- Command-line client (ytmpctl) for sending commands to daemon
- Unix socket-based communication (MPD-style)
- Core playback controls: play, pause, stop, next, previous
- Status querying: current song info, playback state, position/duration
- Basic queue management: play by search, view current queue
- i3blocks integration script for status display
- Authentication with YouTube Music via ytmusicapi
- Testing and documentation

**Out of Scope**:
- GUI interface
- Volume control (handled by YouTube Music web player)
- Advanced playlist management in YouTube Music itself
- Downloading or local playback
- Shuffle/repeat modes (deferred to v2)
- Like/dislike functionality (deferred to v2)
- Seek within track (deferred to v2)

### Success Criteria

- [ ] Daemon runs in background and manages YouTube Music connection
- [ ] Client can send commands and receive responses via Unix socket
- [ ] Can control playback through i3 hotkeys using ytmpctl
- [ ] Current song info displays correctly in i3blocks
- [ ] System works reliably with proper error handling
- [ ] Documentation enables users to set up and use the system

---

## Architecture Overview

### Key Components

1. **ytmpd daemon**: Background service that manages YouTube Music connection and playback state
2. **Socket server**: Unix socket listener that receives commands from clients
3. **Player state manager**: Tracks current song, queue, playback state, position
4. **YouTube Music wrapper**: Abstraction over ytmusicapi for search, playback control
5. **ytmpctl client**: Command-line client that communicates with daemon
6. **i3blocks script**: Status formatter for i3blocks display

### Data Flow

```
i3 hotkey → ytmpctl (client) → Unix socket → ytmpd daemon → ytmusicapi → YouTube Music

YouTube Music → ytmusicapi → ytmpd daemon → Unix socket → ytmpctl/i3blocks script → User
```

### Technology Stack

- **Language**: Python 3.11+
- **Environment Management**: uv
- **Key Libraries**:
  - ytmusicapi: YouTube Music API integration
  - asyncio: Async socket server and playback coordination
- **Testing**: pytest, pytest-asyncio
- **Type Checking**: mypy
- **Linting/Formatting**: ruff
- **IPC**: Unix domain sockets

---

## Phase Breakdown

> **Note for Agents**: Only read the section for your assigned phase. Reading all phases wastes context.

---

### Phase 1: Project Setup & Structure

**Objective**: Create the project foundation with proper Python packaging, directory structure, and configuration system.

**Estimated Context Budget**: ~25k tokens

#### Deliverables

1. Project directory structure
2. `pyproject.toml` with uv-compatible configuration
3. Basic configuration module for storing settings (socket path, auth, etc.)
4. Development environment setup documentation

#### Detailed Requirements

Create the following directory structure:
```
ytmpd/
├── ytmpd/              # Main package
│   ├── __init__.py
│   ├── config.py       # Configuration management
│   └── __main__.py     # Entry point for daemon
├── bin/
│   ├── ytmpctl         # Client executable
│   └── ytmpd-status    # i3blocks script
├── tests/
│   └── __init__.py
├── docs/
│   └── agent/          # Already exists
├── pyproject.toml      # Project metadata and dependencies
├── README.md           # Basic project overview
└── .gitignore
```

**Configuration System (`ytmpd/config.py`)**:
- Load config from `~/.config/ytmpd/config.yaml` (create if missing)
- Default config values:
  - `socket_path: ~/.config/ytmpd/socket`
  - `state_file: ~/.config/ytmpd/state.json`
  - `log_level: INFO`
  - `log_file: ~/.config/ytmpd/ytmpd.log`
- Function: `load_config() -> dict`
- Function: `get_config_dir() -> Path`
- Create config directory if it doesn't exist

**pyproject.toml**:
- Project metadata (name, version, description, author)
- Dependencies: ytmusicapi, pyyaml
- Dev dependencies: pytest, pytest-asyncio, mypy, ruff
- Entry points for `ytmpd` command
- Requires Python >=3.11

#### Dependencies

**Requires**: None (first phase)

**Enables**: All other phases

#### Completion Criteria

- [ ] Directory structure created
- [ ] pyproject.toml configured for uv
- [ ] Config module loads/creates config file
- [ ] Config directory created on first run
- [ ] Basic README exists
- [ ] .gitignore includes Python artifacts, .venv, __pycache__, etc.
- [ ] Can run `uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"`

#### Testing Requirements

- Unit test for config loading
- Test config directory creation
- Test default config values

#### Notes

- Use uv for all dependency management
- Keep config simple - YAML for human readability
- Ensure XDG compliance (~/.config/ytmpd/)

---

### Phase 2: YouTube Music Integration

**Objective**: Implement a wrapper around ytmusicapi that handles authentication and provides clean interfaces for search, playback, and song info retrieval.

**Estimated Context Budget**: ~40k tokens

#### Deliverables

1. `ytmpd/ytmusic.py` - YouTube Music API wrapper
2. Authentication flow implementation
3. Functions for search, get song info, playback control
4. Error handling for API failures

#### Detailed Requirements

**Create `ytmpd/ytmusic.py`** with class `YTMusicClient`:

**Authentication**:
- `setup_oauth() -> None`: Interactive OAuth setup (stores credentials in config dir)
- `__init__(auth_file: Path)`: Initialize with auth credentials
- Handle expired tokens and re-authentication

**Core Methods**:
- `search(query: str, limit: int = 10) -> list[dict]`: Search for songs
  - Return: list of dicts with keys: `video_id`, `title`, `artist`, `duration`
- `get_song_info(video_id: str) -> dict`: Get detailed song information
  - Return: dict with `video_id`, `title`, `artist`, `album`, `duration`, `thumbnail_url`
- `get_streaming_url(video_id: str) -> str`: Get playback URL (if needed by ytmusicapi)

**Error Handling**:
- Custom exceptions: `YTMusicAuthError`, `YTMusicAPIError`, `YTMusicNotFoundError`
- Retry logic for transient failures
- Proper logging of API errors

**Notes**:
- ytmusicapi handles most of the heavy lifting
- Store OAuth credentials in `~/.config/ytmpd/oauth.json`
- Make authentication user-friendly (provide clear setup instructions)

#### Dependencies

**Requires**: Phase 1 (config system)

**Enables**: Phase 3, 5

#### Completion Criteria

- [ ] YTMusicClient class implemented
- [ ] OAuth authentication working
- [ ] Search functionality works
- [ ] Song info retrieval works
- [ ] Proper error handling and logging
- [ ] Authentication credentials stored securely

#### Testing Requirements

- Unit tests with mocked ytmusicapi
- Test authentication flow (mock OAuth)
- Test search parsing
- Test error handling

#### Notes

- Reference ytmusicapi docs: https://ytmusicapi.readthedocs.io/
- OAuth setup is one-time, should be simple for users
- Consider rate limiting if needed

---

### Phase 3: Player State Management

**Objective**: Implement the core player state machine that tracks playback state, current song, queue, and position.

**Estimated Context Budget**: ~35k tokens

#### Deliverables

1. `ytmpd/player.py` - Player state manager
2. State persistence to disk
3. Queue management
4. Position tracking

#### Detailed Requirements

**Create `ytmpd/player.py`** with class `Player`:

**State Management**:
- States: `STOPPED`, `PLAYING`, `PAUSED`
- `state: str` - current playback state
- `current_song: dict | None` - current song info (video_id, title, artist, duration)
- `position: int` - current position in seconds
- `queue: list[dict]` - upcoming songs

**Core Methods**:
- `play(song: dict) -> None`: Start playing a song
- `pause() -> None`: Pause playback
- `resume() -> None`: Resume playback
- `stop() -> None`: Stop playback
- `next() -> None`: Skip to next song in queue
- `previous() -> None`: Go to previous song
- `add_to_queue(songs: list[dict]) -> None`: Add songs to queue
- `get_status() -> dict`: Return current state (state, song, position, queue length)

**State Persistence**:
- `save_state() -> None`: Serialize state to JSON file (~/.config/ytmpd/state.json)
- `load_state() -> None`: Restore state from disk on daemon start
- Auto-save on state changes

**Position Tracking**:
- Background task to increment position while playing
- Reset position on song change
- Persist position to state file

#### Dependencies

**Requires**: Phase 1 (config)

**Enables**: Phase 5 (daemon core)

#### Completion Criteria

- [ ] State machine implemented correctly
- [ ] Queue management works
- [ ] Position tracking accurate
- [ ] State persists across daemon restarts
- [ ] All player methods work as expected
- [ ] Thread-safe / async-safe if needed

#### Testing Requirements

- Unit tests for all state transitions
- Test queue management (add, next, previous)
- Test state persistence (save/load)
- Test position tracking

#### Notes

- Player doesn't directly control YouTube Music playback (that's daemon's job)
- This is the "source of truth" for playback state
- Keep state file small and efficient

---

### Phase 4: Unix Socket Server

**Objective**: Implement a Unix socket server that listens for client commands and returns responses in an MPD-like text protocol.

**Estimated Context Budget**: ~40k tokens

#### Deliverables

1. `ytmpd/server.py` - Socket server implementation
2. Command protocol parser
3. Response formatter
4. Connection handling

#### Detailed Requirements

**Create `ytmpd/server.py`** with class `SocketServer`:

**Socket Setup**:
- Listen on Unix socket (path from config)
- Handle multiple concurrent client connections
- Clean up socket file on shutdown
- Proper file permissions on socket

**Protocol Design (MPD-inspired)**:
```
Client → Server:
  play <video_id>
  pause
  resume
  stop
  next
  previous
  status
  search <query>
  queue

Server → Client:
  OK
  # or on error:
  ERR: <error message>
  # for status:
  state: playing
  title: Song Title
  artist: Artist Name
  position: 45
  duration: 180
  queue_length: 5
  OK
```

**Command Parser**:
- `parse_command(line: str) -> tuple[str, list[str]]`: Parse command and args
- Support for multi-line responses (status, search results, queue)

**Core Methods**:
- `__init__(socket_path: Path, command_handler: Callable)`
- `start() -> None`: Start listening (async)
- `stop() -> None`: Clean shutdown
- `handle_client(reader, writer) -> None`: Handle single client connection

**Command Handler Interface**:
- Server receives callback function that processes commands
- Handler signature: `async def handle_command(cmd: str, args: list[str]) -> str`

#### Dependencies

**Requires**: Phase 1 (config for socket path)

**Enables**: Phase 5 (daemon integration)

#### Completion Criteria

- [ ] Socket server starts and listens correctly
- [ ] Can accept multiple client connections
- [ ] Command parsing works
- [ ] Response formatting matches protocol
- [ ] Socket cleanup on shutdown
- [ ] Proper error handling for malformed commands

#### Testing Requirements

- Unit tests for command parsing
- Integration test: connect client, send commands, verify responses
- Test multiple concurrent connections
- Test socket cleanup

#### Notes

- Use asyncio for async socket handling
- Keep protocol simple and text-based
- Ensure socket permissions allow user access only

---

### Phase 5: Daemon Core

**Objective**: Implement the main daemon process that integrates the player, YouTube Music client, and socket server into a cohesive background service.

**Estimated Context Budget**: ~45k tokens

#### Deliverables

1. `ytmpd/daemon.py` - Main daemon implementation
2. Integration of all components
3. Daemon lifecycle management (start, stop, status)
4. Background playback coordination

#### Detailed Requirements

**Create `ytmpd/daemon.py`** with class `YTMPDDaemon`:

**Initialization**:
- Load configuration
- Initialize YTMusicClient (Phase 2)
- Initialize Player (Phase 3)
- Initialize SocketServer (Phase 4)
- Load persisted state

**Command Handling**:
Implement `handle_command(cmd: str, args: list[str]) -> str` for socket server:
- `play <video_id>`: Update player state, coordinate playback
- `pause`: Pause player
- `resume`: Resume player
- `stop`: Stop player
- `next`: Skip to next song
- `previous`: Previous song
- `status`: Return player status
- `search <query>`: Use YTMusicClient to search, return results
- `queue`: Return current queue

**Background Tasks**:
- Position tracking (update player position every second while playing)
- State persistence (save state every 10 seconds if changed)
- Handle playback completion (auto-advance to next song)

**Lifecycle**:
- `start() -> None`: Start all components, run event loop
- `stop() -> None`: Graceful shutdown, save state
- Signal handling (SIGTERM, SIGINT) for clean shutdown

**Entry Point (`ytmpd/__main__.py`)**:
```python
if __name__ == "__main__":
    daemon = YTMPDDaemon()
    daemon.start()
```

#### Dependencies

**Requires**: Phase 2 (YTMusic), Phase 3 (Player), Phase 4 (Server)

**Enables**: Phase 6 (client can now connect)

#### Completion Criteria

- [ ] Daemon starts successfully
- [ ] All components integrated
- [ ] Commands work end-to-end
- [ ] Background tasks running correctly
- [ ] Graceful shutdown works
- [ ] State persists across restarts
- [ ] Daemon can be run with `python -m ytmpd`

#### Testing Requirements

- Integration tests for full command flow
- Test daemon start/stop
- Test state persistence
- Test auto-advance to next song
- Manual testing with real YouTube Music connection

#### Notes

- This is the heart of the system - integration is key
- Use asyncio for coordinating background tasks
- Ensure clean shutdown to avoid socket file lingering

---

### Phase 6: Client CLI (ytmpctl)

**Objective**: Implement the command-line client that users interact with to control the daemon.

**Estimated Context Budget**: ~35k tokens

#### Deliverables

1. `bin/ytmpctl` - Client executable script
2. Command implementations
3. Output formatting
4. Error handling

#### Detailed Requirements

**Create `bin/ytmpctl`** (Python script with shebang):

**Commands**:
- `ytmpctl play <query>`: Search for song and play first result
- `ytmpctl pause`: Pause playback
- `ytmpctl resume`: Resume playback
- `ytmpctl stop`: Stop playback
- `ytmpctl next`: Next song
- `ytmpctl prev`: Previous song
- `ytmpctl status`: Display current status (human-readable)
- `ytmpctl search <query>`: Search and display results
- `ytmpctl queue`: Display current queue

**Socket Communication**:
- Connect to Unix socket (from config)
- Send command
- Receive and parse response
- Handle `OK` / `ERR:` responses

**Output Formatting**:
- `status`: Format like MPD status (key: value format)
- `search`: Numbered list of results
- `queue`: Numbered list of queued songs
- Errors: Print to stderr with helpful message

**Error Handling**:
- Daemon not running: "ytmpd daemon is not running"
- Connection failed: "Failed to connect to daemon"
- Command error: Display error from daemon

**Usage Help**:
```
ytmpctl - Control ytmpd daemon

Usage:
  ytmpctl play <query>     Search and play a song
  ytmpctl pause            Pause playback
  ytmpctl resume           Resume playback
  ytmpctl stop             Stop playback
  ytmpctl next             Next song
  ytmpctl prev             Previous song
  ytmpctl status           Show current status
  ytmpctl search <query>   Search for songs
  ytmpctl queue            Show queue
```

#### Dependencies

**Requires**: Phase 5 (daemon running)

**Enables**: Phase 7 (i3 integration uses ytmpctl)

#### Completion Criteria

- [ ] All commands implemented
- [ ] Socket communication works
- [ ] Output formatting is clean and readable
- [ ] Error messages are helpful
- [ ] Help text displays correctly
- [ ] Executable bit set on script

#### Testing Requirements

- Integration tests with running daemon
- Test all commands
- Test error cases (daemon not running)
- Manual testing from command line

#### Notes

- Keep output simple and parseable
- Consider colors for better UX (optional)
- Make it feel like using `mpc`

---

### Phase 7: i3blocks Integration

**Objective**: Create a status script for i3blocks that displays current playback information.

**Estimated Context Budget**: ~20k tokens

#### Deliverables

1. `bin/ytmpd-status` - i3blocks script
2. Formatted output for i3blocks
3. Error handling for daemon not running
4. Configuration options

#### Detailed Requirements

**Create `bin/ytmpd-status`** (bash or Python script):

**Functionality**:
- Query daemon status using ytmpctl or direct socket connection
- Format output for i3blocks display
- Handle daemon not running gracefully

**Output Format**:
```
# When playing:
▶ Artist - Song Title [2:34/3:45]

# When paused:
⏸ Artist - Song Title [2:34/3:45]

# When stopped or daemon not running:
⏹ ytmpd

# Truncate long titles to fit:
▶ Very Long Artist Name... [2:34/3:45]
```

**Configuration** (via environment variables or config file):
- `YTMPD_STATUS_FORMAT`: Format string (default: "▶ {artist} - {title} [{position}/{duration}]")
- `YTMPD_STATUS_MAX_LENGTH`: Max length before truncation (default: 50)

**Color Coding** (for i3blocks):
- Playing: green
- Paused: yellow
- Stopped: gray

**Example i3blocks config**:
```ini
[ytmpd]
command=~/path/to/ytmpd-status
interval=5
```

#### Dependencies

**Requires**: Phase 6 (ytmpctl)

**Enables**: Full user workflow

#### Completion Criteria

- [ ] Script outputs correctly formatted status
- [ ] Works when daemon is running
- [ ] Handles daemon not running gracefully
- [ ] Truncation works for long titles
- [ ] Colors work in i3blocks
- [ ] Documentation includes i3blocks config example

#### Testing Requirements

- Test with daemon in various states (playing, paused, stopped)
- Test with daemon not running
- Test truncation
- Manual testing in i3blocks

#### Notes

- Keep it lightweight - this runs every few seconds
- Cache socket connection if possible
- Provide example in README for i3 config

---

### Phase 8: Testing & Documentation

**Objective**: Comprehensive testing suite and user-facing documentation.

**Estimated Context Budget**: ~35k tokens

#### Deliverables

1. Complete test suite with good coverage
2. README with setup and usage instructions
3. Example configuration files
4. Troubleshooting guide

#### Detailed Requirements

**Testing**:
- Achieve >80% code coverage
- Unit tests for all modules
- Integration tests for daemon + client
- Mock ytmusicapi in tests
- Test fixtures for common scenarios

**README.md**:
Sections:
1. Introduction (what is ytmpd)
2. Features
3. Requirements (Python 3.11+, uv, YouTube Music account)
4. Installation
   - Clone repo
   - `uv venv && source .venv/bin/activate`
   - `uv pip install -e .`
   - Setup OAuth: `python -m ytmpd.ytmusic setup-oauth`
5. Usage
   - Start daemon: `python -m ytmpd &`
   - Control with ytmpctl
   - Examples of common commands
6. i3 Integration
   - i3 config examples (hotkeys)
   - i3blocks config example
7. Configuration (config file location and options)
8. Troubleshooting

**Example Files**:
- `examples/i3-config`: Example i3 keybindings
- `examples/i3blocks-config`: Example i3blocks block
- `examples/config.yaml`: Example ytmpd config

**Troubleshooting Guide**:
- Daemon won't start
- Authentication issues
- Socket connection errors
- Playback not working

#### Dependencies

**Requires**: All previous phases

**Enables**: User adoption

#### Completion Criteria

- [ ] Test coverage >80%
- [ ] All tests passing
- [ ] README complete and accurate
- [ ] Example files provided
- [ ] Documentation clear and helpful

#### Testing Requirements

- Run full test suite: `pytest --cov=ytmpd tests/`
- Verify all integration tests pass
- Manual testing of documented examples

#### Notes

- Good documentation is critical for adoption
- Examples should be copy-pasteable
- Include screenshots if helpful (optional)

---

### Phase 9: Polish & Packaging

**Objective**: Final polish, installation script, systemd service, and release preparation.

**Estimated Context Budget**: ~25k tokens

#### Deliverables

1. Installation script
2. systemd service file
3. Improved error messages
4. Edge case handling
5. Release preparation

#### Detailed Requirements

**Installation Script (`install.sh`)**:
```bash
#!/bin/bash
# Install uv if needed
# Create venv
# Install ytmpd
# Setup OAuth interactively
# Install systemd service (optional)
# Add to PATH
```

**systemd Service (`ytmpd.service`)**:
```ini
[Unit]
Description=YouTube Music MPD daemon
After=network.target

[Service]
Type=simple
ExecStart=/path/to/.venv/bin/python -m ytmpd
Restart=on-failure
User=%u

[Install]
WantedBy=default.target
```

**Error Message Improvements**:
- Review all error messages for clarity
- Add suggestions for common errors
- Improve logging output

**Edge Cases**:
- Handle network disconnection gracefully
- Handle YouTube Music API changes
- Handle corrupted state file
- Handle socket file already exists
- Handle queue empty on 'next'

**Release Preparation**:
- Version number in pyproject.toml
- CHANGELOG.md
- LICENSE file
- GitHub release notes template

#### Dependencies

**Requires**: Phase 8 (documentation)

**Enables**: v1.0 release

#### Completion Criteria

- [ ] Install script works on fresh system
- [ ] systemd service starts daemon correctly
- [ ] All error messages reviewed and improved
- [ ] Edge cases handled gracefully
- [ ] Version number set
- [ ] CHANGELOG created
- [ ] Ready for release

#### Testing Requirements

- Test install.sh on clean environment
- Test systemd service
- Test all edge cases
- Final manual testing of complete workflow

#### Notes

- This is the final polish - make it production-ready
- Consider user experience in all aspects
- Test on a fresh system if possible

---

## Phase Dependencies Graph

```
Phase 1 (Setup)
    ↓
    ├─→ Phase 2 (YTMusic)
    │       ↓
    ├─→ Phase 3 (Player)
    │       ↓
    └─→ Phase 4 (Server)
            ↓
        Phase 5 (Daemon) ←─ (integrates 2, 3, 4)
            ↓
        Phase 6 (Client)
            ↓
        Phase 7 (i3blocks)
            ↓
        Phase 8 (Testing & Docs)
            ↓
        Phase 9 (Polish & Packaging)
```

---

## Cross-Cutting Concerns

### Code Style

- Follow PEP 8
- Use type hints for all function signatures
- Maximum line length: 100 characters
- Use docstrings for all public functions (Google style)
- Format with ruff: `ruff format ytmpd/`
- Lint with ruff: `ruff check ytmpd/`

### Error Handling

- Use custom exceptions defined in `ytmpd/exceptions.py`
- Always log errors before raising
- Provide helpful error messages with context
- Handle network errors gracefully (retry, timeout)

### Logging

- Use Python's `logging` module
- Log level configurable via config (default: INFO)
- Format: `[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s`
- Log to file: `~/.config/ytmpd/ytmpd.log`
- Also log to console when running in foreground

### Configuration

- All config in `~/.config/ytmpd/config.yaml`
- Loaded via `ytmpd/config.py`
- Create default config if missing
- Validate config on load

### Testing Strategy

- Unit tests for all modules
- Integration tests for daemon + client
- Mock external dependencies (ytmusicapi)
- Minimum 80% code coverage
- Use pytest with fixtures for common setups
- Test both success and error paths

---

## Integration Points

### Player ↔ Daemon
- Daemon calls player methods to update state
- Daemon reads player state for status queries
- Player persists state to disk, daemon loads on start

### YTMusic ↔ Daemon
- Daemon uses YTMusic for search
- Daemon uses YTMusic for song info
- Daemon handles YTMusic errors and retries

### Server ↔ Daemon
- Server receives commands, passes to daemon handler
- Daemon handler returns formatted responses
- Server sends responses back to client

### Client ↔ Daemon
- Client connects to Unix socket
- Client sends text commands
- Client parses responses and displays to user

---

## Data Schemas

### Song Info Dictionary
```python
{
    "video_id": str,        # YouTube video ID
    "title": str,           # Song title
    "artist": str,          # Artist name
    "album": str,           # Album name (optional)
    "duration": int,        # Duration in seconds
    "thumbnail_url": str    # Thumbnail URL (optional)
}
```

### Player State File
```json
{
    "state": "PLAYING|PAUSED|STOPPED",
    "current_song": { /* song info dict or null */ },
    "position": 123,
    "queue": [ /* array of song info dicts */ ]
}
```

### Config File
```yaml
socket_path: ~/.config/ytmpd/socket
state_file: ~/.config/ytmpd/state.json
log_level: INFO
log_file: ~/.config/ytmpd/ytmpd.log
```

---

## Glossary

**Daemon**: Background service that runs continuously
**ytmpctl**: Command-line client for controlling ytmpd
**ytmusicapi**: Python library for YouTube Music API
**Unix socket**: IPC mechanism for local process communication
**MPD**: Music Player Daemon (inspiration for this project)
**i3**: Tiling window manager for Linux
**i3blocks**: Status bar for i3

---

## Future Enhancements

- [ ] Volume control integration
- [ ] Shuffle and repeat modes
- [ ] Like/dislike tracks
- [ ] Seek within track
- [ ] Advanced playlist management
- [ ] Web UI for control
- [ ] Multiple queue support
- [ ] History tracking
- [ ] Scrobbling to Last.fm
- [ ] MPRIS D-Bus interface

---

## References

- ytmusicapi docs: https://ytmusicapi.readthedocs.io/
- MPD protocol: https://www.musicpd.org/doc/html/protocol.html
- i3 documentation: https://i3wm.org/docs/
- Python asyncio: https://docs.python.org/3/library/asyncio.html

---

**Instructions for Agents**:
1. Read ONLY your assigned phase section
2. Check the dependencies to understand what should already exist
3. Follow the detailed requirements exactly
4. Meet all completion criteria before marking phase complete
5. Create your summary in `summaries/PHASE_XX_SUMMARY.md`
6. Update `STATUS.md` when complete

**Context Budget Note**: Each phase is designed to fit within ~120k tokens total (reading previous summaries + implementation + output + thinking). If a phase exceeds this, note it in your summary and suggest splitting.
