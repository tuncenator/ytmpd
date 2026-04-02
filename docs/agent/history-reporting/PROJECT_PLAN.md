# ytmpd - History Reporting - Project Plan

**Feature/Initiative**: history-reporting
**Type**: New Feature
**Created**: 2026-04-02
**Estimated Total Phases**: 2

---

## Project Location

**IMPORTANT: All paths in this document are relative to the project root.**

- **Project Root**: `/home/tunc/Sync/Programs/ytmpd`
- **Verify with**: `pwd` -- should output `/home/tunc/Sync/Programs/ytmpd`

When you see a path like `ytmpd/history_reporter.py`, it means `/home/tunc/Sync/Programs/ytmpd/ytmpd/history_reporter.py`

---

## Project Overview

### Purpose

ytmpd is currently a read-only bridge -- it fetches YouTube Music playlists and resolves stream URLs for MPD playback, but never reports what the user actually listens to. This means YouTube Music's recommendation engine (radio, Discover Mix, Your Mix) gradually becomes stale because it loses the feedback loop.

This feature adds playback history reporting: when a track finishes playing through MPD, ytmpd reports it back to YouTube Music via `ytmusicapi.add_history_item()`, keeping the recommendation engine fed with listening data.

### Scope

**In Scope**:
- MPD idle listener detecting track changes via `idle('player')` subsystem
- Video ID lookup from TrackStore when a track finishes
- Reporting plays to YouTube Music via `get_song()` + `add_history_item()`
- Opt-in configuration (`history_reporting.enabled`, default false)
- Minimum play duration threshold to distinguish skips from listens (`min_play_seconds`, default 30)
- Unit tests for all new code

**Out of Scope**:
- Offline queue / retry persistence across daemon restarts
- Reporting partial plays or play duration/progress
- Scrobbling to third-party services (Last.fm, ListenBrainz)
- UI/CLI commands for history reporting status

### Success Criteria

- [ ] When a track plays for >= min_play_seconds in MPD, it appears in YouTube Music history
- [ ] Skipped tracks (< min_play_seconds) are NOT reported
- [ ] Feature is opt-in and disabled by default
- [ ] Daemon shutdown is clean (no hung threads, no lost reports)
- [ ] All tests pass, mypy/ruff clean

---

## Architecture Overview

### Key Components

1. **HistoryReporter** (`ytmpd/history_reporter.py`): New module with its own MPD connection that listens for player state changes, tracks playback duration, and reports completed plays to YouTube Music.
2. **YTMusicClient additions** (`ytmpd/ytmusic.py`): Two new wrapper methods -- `get_song()` returning the raw song dict, and `report_history()` calling `add_history_item()`.
3. **Config additions** (`ytmpd/config.py`): New `history_reporting` section with `enabled` and `min_play_seconds` fields.
4. **Daemon integration** (`ytmpd/daemon.py`): New background thread running the history reporter, with proper lifecycle management.

### Data Flow

```
MPD plays track --> idle('player') fires --> HistoryReporter detects track change
  --> extract video_id from previous track's proxy URL
  --> check if play duration >= min_play_seconds
  --> if yes: YTMusicClient.get_song(video_id) --> YTMusicClient.report_history(song)
  --> YouTube Music receives playback event (HTTP 204)
  --> track appears in user's YouTube Music history
```

### Technology Stack

- **Language**: Python 3.11+
- **Key Libraries**: ytmusicapi (add_history_item), python-mpd2 (idle listener), sqlite3 (TrackStore)
- **Testing**: pytest
- **Linting**: ruff, mypy (strict)

---

## Phase Breakdown

> **Note for Agents**: Only read the section for your assigned phase. Reading all phases wastes context.

---

### Phase 1: Core History Reporter Module

**Objective**: Create the `HistoryReporter` class and add YouTube Music history reporting methods to `YTMusicClient`. This phase builds the complete, self-contained module that can detect track changes, enforce minimum play duration, and report plays -- ready to be wired into the daemon in Phase 2.

**Estimated Context Budget**: ~60k tokens

#### Deliverables

1. `ytmpd/history_reporter.py` -- New module with `HistoryReporter` class
2. Two new methods in `ytmpd/ytmusic.py` -- `get_song()` and `report_history()`
3. `tests/test_history_reporter.py` -- Unit tests for HistoryReporter
4. `tests/test_ytmusic_history.py` -- Unit tests for new YTMusicClient methods

#### Detailed Requirements

**1. YTMusicClient additions (`ytmpd/ytmusic.py`):**

Add two new public methods to the `YTMusicClient` class:

```python
def get_song(self, video_id: str) -> dict[str, Any]:
    """Fetch full song metadata from YouTube Music.

    Returns the raw response from ytmusicapi.get_song(), which contains
    the playbackTracking URLs needed by add_history_item().

    Raises:
        YTMusicAuthError: If not authenticated.
        YTMusicNotFoundError: If video_id doesn't exist.
        YTMusicAPIError: On other API failures.
    """
```

```python
def report_history(self, song: dict[str, Any]) -> bool:
    """Report a song as played to YouTube Music history.

    Takes the dict returned by get_song(). Calls ytmusicapi.add_history_item(song).
    Returns True on success (HTTP 204), False on failure.

    Does NOT raise on failure -- history reporting is best-effort.
    Logs warnings on failure but does not propagate exceptions.
    """
```

Both methods should use the existing `_rate_limit()` and `_retry_on_failure()` patterns. `report_history()` should catch all exceptions and return False (logging the error) rather than raising, since history reporting should never crash the caller.

**2. HistoryReporter class (`ytmpd/history_reporter.py`):**

```python
class HistoryReporter:
    def __init__(
        self,
        mpd_socket_path: str,
        ytmusic: YTMusicClient,
        track_store: TrackStore,
        proxy_config: dict[str, Any],
        min_play_seconds: int = 30,
    ) -> None:
```

The class needs its own `MPDClient` connection (separate from the daemon's) because `idle()` blocks the connection.

**Core logic -- the idle loop:**

```python
def run(self, shutdown_event: threading.Event) -> None:
    """Main loop. Blocks until shutdown_event is set."""
```

The loop should:
1. Connect its own MPDClient to MPD
2. Call `self._mpd._client.idle('player')` to block until a player event
3. On wake, get current MPD status and current song
4. Compare with previous state to detect: new track started, track stopped/finished
5. If a previous track was playing and enough time has elapsed (>= min_play_seconds):
   - Extract `video_id` from the previous track's URL (proxy URL format: `/proxy/{video_id}`)
   - Call `ytmusic.get_song(video_id)` then `ytmusic.report_history(song)`
   - Log success/failure
6. Update tracking state (current track URL, playback start time)
7. On `shutdown_event`: break loop, disconnect MPD

**Video ID extraction:**

The proxy URL format is `http://host:port/proxy/{video_id}` where video_id matches `[a-zA-Z0-9_-]{11}`. Extract video_id by parsing the URL path -- the last path segment after `/proxy/`. Use a simple approach:

```python
def _extract_video_id(self, url: str) -> str | None:
    """Extract video_id from proxy URL like http://localhost:8080/proxy/dQw4w9WgXcQ"""
```

Note: The daemon already has `_extract_video_id_from_url()` in daemon.py (lines 787-805) -- look at that implementation for reference, but implement your own in HistoryReporter to keep the module self-contained.

**Playback timing:**

Track when each song starts playing:
- `_current_track_url: str | None` -- URL of currently playing track
- `_current_track_start: float | None` -- `time.monotonic()` when track started
- When a track change is detected, calculate `elapsed = time.monotonic() - _current_track_start`
- Only report if `elapsed >= min_play_seconds`

**State transitions to handle:**
- `play -> play` (different track): Previous track finished/skipped, new one started. Report previous if duration met.
- `play -> stop/pause`: Track stopped or paused. If stopped, report previous if duration met. If paused, do NOT report yet (track may resume).
- `pause -> play` (same track): Track resumed. Do NOT reset start time -- accumulate total play time.
- `pause -> play` (different track): Previous was abandoned during pause. Report if duration met. Start tracking new.
- `stop -> play`: New track started from stopped state. Start tracking.

Handle pause correctly: maintain a `_pause_start: float | None` timestamp. When paused, record when. When resumed (same track), subtract pause duration from elapsed time. This way only actual play time counts toward the threshold.

**Error handling:**
- MPD connection lost: Log error, wait briefly (use `shutdown_event.wait(timeout=5)`), attempt reconnect, continue loop
- YTMusic API failure: Log warning, skip reporting, continue (best-effort)
- Auth failure: Log error, skip reporting (the auto-auth loop will handle token refresh)
- Unexpected exceptions in loop: Log with traceback, continue loop (don't crash thread)

**3. Unit tests (`tests/test_history_reporter.py`):**

Test the following scenarios using mocks for MPDClient, YTMusicClient, and TrackStore:

- Track plays for >= min_play_seconds --> reported to YouTube Music
- Track skipped (< min_play_seconds) --> NOT reported
- Track paused then resumed (same track) --> pause time excluded from duration
- Track paused then different track plays --> previous reported if duration met
- Playback stops --> previous track reported if duration met
- Video ID extraction from proxy URLs (valid, invalid, non-proxy URLs)
- MPD connection failure --> reconnects and continues
- YTMusic API failure --> logs warning, continues without crashing
- Shutdown event --> loop exits cleanly

**4. Unit tests (`tests/test_ytmusic_history.py`):**

Test the new YTMusicClient methods:
- `get_song()` returns song dict on success
- `get_song()` raises `YTMusicNotFoundError` for invalid video_id
- `get_song()` raises `YTMusicAuthError` when not authenticated
- `report_history()` returns True on success (HTTP 204)
- `report_history()` returns False on API failure (does not raise)
- `report_history()` returns False on auth failure (does not raise)
- Both methods use rate limiting

#### Dependencies

**Requires**: None (first phase)

**Enables**: Phase 2 (daemon integration requires the HistoryReporter class)

#### Completion Criteria

- [ ] `ytmpd/history_reporter.py` exists with `HistoryReporter` class
- [ ] `HistoryReporter.run()` implements MPD idle loop with track change detection
- [ ] Playback timing tracks actual play time (pause time excluded)
- [ ] Video ID extraction from proxy URLs works correctly
- [ ] `YTMusicClient.get_song()` wraps ytmusicapi's `get_song()`
- [ ] `YTMusicClient.report_history()` wraps `add_history_item()` with best-effort semantics
- [ ] `tests/test_history_reporter.py` covers all state transitions and error cases
- [ ] `tests/test_ytmusic_history.py` covers both new methods
- [ ] All tests pass: `pytest tests/test_history_reporter.py tests/test_ytmusic_history.py -v`
- [ ] No mypy errors: `mypy ytmpd/history_reporter.py`
- [ ] No ruff errors: `ruff check ytmpd/history_reporter.py`

#### Testing Requirements

- Unit tests with mocked dependencies (MPDClient, YTMusicClient, TrackStore)
- Test all state transitions: play->play, play->stop, play->pause->play, pause->different track
- Test timing logic: tracks meeting threshold, tracks below threshold, pause exclusion
- Test error recovery: MPD disconnect, API failures, auth failures
- Test clean shutdown via threading.Event

#### Notes

- The HistoryReporter needs its own MPDClient instance because `idle()` monopolizes the connection
- `idle('player')` returns `['player']` when a player event occurs -- it blocks until then
- `get_song()` is a network call per track, but rate is very low (once per 3-5 minutes of music)
- `add_history_item()` returns an HTTP response; 204 means success
- Use `time.monotonic()` not `time.time()` for duration tracking (immune to clock adjustments)
- The daemon already has a `_extract_video_id_from_url()` method -- reuse the same regex pattern
- Keep HistoryReporter independent of daemon.py -- it receives dependencies via constructor injection

---

### Phase 2: Config, Daemon Integration & Testing

**Objective**: Wire the HistoryReporter into the daemon lifecycle, add configuration support with validation, update the example config, and write integration tests to verify the end-to-end flow.

**Estimated Context Budget**: ~60k tokens

#### Deliverables

1. Config additions in `ytmpd/config.py` -- `history_reporting` section with validation
2. Daemon integration in `ytmpd/daemon.py` -- thread lifecycle for HistoryReporter
3. Updated `examples/config.yaml` -- documented history_reporting section
4. `tests/test_history_config.py` -- Config validation tests
5. `tests/test_history_integration.py` -- Integration tests for daemon wiring

#### Detailed Requirements

**1. Config additions (`ytmpd/config.py`):**

Add to the defaults dict (after `auto_auth` section):

```python
'history_reporting': {
    'enabled': False,
    'min_play_seconds': 30,
}
```

Add validation in `_validate_config()` for the new section:
- `history_reporting` must be a dict (if present)
- `enabled` must be a bool (default: False)
- `min_play_seconds` must be a positive integer (default: 30, minimum: 5)
- Warn if `min_play_seconds` is very low (< 10) -- likely misconfiguration

Follow the same validation pattern used for `auto_auth`:
```python
# History reporting settings
history = config.get('history_reporting', {})
if not isinstance(history, dict):
    history = {}
# validate enabled, min_play_seconds...
config['history_reporting'] = history
```

**2. Daemon integration (`ytmpd/daemon.py`):**

Add to `__init__()`:
- Initialize `self._history_reporter: HistoryReporter | None = None`
- Initialize `self._history_thread: threading.Thread | None = None`
- Initialize `self._history_shutdown = threading.Event()`
- If `config['history_reporting']['enabled']` is True:
  - Create `HistoryReporter` instance with:
    - `mpd_socket_path=config['mpd_socket_path']`
    - `ytmusic=self.ytmusic` (existing YTMusicClient)
    - `track_store=self.track_store` (existing TrackStore)
    - `proxy_config={'host': config['proxy_host'], 'port': config['proxy_port'], 'enabled': config['proxy_enabled']}`
    - `min_play_seconds=config['history_reporting']['min_play_seconds']`

Add a new background thread method:
```python
def _history_loop(self) -> None:
    """Run history reporter in background thread."""
    try:
        logger.info("History reporting started (min_play_seconds=%d)",
                     self.config['history_reporting']['min_play_seconds'])
        self._history_reporter.run(self._history_shutdown)
    except Exception as e:
        logger.error("History reporter crashed: %s", e, exc_info=True)
    finally:
        logger.info("History reporting stopped")
```

In `run()`, after spawning the other daemon threads:
- If history reporting is enabled, spawn the thread:
```python
if self._history_reporter is not None:
    self._history_thread = threading.Thread(
        target=self._history_loop,
        name="history-reporter",
        daemon=True,
    )
    self._history_thread.start()
    logger.info("History reporting thread started")
```

In `stop()`, before other thread shutdowns:
- Signal and join the history thread:
```python
if self._history_thread is not None:
    logger.info("Stopping history reporter...")
    self._history_shutdown.set()
    self._history_thread.join(timeout=5)
    if self._history_thread.is_alive():
        logger.warning("History reporter thread did not stop in time")
```

**3. Example config (`examples/config.yaml`):**

Add a new section at the end of the file:

```yaml
# ===== History Reporting Settings =====

# Report played tracks back to YouTube Music so your recommendations stay fresh.
# When enabled, ytmpd detects track changes via MPD and calls YouTube Music's
# history API for each track that plays longer than the minimum threshold.
history_reporting:
  # Enable history reporting (opt-in)
  # Default: false
  enabled: false

  # Minimum seconds a track must play before it counts as a "listen"
  # Tracks played for less than this are treated as skips and not reported.
  # Default: 30
  # Valid range: 5+
  min_play_seconds: 30
```

**4. Config tests (`tests/test_history_config.py`):**

- Test default config has `history_reporting` section with correct defaults
- Test `enabled` validates as bool
- Test `min_play_seconds` validates as positive int
- Test `min_play_seconds` < 5 is rejected or clamped
- Test missing `history_reporting` section gets populated with defaults
- Test invalid types are handled (string instead of int, etc.)

**5. Integration tests (`tests/test_history_integration.py`):**

- Test daemon creates HistoryReporter when `enabled=True`
- Test daemon does NOT create HistoryReporter when `enabled=False`
- Test daemon spawns history thread on `run()` (use mocks to prevent actual blocking)
- Test daemon stops history thread on `stop()`
- Test HistoryReporter receives correct config values from daemon
- Test end-to-end mock: simulate track change -> verify `report_history()` called with correct video_id

#### Dependencies

**Requires**: Phase 1 (HistoryReporter class must exist)

**Enables**: None (final phase)

#### Completion Criteria

- [ ] `config.py` defaults include `history_reporting` section
- [ ] `_validate_config()` validates `history_reporting.enabled` and `min_play_seconds`
- [ ] `daemon.py` creates and manages HistoryReporter lifecycle when enabled
- [ ] `daemon.py` does NOT create HistoryReporter when disabled (no wasted resources)
- [ ] Daemon shutdown cleanly stops history reporter thread
- [ ] `examples/config.yaml` documents the new section
- [ ] `tests/test_history_config.py` passes
- [ ] `tests/test_history_integration.py` passes
- [ ] Full test suite passes: `pytest tests/ -v`
- [ ] No mypy errors across modified files
- [ ] No ruff errors across modified files

#### Testing Requirements

- Config validation tests for all edge cases
- Daemon lifecycle tests with mocked HistoryReporter
- End-to-end integration test with mocked MPD and YTMusic
- Verify thread start/stop behavior
- Verify config values flow correctly to HistoryReporter

#### Notes

- Follow the exact same thread lifecycle pattern as `_auto_auth_loop` in daemon.py
- The history thread should be started after the proxy server thread (proxy must be running for URL resolution)
- The `_history_shutdown` event follows the same pattern as `_auto_auth_shutdown`
- Import `HistoryReporter` at the top of daemon.py alongside other ytmpd imports
- The proxy_config dict passed to HistoryReporter should match what mpd_client.py uses for URL generation

---

## Phase Dependencies Graph

```
Phase 1 (Core Module)
    |
    v
Phase 2 (Integration)
```

Linear dependency -- Phase 2 cannot start until Phase 1 is complete.

---

## Cross-Cutting Concerns

### Code Style

- Follow existing project style (ruff with line-length 100)
- Use type hints for all function signatures (mypy strict mode)
- Use `str | None` union syntax (Python 3.11+)
- Module-level logger: `logger = logging.getLogger(__name__)`

### Error Handling

- History reporting is best-effort: failures should log but never crash the daemon
- Use existing exception hierarchy from `ytmpd/exceptions.py`
- MPD reconnection on connection loss (with backoff)
- Auth failures should be logged but not retried (auto-auth loop handles refresh)

### Logging

- All logging via `logging.getLogger(__name__)`
- Key events to log at INFO: thread start/stop, successful history reports
- Errors at WARNING/ERROR: API failures, connection losses, skipped reports
- Debug: state transitions, timing details, video_id extraction

### Testing Strategy

- Unit tests with mocked dependencies in each phase
- Integration tests in Phase 2 for daemon wiring
- All tests must pass with `pytest tests/ -v`
- Type checking with `mypy ytmpd/`
- Linting with `ruff check ytmpd/`

---

## Integration Points

### HistoryReporter <-> MPDClient
- Uses its own MPDClient connection (not shared with daemon)
- Calls `idle('player')`, `status()`, `currentsong()` on python-mpd2 client

### HistoryReporter <-> YTMusicClient
- Calls `get_song(video_id)` and `report_history(song)`
- Shares the daemon's YTMusicClient instance (thread-safe due to rate limiter)

### HistoryReporter <-> TrackStore
- Reads track metadata by video_id (thread-safe, uses internal lock)

### Config <-> Daemon <-> HistoryReporter
- Config loaded once at daemon startup
- Daemon passes config values to HistoryReporter constructor
- No runtime config changes (restart daemon to change settings)

---

## Glossary

**idle('player')**: python-mpd2 call that blocks until MPD's player subsystem changes state (play/pause/stop/track change)
**add_history_item**: ytmusicapi method that sends a playback event to YouTube Music's videostatsPlaybackUrl endpoint
**get_song**: ytmusicapi method that returns full song metadata including playbackTracking URLs needed by add_history_item
**min_play_seconds**: Minimum number of seconds a track must play before it's reported as a listen (to filter out skips)
**proxy URL**: `http://host:port/proxy/{video_id}` -- the URL format MPD uses to request streams through ytmpd's proxy

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

**Context Budget Note**: Each phase is designed to fit within ~60k tokens of reading plus implementation, leaving buffer for thinking and output.
