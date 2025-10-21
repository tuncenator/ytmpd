# Changelog

All notable changes to ytmpd (YouTube Music MPD) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-10-17

### Added

#### Core Functionality
- YouTube Music integration via ytmusicapi with browser-based authentication
- Background daemon process for managing YouTube Music playback state
- Unix socket server for client-daemon communication using MPD-inspired protocol
- Player state management with queue, position tracking, and state persistence
- Command-line client (ytmpctl) for controlling playback
- i3blocks integration script (ytmpd-status) for status display

#### Playback Controls
- Play songs by search query
- Pause/resume playback
- Stop playback
- Skip to next song in queue
- Restart current song (previous command)
- Queue management (add songs, view queue)

#### Authentication
- Browser-based authentication setup via request headers
- Secure credential storage in ~/.config/ytmpd/browser.json
- Long-lived authentication (~2 years before renewal needed)

#### Configuration
- YAML-based configuration file (~/.config/ytmpd/config.yaml)
- Configurable socket path, state file, log level, and log file
- XDG-compliant configuration directory structure

#### State Management
- Persistent state across daemon restarts
- Automatic state file saving
- Graceful handling of corrupted state files
- Position tracking with auto-advance to next song

#### i3 Integration
- Status script for i3blocks with color-coded playback states
- Example i3 configuration for keybindings
- Example i3blocks configuration
- Configurable output format and truncation

#### Error Handling
- Comprehensive error handling with retry logic for network failures
- Custom exception hierarchy for different error types
- Graceful degradation when daemon is not running
- Clear error messages with helpful suggestions

#### Edge Cases
- Automatic removal of stale socket files
- Handling of empty queue
- Network disconnection recovery with retry logic
- Corrupted state file recovery

#### Testing
- Comprehensive test suite with 109 tests
- 85% code coverage across all modules
- Unit tests for all core modules
- Integration tests for daemon and client interaction
- Mocked YouTube Music API for reliable testing

#### Documentation
- Comprehensive README with setup and usage instructions
- Troubleshooting guide for common issues
- Architecture overview and component descriptions
- Example configuration files
- Installation script with interactive setup
- systemd service file for automatic daemon startup

#### Development Tools
- Type checking with mypy
- Linting and formatting with ruff
- Automated test suite with pytest
- Code coverage reporting
- Development environment setup with uv

### Technical Details

- **Language**: Python 3.11+
- **Environment Management**: uv
- **Key Dependencies**: ytmusicapi, pyyaml
- **IPC**: Unix domain sockets
- **Protocol**: MPD-inspired text protocol
- **State Persistence**: JSON-based state files
- **Async Support**: asyncio for concurrent operations

### Installation

- Automated installation script (install.sh) with:
  - uv installation (if needed)
  - Virtual environment creation
  - Dependency installation
  - Interactive authentication setup
  - Optional systemd service installation
  - Optional PATH configuration

### Known Limitations

- No volume control (handled by YouTube Music web player)
- No seek within track (planned for future release)
- No shuffle/repeat modes (planned for future release)
- No like/dislike functionality (planned for future release)
- Previous command only restarts current song (no history)

### Security

- User-only socket permissions
- Secure credential storage in user config directory
- No network exposure (local Unix socket only)
- systemd service with security hardening options

### Contributors

Initial release developed through a phased development workflow with comprehensive
planning, implementation, testing, and documentation across 9 development phases.

---

## [Unreleased]

### Added

#### Track Rating Features
- Bidirectional like/dislike support for YouTube Music tracks
  - `ytmpctl like` - Toggle like status for currently playing track
  - `ytmpctl dislike` - Toggle dislike status for currently playing track
  - Immediate sync trigger after liking songs to update "Liked Songs" playlist
  - Smart toggle semantics: pressing same command twice reverts action
  - Support for all rating state transitions (neutral ↔ liked, neutral ↔ disliked, liked ↔ disliked)
  - Color-coded user feedback (green ✓ for likes, red ✗ for dislikes)
  - Comprehensive error handling for all failure scenarios
- Extended `YTMusicClient` with rating methods:
  - `get_track_rating(video_id)` - Query current rating state
  - `set_track_rating(video_id, rating)` - Set like/dislike/neutral rating
  - Rate limiting (100ms minimum between API calls) to prevent API abuse
  - Automatic retry with exponential backoff for transient failures
- New `ytmpd.rating` module with rating state machine:
  - `RatingManager` class for toggle logic and state transitions
  - `RatingState` enum (NEUTRAL, LIKED, DISLIKED)
  - `RatingAction` enum (LIKE, DISLIKE, INDIFFERENT)
  - Complete state transition logic with 6 possible transitions
- Integration tests for rating workflow (20 tests):
  - All state transition scenarios tested
  - Error handling validation (network, auth, MPD connection)
  - Sync trigger verification
  - End-to-end workflow validation

### Changed
- `ytmpctl help` updated to include like/dislike commands
- README.md expanded with like/dislike feature documentation and examples

### Technical
- Test coverage: 97% for rating.py, 35% for ytmusic.py rating methods
- All tests passing (65 total: 20 integration + 28 rating unit + 17 ytmusic_rating unit)
- Pre-commit hooks passing (ruff, ruff-format)
- Type hints and docstrings complete for all new code

### Planned Features

- Seek within track
- Shuffle and repeat modes
- Volume control integration
- Advanced playlist management
- History tracking
- Last.fm scrobbling
- MPRIS D-Bus interface
- Web UI for control

---

[1.0.0]: https://github.com/tuncenator/ytmpd/releases/tag/v1.0.0
