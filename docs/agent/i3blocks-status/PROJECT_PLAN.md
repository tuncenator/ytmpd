# ytmpd - Project Plan

**Feature/Initiative**: i3blocks-status
**Type**: Feature Enhancement / Modernization
**Created**: 2025-10-20
**Estimated Total Phases**: 7

---

## 📍 Project Location

**IMPORTANT: All paths in this document are relative to the project root.**

- **Project Root**: `/home/tunc/Sync/Programs/ytmpd`
- **Verify with**: `pwd` → should output `/home/tunc/Sync/Programs/ytmpd`

When you see a path like `bin/ytmpd-status`, it means `/home/tunc/Sync/Programs/ytmpd/bin/ytmpd-status`

---

## Project Overview

### Purpose

The `i3blocks-status` feature enhances the existing `bin/ytmpd-status` script to provide a modern, performant, and feature-rich status display for i3blocks. This replaces three old bash scripts (`mpc.sh`, `mpc-bar.sh`, `mpc-surround.sh`) with a single Python-based solution that leverages ytmpd's unique capabilities to distinguish between YouTube-streamed and local music files.

**Key Goals:**
- Replace inefficient bash scripts with performant Python implementation
- Provide real-time music status display for i3blocks status bar
- Visualize YouTube vs local track playback with different colors/styles
- Display progress bars, playlist context, and sync status
- Support efficient MPD idle mode for minimal CPU usage
- Offer comprehensive CLI configuration options

### Scope

**In Scope**:
- Enhanced `bin/ytmpd-status` script with MPD client integration
- Current track display with play/pause/stop indicators
- Progress bar with customizable length and styles
- YouTube vs local track detection via database lookup
- Different visual styles for YouTube vs local (colors, progress bar chars)
- Next/previous track display from playlist
- Sync status indicators ("Resolving...", "Syncing...")
- CLI arguments for comprehensive configuration
- MPD idle mode for efficient updates
- i3blocks click handlers (play/pause, skip)
- Optional scrolling animation for long titles
- Installation documentation and example configs

**Out of Scope**:
- ytmpd daemon modifications (uses existing daemon/database)
- MPD server configuration changes
- i3blocks installation or setup
- Support for status bars other than i3blocks (can be added later)
- GUI or web interface
- Playlist management features

### Success Criteria

- [ ] Single Python script replaces all three bash scripts
- [ ] CPU usage significantly lower than bash script approach
- [ ] Visual distinction between YouTube and local tracks
- [ ] Progress bar accurately shows playback position
- [ ] All CLI options work as documented
- [ ] i3blocks integration works with click handlers
- [ ] Comprehensive test coverage (unit + integration)
- [ ] Documentation complete with examples

---

## Architecture Overview

### Key Components

1. **MPD Client**: Connect to MPD server using `python-mpd2` library
2. **Track Classifier**: Query ytmpd database to determine YouTube vs local
3. **Status Formatter**: Format track info, status icons, colors
4. **Progress Bar Renderer**: Calculate and render progress with different styles
5. **Playlist Context**: Retrieve next/prev tracks from MPD
6. **Sync Status Checker**: Determine if tracks are resolved/syncing
7. **CLI Interface**: argparse-based configuration
8. **i3blocks Integration**: Handle signals and output formatting

### Data Flow

```
MPD Server (port 6601)
    ↓ (python-mpd2 connection)
MPD Client Module
    ↓ (current track info)
Track Classifier ←→ ytmpd Database (~/.config/ytmpd/track_mapping.db)
    ↓ (track type: youtube/local, sync status)
Status Formatter + Progress Renderer + Playlist Context
    ↓ (formatted output)
i3blocks Display
```

### Technology Stack

- **Language**: Python 3.11+
- **Key Libraries**:
  - `python-mpd2` - MPD client (new dependency)
  - `click` - CLI framework (existing)
  - `sqlite3` - Database queries (stdlib)
  - Standard library: `socket`, `argparse`, `pathlib`
- **Testing**: pytest (existing)
- **Database**: ytmpd's SQLite database at `~/.config/ytmpd/track_mapping.db`
- **MPD**: Connect to existing MPD server on port 6601

---

## Phase Breakdown

> **Note for Agents**: Only read the section for your assigned phase. Reading all phases wastes context.

---

### Phase 1: Core MPD Status Display

**Objective**: Replace the socket-based daemon connection with MPD client and implement basic status display with YouTube/local track detection.

**Estimated Context Budget**: ~35k tokens

#### Deliverables

1. `bin/ytmpd-status` - Enhanced with MPD client connection
2. MPD connection helper functions
3. Track classification function (YouTube vs local via database)
4. Status icon rendering (play/pause/stop)
5. Color coding for YouTube vs local tracks
6. Basic tests for core functionality

#### Detailed Requirements

**Modify** `bin/ytmpd-status`:

1. **Add python-mpd2 dependency**:
   - Add `python-mpd2>=3.1.0` to `pyproject.toml` dependencies
   - Install with `uv pip install python-mpd2`

2. **Replace socket connection with MPD client**:
   - Remove `get_socket_path()`, `send_command()`, `parse_status()` functions
   - Add `get_mpd_client(host='localhost', port=6601) -> MPDClient` function
   - Handle connection errors gracefully
   - Get current song info: `currentsong()`, `status()`

3. **Implement track classification**:
   - Add `get_track_type(file_path: str) -> str` function
   - Query ytmpd database at `~/.config/ytmpd/track_mapping.db`
   - Check if file path starts with `http://localhost:6602/proxy/` (YouTube)
   - Return `'youtube'`, `'local'`, or `'unknown'`
   - Handle database not existing (return 'unknown')

4. **Color scheme for track types**:
   - **YouTube tracks**:
     - Playing: `#FF6B35` (orange)
     - Paused: `#FFB84D` (light orange)
   - **Local tracks**:
     - Playing: `#00FF00` (green)
     - Paused: `#FFFF00` (yellow)
   - **Stopped/Unknown**: `#808080` (gray)

5. **Status icons**:
   - Playing: `▶`
   - Paused: `⏸` or `▷`
   - Stopped: `⏹` or `◼`

6. **Output format** (same i3blocks format):
   ```
   Line 1: Full text (e.g., "▶ Artist - Title")
   Line 2: Short text (truncated version)
   Line 3: Color code
   ```

7. **Error handling**:
   - MPD not running → Show "⏹ MPD stopped" in gray
   - No current song → Show "⏹ Stopped" in gray
   - Database query fails → Fall back to 'unknown' type

#### Dependencies

**Requires**: None (first phase)

**Enables**:
- Phase 2: Progress Bar (needs MPD connection and track info)
- Phase 3: Playlist Context (needs MPD client)

#### Completion Criteria

- [ ] `python-mpd2` added to pyproject.toml and installed
- [ ] MPD client connection implemented and working
- [ ] Track classification function queries database correctly
- [ ] YouTube tracks show orange colors when playing/paused
- [ ] Local tracks show green/yellow colors when playing/paused
- [ ] Stopped state shows gray
- [ ] Status icons display correctly (▶ ⏸ ⏹)
- [ ] Handles MPD not running gracefully
- [ ] Handles missing database gracefully
- [ ] All existing functionality preserved (truncation, formatting)

#### Testing Requirements

Create `tests/test_ytmpd_status.py`:
- Test MPD connection (mock MPDClient)
- Test track classification with mocked database
- Test color selection for different states and track types
- Test error handling (no MPD, no database)
- Test output formatting

**Manual Testing**:
- Run with MPD playing a YouTube track → verify orange color
- Run with MPD playing a local track → verify green color
- Run with MPD paused → verify correct paused colors
- Run with MPD stopped → verify gray
- Run with MPD not running → verify graceful degradation

#### Notes

- Keep the existing environment variable support (`YTMPD_STATUS_MAX_LENGTH`) for backward compatibility
- Focus on getting the connection and classification working; formatting refinements come in later phases
- The database query can be simple: just check if `file` column value starts with the proxy URL pattern
- Don't worry about progress bars, playlist context, or CLI args in this phase

---

### Phase 2: Progress Bar Implementation

**Objective**: Add configurable progress bar rendering with different styles for YouTube vs local tracks.

**Estimated Context Budget**: ~40k tokens

#### Deliverables

1. Progress bar calculation functions
2. Progress bar rendering with customizable styles
3. Time formatting and display (current/total)
4. Different bar styles for YouTube vs local
5. Tests for progress calculations

#### Detailed Requirements

**Enhance** `bin/ytmpd-status`:

1. **Add progress bar functions**:
   - `calculate_progress(elapsed: int, duration: int, bar_length: int) -> int`
     - Convert elapsed/duration seconds to number of filled blocks
     - Handle edge cases: duration=0, elapsed > duration
   - `format_time(seconds: int) -> str`
     - Convert seconds to "M:SS" format (e.g., "3:45", "15:02")
     - Already exists but may need enhancement
   - `render_progress_bar(progress: int, total_length: int, style: str) -> str`
     - Render bar using specified style characters
     - Style options: 'blocks', 'smooth', 'simple'

2. **Progress bar styles**:
   - **Local tracks** (default):
     - Style: `blocks`
     - Characters: `█` (filled), `░` (empty)
     - Example: `█████░░░░░`
   - **YouTube tracks**:
     - Style: `smooth`
     - Characters: `▰` (filled), `▱` (empty)
     - Example: `▰▰▰▰▰▱▱▱▱▱`
   - **Simple** (fallback):
     - Characters: `#` (filled), `-` (empty)
     - Example: `#####-----`

3. **Default bar length**: 10 characters (configurable via env var for now)

4. **Progress display format**:
   ```
   ▶ Artist - Title [3:45 █████░░░░░ 7:30]
   ```
   Or with time before/after bar:
   ```
   ▶ Artist - Title 3:45 █████░░░░░ 7:30
   ```

5. **Environment variable support**:
   - `YTMPD_STATUS_BAR_LENGTH`: Bar length (default: 10)
   - `YTMPD_STATUS_SHOW_BAR`: Enable/disable bar (default: true)
   - `YTMPD_STATUS_BAR_STYLE`: Force specific style (override auto-detection)

6. **Edge cases**:
   - Stream without duration (show `--:--` or elapsed only)
   - Duration = 0 (don't show bar)
   - Elapsed > duration (fill entire bar)
   - Very short tracks (<10s) - ensure bar updates properly

#### Dependencies

**Requires**:
- Phase 1: MPD connection and track classification

**Enables**:
- Phase 3: Playlist Context (progress bar + context display)
- Phase 4: Integration Testing

#### Completion Criteria

- [ ] Progress calculation accurate within 1 second
- [ ] Different bar styles render correctly for YouTube/local
- [ ] Time formatting works for all ranges (0:00 to 99:59)
- [ ] Bar length configurable via environment variable
- [ ] Progress bar can be disabled
- [ ] Edge cases handled gracefully (no duration, etc.)
- [ ] Bar updates reflect actual playback position
- [ ] Integration with Phase 1 code works seamlessly

#### Testing Requirements

**Unit Tests** (`tests/test_ytmpd_status.py`):
- `test_calculate_progress()` - various elapsed/duration combinations
- `test_format_time()` - edge cases (0, 60, 3599, etc.)
- `test_render_progress_bar()` - all three styles
- `test_progress_bar_edge_cases()` - duration=0, elapsed>duration, etc.

**Manual Testing**:
- Play a local track → verify `█░` style bar
- Play a YouTube track → verify `▰▱` style bar
- Test with different bar lengths (5, 10, 20)
- Verify time display updates every second
- Test with very short track (<30s)
- Test with long track (>1 hour) - ensure format handles it

#### Notes

- Consider how the progress bar fits with the max length truncation - bar should be included in length calculation
- May need to adjust the overall format string to accommodate the bar
- The bar should update smoothly - consider how i3blocks will refresh (addressed in Phase 5)
- For now, rely on periodic polling - idle mode comes in Phase 5

---

### Phase 3: Playlist Context & Sync Status

**Objective**: Add next/previous track display, sync status checking, and context-aware messaging.

**Estimated Context Budget**: ~45k tokens

#### Deliverables

1. Playlist position and context retrieval
2. Next/previous track display (optional)
3. Sync status checking from database
4. Context-aware status messages
5. Text truncation for long titles with proper ellipsis placement
6. Tests for playlist and sync status features

#### Detailed Requirements

**Enhance** `bin/ytmpd-status`:

1. **Playlist context functions**:
   - `get_playlist_context() -> dict`
     - Get current position in playlist
     - Get next track info (artist, title)
     - Get previous track info (artist, title)
     - Return dict with 'current_pos', 'total', 'next', 'prev'
   - Handle edge cases: first song (no prev), last song (no next), single song

2. **Sync status checking**:
   - `get_sync_status(video_id: str) -> str`
     - Query ytmpd database for track sync status
     - Check if `stream_url IS NULL` (unresolved)
     - Return status: `'resolved'`, `'unresolved'`, `'local'`, `'unknown'`
   - Extract video_id from proxy URL pattern: `http://localhost:6602/proxy/{video_id}`

3. **Context-aware messages**:
   Show additional context in certain situations:
   - **Unresolved YouTube track**: `"▶ Artist - Title [Resolving...]"`
   - **First track in playlist**: `"▶ Artist - Title [1/25]"`
   - **Last track in playlist**: `"▶ Artist - Title [25/25]"`
   - **Single track**: `"▶ Artist - Title [1/1]"`

4. **Next/Previous display** (optional, env var controlled):
   - `YTMPD_STATUS_SHOW_NEXT`: Show next track (default: false)
   - `YTMPD_STATUS_SHOW_PREV`: Show previous track (default: false)
   - Format when enabled:
     ```
     ▶ Current Artist - Title [3:45/7:30]
     ↓ Next Artist - Title
     ```

5. **Truncation strategy**:
   - Truncate from the middle of title if possible, not the end
   - Preserve artist name when truncating
   - Use proper ellipsis: `…` (U+2026) instead of `...`
   - Example: `"Very Long Song Title Name" → "Very Long … Name"`

6. **Compact mode**:
   - `YTMPD_STATUS_COMPACT`: Minimal output (default: false)
   - Compact format: `"▶ Artist - Title"` (no time, no bar, no context)

#### Dependencies

**Requires**:
- Phase 1: MPD client and track classification
- Phase 2: Progress bar rendering

**Enables**:
- Phase 4: Integration Testing

#### Completion Criteria

- [ ] Playlist context retrieval works correctly
- [ ] Next/previous track info displays when enabled
- [ ] Sync status detection accurate for YouTube tracks
- [ ] "Resolving..." message shows for unresolved tracks
- [ ] Playlist position shows for first/last/single tracks
- [ ] Truncation preserves most important info
- [ ] Compact mode reduces output appropriately
- [ ] All environment variables work correctly
- [ ] Integration with Phases 1 & 2 seamless

#### Testing Requirements

**Unit Tests** (`tests/test_ytmpd_status.py`):
- `test_get_playlist_context()` - various playlist scenarios
- `test_get_sync_status()` - resolved, unresolved, local tracks
- `test_context_messages()` - verify correct messages
- `test_truncation()` - various title lengths
- `test_compact_mode()` - output format

**Manual Testing**:
- Play YouTube track that's not resolved → verify "Resolving..." appears
- Play first track in playlist → verify position shows
- Play last track → verify position shows
- Enable next track display → verify next track shows
- Test with very long track titles → verify smart truncation
- Test compact mode → verify minimal output

#### Notes

- The sync status feature is ytmpd-specific and differentiates this from a generic MPD status script
- Consider i3blocks screen space limitations - next/prev display should be optional
- The database query for sync status should be fast (indexed lookup)
- May want to cache database connections rather than opening/closing per query

---

### Phase 4: Integration Testing

**Objective**: Verify that all components from Phases 1-3 work together correctly with various track types, playlist scenarios, and edge cases.

**Estimated Context Budget**: ~35k tokens

#### Deliverables

1. Integration test suite
2. Test scenarios covering all phase 1-3 features
3. Manual testing checklist
4. Bug fixes for any integration issues discovered
5. Performance testing and optimization if needed

#### Detailed Requirements

**Create comprehensive integration tests**:

1. **Create** `tests/integration/test_ytmpd_status_integration.py`:
   - Test full workflow: MPD connection → track classification → progress bar → output
   - Mock MPD server responses for different scenarios
   - Mock ytmpd database with sample data
   - Verify complete output format matches expectations

2. **Test scenarios**:

   **Scenario 1: YouTube Track - Playing - Resolved**
   - Mock MPD: playing YouTube track, 2:30 elapsed, 5:00 total
   - Mock DB: track resolved (has stream_url)
   - Expected: Orange playing icon, smooth progress bar, correct times

   **Scenario 2: Local Track - Paused - Mid-Playlist**
   - Mock MPD: paused local track, position 5/10
   - Expected: Yellow paused icon, blocks progress bar, shows position

   **Scenario 3: YouTube Track - Playing - Unresolved**
   - Mock MPD: playing YouTube track
   - Mock DB: track unresolved (stream_url IS NULL)
   - Expected: "Resolving..." message, orange color

   **Scenario 4: First Track in Playlist**
   - Mock MPD: position 1/25
   - Expected: Position indicator shows [1/25]

   **Scenario 5: Last Track in Playlist**
   - Mock MPD: position 25/25
   - Expected: Position indicator shows [25/25]

   **Scenario 6: MPD Stopped**
   - Mock MPD: state = stopped
   - Expected: Stop icon, gray color, "Stopped" message

   **Scenario 7: Long Title Truncation**
   - Track with very long title (>80 chars)
   - Expected: Smart truncation preserves key info

   **Scenario 8: Next/Prev Display Enabled**
   - Mock MPD: playlist with next/prev tracks
   - Enable YTMPD_STATUS_SHOW_NEXT
   - Expected: Next track info displayed

   **Scenario 9: No Duration Track**
   - Stream with unknown duration
   - Expected: Shows elapsed time only, no bar

   **Scenario 10: Database Not Available**
   - ytmpd database doesn't exist
   - Expected: Falls back to 'unknown' type, uses default colors

3. **Environment variable integration tests**:
   - Test all env vars together: bar length, show bar, compact mode, etc.
   - Verify env vars override defaults correctly
   - Test invalid env var values (graceful degradation)

4. **Manual testing checklist** (document in phase summary):
   - [ ] Test with real MPD server playing YouTube track
   - [ ] Test with real MPD server playing local track
   - [ ] Verify colors appear correctly in i3blocks
   - [ ] Test progress bar updates smoothly (re-run script every 1-2 seconds)
   - [ ] Test with ytmpd daemon running vs not running
   - [ ] Test truncation with real long titles
   - [ ] Verify all env vars work as expected

5. **Performance testing**:
   - Measure execution time (should be <100ms)
   - Check database query performance
   - Verify no memory leaks with repeated runs
   - Test with large playlists (100+ tracks)

6. **Bug fixes**:
   - Fix any integration issues discovered
   - Handle edge cases that were missed
   - Improve error messages if needed

#### Dependencies

**Requires**:
- Phase 1: Core MPD Status Display
- Phase 2: Progress Bar Implementation
- Phase 3: Playlist Context & Sync Status

**Enables**:
- Phase 5: CLI Arguments (confidence that base functionality works)
- Phase 6: i3blocks Integration (validated core before adding integration layer)

#### Completion Criteria

- [ ] All 10+ integration test scenarios pass
- [ ] Manual testing checklist completed successfully
- [ ] Performance meets <100ms execution time target
- [ ] No integration bugs remaining
- [ ] All environment variables tested together
- [ ] Database connection handling tested thoroughly
- [ ] Output format verified in actual i3blocks environment
- [ ] Edge cases handled gracefully

#### Testing Requirements

**Integration Tests** (`tests/integration/test_ytmpd_status_integration.py`):
- Use pytest fixtures for MPD client mocks
- Use pytest fixtures for database mocks
- Test complete workflows end-to-end
- Verify exact output format (all 3 lines for i3blocks)

**Performance Tests**:
- Use `time` or `pytest-benchmark` to measure execution time
- Test with various playlist sizes
- Test with database queries

**Manual Tests**:
- Document results in phase summary
- Include screenshots/examples if possible
- Note any unexpected behavior

#### Notes

- This phase is about verification and bug fixing, not new features
- If significant issues are found, they should be fixed in this phase
- Document any workarounds or limitations discovered
- Update documentation if behavior differs from spec
- This provides confidence before adding CLI args and i3blocks integration

---

### Phase 5: CLI Arguments & Configuration

**Objective**: Replace environment variables with comprehensive CLI arguments, maintain backward compatibility, and provide flexible configuration options.

**Estimated Context Budget**: ~40k tokens

#### Deliverables

1. argparse-based CLI interface
2. All configuration options as CLI arguments
3. Backward compatibility with environment variables
4. Help documentation and usage examples
5. Configuration validation
6. Tests for CLI argument parsing

#### Detailed Requirements

**Enhance** `bin/ytmpd-status`:

1. **Replace environment variables with argparse**:

   Create comprehensive CLI with following arguments:

   **Connection Options**:
   - `--host` - MPD server host (default: localhost)
   - `--port` - MPD server port (default: 6601)

   **Display Options**:
   - `--max-length` / `-l` - Maximum output length (default: 50)
   - `--format` / `-f` - Format string template (default: auto)
   - `--compact` / `-c` - Compact mode flag

   **Progress Bar Options**:
   - `--show-bar / --no-show-bar` - Enable/disable progress bar (default: show)
   - `--bar-length` - Progress bar length in chars (default: 10)
   - `--bar-style` - Force specific style: blocks, smooth, simple (default: auto)

   **Playlist Context Options**:
   - `--show-next` - Show next track
   - `--show-prev` - Show previous track
   - `--show-position` - Show playlist position

   **Color Options**:
   - `--color-youtube-playing` - Custom color for YouTube playing (default: #FF6B35)
   - `--color-youtube-paused` - Custom color for YouTube paused (default: #FFB84D)
   - `--color-local-playing` - Custom color for local playing (default: #00FF00)
   - `--color-local-paused` - Custom color for local paused (default: #FFFF00)
   - `--color-stopped` - Custom color for stopped (default: #808080)

   **Icon Options**:
   - `--icon-playing` - Custom playing icon (default: ▶)
   - `--icon-paused` - Custom paused icon (default: ⏸)
   - `--icon-stopped` - Custom stopped icon (default: ⏹)

   **Debug Options**:
   - `--verbose` / `-v` - Verbose output (show connection info, etc.)
   - `--version` - Show version info

2. **Format string templating**:

   Support custom format strings with placeholders:
   - `{icon}` - Status icon
   - `{artist}` - Artist name
   - `{title}` - Song title
   - `{album}` - Album name
   - `{elapsed}` - Elapsed time (formatted)
   - `{duration}` - Total duration (formatted)
   - `{bar}` - Progress bar
   - `{position}` - Playlist position
   - `{total}` - Playlist total
   - `{next}` - Next track (if available)
   - `{prev}` - Previous track (if available)

   Default format: `"{icon} {artist} - {title} [{elapsed} {bar} {duration}]"`

   Example custom format: `"{icon} {title} ({elapsed}/{duration})"`

3. **Backward compatibility with environment variables**:

   Priority: CLI args > Environment variables > Defaults

   Maintain support for existing env vars:
   - `YTMPD_STATUS_MAX_LENGTH` → `--max-length`
   - `YTMPD_STATUS_FORMAT` → `--format`
   - `YTMPD_STATUS_BAR_LENGTH` → `--bar-length`
   - `YTMPD_STATUS_SHOW_BAR` → `--show-bar`
   - `YTMPD_STATUS_COMPACT` → `--compact`
   - etc.

4. **Configuration validation**:
   - Validate port range (1-65535)
   - Validate max-length (1-200)
   - Validate bar-length (1-50)
   - Validate color format (#RRGGBB)
   - Validate format string has valid placeholders
   - Provide helpful error messages

5. **Help documentation**:
   ```
   usage: ytmpd-status [options]

   Display ytmpd/MPD status for i3blocks with YouTube track detection

   Connection Options:
     --host HOST           MPD server host (default: localhost)
     --port PORT           MPD server port (default: 6601)

   Display Options:
     -l, --max-length LEN  Maximum output length (default: 50)
     -f, --format FORMAT   Custom format string (default: auto)
     -c, --compact         Use compact display mode

   [... etc for all options ...]

   Format String Placeholders:
     {icon}     - Playback status icon
     {artist}   - Track artist
     {title}    - Track title
     [... etc ...]

   Examples:
     ytmpd-status
     ytmpd-status --compact --no-show-bar
     ytmpd-status --format "{icon} {title} ({elapsed}/{duration})"
     ytmpd-status --bar-length 15 --show-next
   ```

#### Dependencies

**Requires**:
- Phase 1-3: All core functionality
- Phase 4: Integration testing (validates base works)

**Enables**:
- Phase 6: i3blocks integration (can use CLI args in config)

#### Completion Criteria

- [ ] All CLI arguments implemented and working
- [ ] Format string templating works correctly
- [ ] Backward compatibility with env vars maintained
- [ ] Configuration validation catches invalid values
- [ ] Help text comprehensive and accurate
- [ ] Priority order correct: CLI > env > defaults
- [ ] All custom colors work
- [ ] All custom icons work
- [ ] Custom format strings work
- [ ] Tests cover all CLI argument combinations

#### Testing Requirements

**Unit Tests** (`tests/test_ytmpd_status_cli.py`):
- `test_parse_args()` - various CLI argument combinations
- `test_env_var_compatibility()` - env vars still work
- `test_priority_order()` - CLI overrides env vars
- `test_validation()` - invalid values rejected
- `test_format_string()` - placeholder substitution
- `test_help_text()` - help renders correctly

**Manual Testing**:
- Run with various CLI arg combinations
- Test format string customization
- Verify env vars still work
- Test custom colors in i3blocks
- Test validation error messages

#### Notes

- argparse provides automatic help generation - use it
- Consider adding a `--config` option for config file support (future enhancement)
- Format string feature makes this very flexible for different preferences
- Validation should be helpful, not restrictive
- Document all options in `--help` output

---

### Phase 6: i3blocks Integration & Idle Mode

**Objective**: Implement efficient MPD idle mode for minimal CPU usage, add i3blocks click handlers, and provide complete i3blocks integration documentation.

**Estimated Context Budget**: ~40k tokens

#### Deliverables

1. MPD idle mode for efficient updates
2. i3blocks signal handling (SIGUSR1)
3. Click handler support (play/pause, skip)
4. Example i3blocks configuration
5. Installation documentation
6. Tests for idle mode and signal handling

#### Detailed Requirements

**Enhance** `bin/ytmpd-status`:

1. **Add idle mode support**:

   Create optional `--idle` mode for continuous monitoring:
   - `--idle` - Run continuously, update on MPD state changes
   - Use `mpd.idle(['player'])` to wait for playback changes
   - Only update output when something changes (efficient)
   - Handle MPD disconnection/reconnection
   - Graceful shutdown on SIGTERM/SIGINT

   Example behavior:
   ```bash
   ytmpd-status --idle
   # Waits for MPD changes, outputs new status on each change
   # Uses minimal CPU while waiting
   ```

2. **Signal handling for i3blocks**:

   i3blocks can send SIGUSR1 for manual refresh:
   - Catch SIGUSR1 signal
   - Trigger immediate status update
   - Continue idle mode after update
   - Example i3blocks usage: `pkill -RTMIN+10 ytmpd-status`

3. **Click handler support**:

   i3blocks passes `$BLOCK_BUTTON` environment variable:
   - **Button 1 (left click)**: Toggle play/pause
   - **Button 2 (middle click)**: Stop playback
   - **Button 3 (right click)**: Show detailed info (optional)
   - **Scroll up (button 4)**: Next track
   - **Scroll down (button 5)**: Previous track

   Implement `handle_click()` function:
   - Read `$BLOCK_BUTTON` environment variable
   - Execute appropriate MPD command
   - Update display immediately
   - Return to idle mode

4. **i3blocks configuration example**:

   Create `examples/i3blocks.conf`:
   ```ini
   [ytmpd-status]
   command=/path/to/ytmpd-status --idle --bar-length 12
   interval=persist
   signal=10
   markup=none

   # Click handlers:
   # Left click: play/pause
   # Middle click: stop
   # Scroll up: next track
   # Scroll down: previous track
   ```

5. **Alternative: Polling mode** (default, no --idle):

   For users who don't want persistent process:
   - Run once, output status, exit
   - i3blocks calls script every N seconds (interval=2)
   - Less efficient but simpler

   Example:
   ```ini
   [ytmpd-status]
   command=/path/to/ytmpd-status --bar-length 12
   interval=2
   ```

6. **Installation script**:

   Create `scripts/install-i3blocks.sh`:
   ```bash
   #!/bin/bash
   # Install ytmpd-status for i3blocks
   # - Check dependencies (python-mpd2, i3blocks)
   # - Copy example config
   # - Show setup instructions
   ```

7. **Documentation**:

   Create `docs/i3blocks-integration.md`:
   - Installation instructions
   - Configuration examples (idle vs polling)
   - Customization guide (colors, format, icons)
   - Troubleshooting (MPD not connecting, etc.)
   - Screenshots/examples

#### Dependencies

**Requires**:
- Phase 1-3: Core functionality
- Phase 4: Integration testing
- Phase 5: CLI arguments

**Enables**:
- Phase 7: Final testing and polish

#### Completion Criteria

- [ ] Idle mode works efficiently (minimal CPU usage)
- [ ] Status updates immediately on MPD changes
- [ ] SIGUSR1 signal triggers refresh
- [ ] All click handlers work correctly
- [ ] Polling mode works as fallback
- [ ] Example i3blocks config provided
- [ ] Installation script works
- [ ] Documentation comprehensive
- [ ] Handles MPD disconnect/reconnect gracefully
- [ ] Graceful shutdown on SIGTERM/SIGINT

#### Testing Requirements

**Unit Tests** (`tests/test_ytmpd_status_idle.py`):
- `test_idle_mode()` - mock MPD idle responses
- `test_signal_handling()` - simulate SIGUSR1
- `test_click_handlers()` - test all button values
- `test_reconnection()` - MPD disconnect/reconnect

**Manual Testing**:
- Run in idle mode with i3blocks
- Test click handlers: left click play/pause, scroll to skip
- Test signal refresh: `pkill -RTMIN+10 ytmpd-status`
- Kill MPD, verify graceful handling, restart MPD, verify reconnect
- Measure CPU usage in idle mode (should be near 0%)
- Test polling mode as alternative

#### Notes

- Idle mode is the recommended approach for i3blocks (most efficient)
- Click handlers make this much more useful than passive display
- Signal handling allows manual refresh when needed
- Documentation is critical - this is user-facing feature
- Consider adding systemd user service example (optional)
- The `interval=persist` setting in i3blocks keeps the process running

---

### Phase 7: Testing, Scrolling & Polish

**Objective**: Complete test coverage, implement optional scrolling animation, fix any remaining bugs, and finalize documentation.

**Estimated Context Budget**: ~35k tokens

#### Deliverables

1. Comprehensive test coverage (unit + integration)
2. Optional scrolling animation for long titles
3. Bug fixes and polish
4. Performance benchmarking vs old bash scripts
5. Complete README documentation
6. Final code review and cleanup

#### Detailed Requirements

1. **Complete test coverage**:

   Achieve >80% code coverage:
   - Add missing unit tests
   - Add edge case tests
   - Add error condition tests
   - Run `pytest --cov=bin/ytmpd-status --cov-report=html`

2. **Optional scrolling animation**:

   Add `--scroll` mode for long titles (low priority):
   - `--scroll` - Enable scrolling for titles > max length
   - Animate text horizontally (like old `mpc-surround.sh`)
   - Use spaces for padding, cycle through text
   - Configurable scroll speed: `--scroll-speed` (chars per update)
   - Only works in idle mode (updates display periodically)

   Example:
   ```
   # Title: "Very Long Song Title That Doesn't Fit"
   # Max length: 20 chars

   Frame 1: "Very Long Song Ti..."
   Frame 2: "ery Long Song Tit..."
   Frame 3: "ry Long Song Titl..."
   [... continues scrolling ...]
   ```

   Implementation:
   - Track scroll offset in idle mode
   - Update every N idle cycles (configurable)
   - Reset offset when track changes
   - Optional: add padding spaces between cycles

3. **Bug fixes and polish**:
   - Fix any bugs discovered during final testing
   - Improve error messages
   - Handle all edge cases gracefully
   - Code cleanup: remove dead code, improve comments
   - Ensure consistent style (black formatting)
   - Type hints for all functions

4. **Performance benchmarking**:

   Compare with old bash scripts:
   - Measure execution time: ytmpd-status vs mpc.sh
   - Measure CPU usage: idle mode vs bash `while true` loop
   - Memory footprint comparison
   - Document results in README

   Expected results:
   - Execution time: <100ms (bash scripts: 200-500ms)
   - CPU usage (idle): <0.1% (bash scripts: 2-5%)
   - Memory: ~20MB (bash scripts: ~5MB but higher total due to multiple processes)

5. **Documentation finalization**:

   **Update main README** (or create README-i3blocks.md):
   - Feature overview
   - Quick start guide
   - Installation instructions
   - Configuration guide
   - Examples (screenshots if possible)
   - Troubleshooting section
   - Performance comparison
   - Migration guide from old bash scripts

   **Code documentation**:
   - Docstrings for all functions
   - Module-level docstring
   - Inline comments for complex logic
   - Type hints everywhere

6. **Final code review**:
   - Run linters: `pylint bin/ytmpd-status`
   - Run type checker: `mypy bin/ytmpd-status`
   - Format code: `black bin/ytmpd-status`
   - Security review: no injection vulnerabilities
   - Review error handling completeness

7. **Deprecation plan for bash scripts**:
   - Document how to migrate from old scripts
   - Provide side-by-side comparison
   - Consider adding deprecation warnings to old scripts
   - Update any other documentation referencing old scripts

#### Dependencies

**Requires**:
- Phase 1-6: All previous phases complete

**Enables**:
- Feature complete and ready for production use!

#### Completion Criteria

- [ ] Test coverage >80%
- [ ] All edge cases tested
- [ ] Optional scrolling animation working (if implemented)
- [ ] Performance benchmarking complete
- [ ] Performance meets or exceeds targets
- [ ] README comprehensive and accurate
- [ ] All code documented with docstrings
- [ ] Code passes linters (pylint, mypy, black)
- [ ] No known bugs remaining
- [ ] Migration guide from bash scripts complete
- [ ] Examples and screenshots provided

#### Testing Requirements

**Final Test Suite**:
- Run entire test suite: `pytest`
- Check coverage: `pytest --cov`
- Run linters: `pylint`, `mypy`, `black --check`
- Manual testing checklist (all features)
- Performance benchmarks documented

**Edge Cases to Test**:
- Very long titles (>200 chars)
- Unicode characters in titles (emoji, special chars)
- Missing metadata (no artist, no title)
- Network issues (MPD timeout)
- Database corruption
- Concurrent access to database
- Rapid track changes
- Playlist edge cases (empty, single track, 1000+ tracks)

**Manual Testing Checklist**:
- [ ] Test in real i3blocks environment
- [ ] Test all CLI arguments
- [ ] Test all click handlers
- [ ] Test idle mode for extended period (1+ hour)
- [ ] Test with various track types (YouTube, local, streaming radio)
- [ ] Test with ytmpd daemon not running
- [ ] Test with MPD not running
- [ ] Verify colors in terminal and i3blocks
- [ ] Test scrolling animation (if implemented)
- [ ] Verify graceful error handling

#### Notes

- This phase is about polish and completeness, not new features
- Scrolling animation is nice-to-have, not critical (can be skipped if context tight)
- Performance benchmarking provides great validation of the rewrite
- Documentation is critical for user adoption
- Consider adding a changelog for version tracking
- This completes the feature - celebrate! 🎉

---

## Phase Dependencies Graph

```
Phase 1: Core MPD Status Display
    ↓
Phase 2: Progress Bar Implementation
    ↓
Phase 3: Playlist Context & Sync Status
    ↓
Phase 4: Integration Testing
    ↓
Phase 5: CLI Arguments & Configuration
    ↓
Phase 6: i3blocks Integration & Idle Mode
    ↓
Phase 7: Testing, Scrolling & Polish
```

All phases are sequential - each builds on the previous.

---

## Cross-Cutting Concerns

### Code Style

- Follow PEP 8 for Python
- Use type hints for all function signatures
- Maximum line length: 100 characters (black default: 88)
- Use docstrings for all public functions (Google style)
- Use f-strings for string formatting

### Error Handling

- Catch specific exceptions, not generic `Exception`
- Provide helpful error messages with context
- Gracefully degrade on non-critical errors (show fallback status)
- Log errors if verbose mode enabled
- Never crash - always output something for i3blocks

**Error hierarchy**:
1. MPD not running → Show "⏹ MPD stopped" (gray)
2. Database error → Fall back to 'unknown' track type
3. Network timeout → Retry once, then show error state
4. Invalid config → Show validation error, exit cleanly

### Logging

- Use Python's `logging` module (not print statements)
- Log level: INFO by default, DEBUG if `--verbose`
- Format: `[timestamp] [level] message`
- Log to stderr (stdout reserved for i3blocks output)
- Example logs:
  - INFO: "Connected to MPD on localhost:6601"
  - DEBUG: "Track type: youtube, video_id: abc123"
  - ERROR: "Failed to query database: [error]"

### Configuration

- Priority: CLI args > Environment variables > Defaults
- All defaults defined in one place (constants at top of file)
- Validation happens early (before MPD connection)
- Invalid values trigger helpful error message + exit

### Database Access

- Use context managers for database connections
- Handle database not existing (not an error - just means no ytmpd)
- Use prepared statements to prevent SQL injection (even though no user input)
- Close connections promptly
- Consider connection pooling if performance issue (probably not needed)

### Testing Strategy

**Unit Tests**:
- Mock external dependencies (MPD, database)
- Test each function in isolation
- Focus on logic and edge cases
- Fast execution (<1s for all unit tests)

**Integration Tests**:
- Test complete workflows
- Mock external services but test integration between modules
- Verify output format correctness
- Test environment variable and CLI arg interaction

**Manual Tests**:
- Real MPD server
- Real ytmpd database
- Real i3blocks environment
- Actual user workflows

**Coverage Goal**: >80% line coverage

---

## Integration Points

### bin/ytmpd-status ↔ MPD Server

- Connection: TCP socket to localhost:6601
- Protocol: MPD protocol via python-mpd2
- Commands: `currentsong()`, `status()`, `playlistinfo()`, `idle()`
- Error handling: Graceful degradation if MPD not running

### bin/ytmpd-status ↔ ytmpd Database

- Database: SQLite at `~/.config/ytmpd/track_mapping.db`
- Tables: `tracks` (video_id, title, artist, stream_url, etc.)
- Queries:
  - Check if track is YouTube: `SELECT video_id FROM tracks WHERE ...`
  - Check sync status: `SELECT stream_url FROM tracks WHERE video_id = ?`
- Error handling: Database not existing is not an error (just means local tracks only)

### bin/ytmpd-status ↔ i3blocks

- Output format: 3 lines (full text, short text, color)
- Input: Environment variable `$BLOCK_BUTTON` for click events
- Signals: SIGUSR1 for manual refresh
- Modes: Persistent (`interval=persist`) or polling (`interval=N`)

---

## Data Schemas

### MPD `currentsong()` Response

```python
{
    'file': 'http://localhost:6602/proxy/abc123',  # or '/path/to/song.mp3'
    'artist': 'Artist Name',
    'title': 'Song Title',
    'album': 'Album Name',
    'time': '300',  # duration in seconds (may be '0' for streams)
    'pos': '5',     # position in playlist
    'id': '123'
}
```

### MPD `status()` Response

```python
{
    'state': 'play',  # or 'pause', 'stop'
    'elapsed': '123.456',  # seconds with decimals
    'duration': '300.0',   # seconds with decimals
    'volume': '80',
    'playlistlength': '25'
}
```

### ytmpd Database Schema

```sql
CREATE TABLE tracks (
    video_id TEXT PRIMARY KEY,
    title TEXT,
    artist TEXT,
    stream_url TEXT,  -- NULL if unresolved
    updated_at INTEGER
);
```

### i3blocks Output Format

```
Line 1: Full text to display
Line 2: Short text (for minimal display)
Line 3: Color code (e.g., #FF6B35)
```

---

## Glossary

**MPD**: Music Player Daemon - the music player server
**i3blocks**: Status bar for i3 window manager
**ytmpd**: YouTube Music Player Daemon - this project
**Proxy URL**: YouTube stream proxied through ytmpd (format: `http://localhost:6602/proxy/{video_id}`)
**Track Type**: Classification of track - `youtube`, `local`, or `unknown`
**Sync Status**: Whether a YouTube track's stream URL has been resolved
**Idle Mode**: Efficient monitoring using MPD's idle command
**Polling Mode**: Periodic execution by i3blocks (less efficient)

---

## Future Enhancements

(Out of scope for current project, but valuable for future)

- [ ] Configuration file support (`~/.config/ytmpd/status.conf`)
- [ ] Support for other status bars (waybar, polybar)
- [ ] Album art display (requires image support in status bar)
- [ ] Volume control click handlers
- [ ] Playlist management click handlers (clear, shuffle, etc.)
- [ ] Desktop notifications on track change
- [ ] Lyrics display integration
- [ ] Themes/presets for common configurations
- [ ] GUI configuration tool

---

## References

- MPD Protocol: https://mpd.readthedocs.io/en/latest/protocol.html
- python-mpd2 Documentation: https://python-mpd2.readthedocs.io/
- i3blocks Documentation: https://github.com/vivien/i3blocks
- ytmpd Project: (this repository)

---

**Instructions for Agents**:
1. **First**: Run `pwd` and verify you're in `/home/tunc/Sync/Programs/ytmpd`
2. **Second**: Run `git branch` and verify you're on `feature/i3blocks-status`
3. **Third**: Activate environment: `source .venv/bin/activate`
4. Read ONLY your assigned phase section
5. Check the dependencies to understand what should already exist
6. Follow the detailed requirements exactly
7. Meet all completion criteria before marking phase complete
8. Create your summary in `summaries/PHASE_XX_SUMMARY.md`
9. Update `STATUS.md` when complete
10. Stage changes: `git add -A && git status`
11. **WAIT for user confirmation before committing**
12. Commit with clean message (no AI/Claude references)

**Remember**: All file paths in this plan are relative to `/home/tunc/Sync/Programs/ytmpd`

**Context Budget Note**: Each phase is designed to fit within ~30-45k tokens of reading plus implementation, leaving buffer for thinking and output. If a phase exceeds this, note it in your summary and suggest splitting.
