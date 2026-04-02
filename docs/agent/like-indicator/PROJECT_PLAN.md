# ytmpd - Like Indicator - Project Plan

**Feature/Initiative**: like-indicator
**Type**: New Feature
**Created**: 2026-04-02
**Estimated Total Phases**: 2

---

## Project Location

**IMPORTANT: All paths in this document are relative to the project root.**

- **Project Root**: `/home/tunc/Sync/Programs/ytmpd`
- **Verify with**: `pwd` -- should output `/home/tunc/Sync/Programs/ytmpd`

When you see a path like `ytmpd/config.py`, it means `/home/tunc/Sync/Programs/ytmpd/ytmpd/config.py`

---

## Project Overview

### Purpose

Add a visual like indicator to tracks in ncmpcpp playlists. When a track is in the user's YouTube Music "Liked Songs" collection, a configurable marker (e.g., `[+1]` or `[*]`) is shown in the track title. This uses zero extra API calls -- the liked songs data is already fetched during the regular sync cycle.

### Scope

**In Scope**:
- Configurable like indicator (enabled/disabled, custom tag string, left/right alignment)
- Like indicator applied to all playlists EXCEPT the "Liked Songs" playlist itself
- Support for both M3U and XSPF playlist formats
- Config validation for the new `like_indicator` section
- Unit tests for all new logic

**Out of Scope**:
- Dislike indicator (unreliable due to YouTube Music API limitation)
- Per-track API calls to check like status
- Real-time like status updates (indicator refreshes on sync cycle)
- Any changes to the rating/like/dislike toggle commands

### Success Criteria

- [ ] Like indicator appears in ncmpcpp for liked tracks across all non-"Liked Songs" playlists
- [ ] Indicator is configurable via config.yaml (tag string, alignment, enable/disable)
- [ ] Zero additional API calls -- piggybacks on existing liked songs fetch
- [ ] All existing tests continue to pass
- [ ] New unit tests cover config validation and title formatting

---

## Architecture Overview

### Key Components

1. **Config (config.py)**: New `like_indicator` section with `enabled`, `tag`, `alignment` fields
2. **SyncEngine (sync_engine.py)**: Builds a `set[str]` of liked video IDs during sync, passes it through to playlist generation
3. **MPDClient (mpd_client.py)**: Receives liked video ID set, modifies track titles when writing M3U/XSPF files
4. **Daemon (daemon.py)**: Wires new config values into SyncEngine constructor

### Data Flow

```
sync_all_playlists()
  |
  +-- get_liked_songs() --> extract video_ids --> liked_video_ids: set[str]
  |
  +-- for each playlist:
        |
        +-- _sync_single_playlist_internal(playlist, liked_video_ids)
              |
              +-- create_or_replace_playlist(..., liked_video_ids, like_indicator_config)
                    |
                    +-- if video_id in liked_video_ids AND not liked songs playlist:
                          modify title with [tag] (left or right)
```

### Technology Stack

- **Language**: Python 3.11+
- **Key Libraries**: ytmusicapi, python-mpd2, PyYAML
- **Testing**: pytest
- **Package Manager**: uv

---

## Phase Breakdown

> **Note for Agents**: Only read the section for your assigned phase. Reading all phases wastes context.

---

### Phase 1: Core Implementation

**Objective**: Implement the like indicator feature end-to-end: config, sync engine, playlist generation, and daemon wiring.

**Estimated Context Budget**: ~60k tokens

#### Deliverables

1. `ytmpd/config.py` -- Add `like_indicator` defaults and validation
2. `ytmpd/sync_engine.py` -- Build liked set, pass to playlist generation, skip indicator for liked songs playlist
3. `ytmpd/mpd_client.py` -- Apply like indicator to track titles in M3U and XSPF generation
4. `ytmpd/daemon.py` -- Wire `like_indicator` config into SyncEngine
5. `examples/config.yaml` -- Add documented `like_indicator` section

#### Detailed Requirements

**1. Config changes (`ytmpd/config.py`)**

Add to `default_config` dict (after `history_reporting`):

```python
"like_indicator": {
    "enabled": False,
    "tag": "+1",
    "alignment": "right",
},
```

Add deep-merge for `like_indicator` alongside `auto_auth` and `history_reporting` (line ~86-89):
```python
for key in ("auto_auth", "history_reporting", "like_indicator"):
```

Add validation in `_validate_config()`:
- `like_indicator` must be a dict
- `like_indicator.enabled` must be bool
- `like_indicator.tag` must be a non-empty string
- `like_indicator.alignment` must be `"left"` or `"right"`

**2. SyncEngine changes (`ytmpd/sync_engine.py`)**

Add `like_indicator` parameter to `__init__()`:
```python
like_indicator: dict | None = None,
```
Store as `self.like_indicator = like_indicator or {"enabled": False, "tag": "+1", "alignment": "right"}`.

In `sync_all_playlists()`:
- After fetching liked songs (line ~174), build the liked set:
  ```python
  liked_video_ids: set[str] = set()
  if self.like_indicator.get("enabled", False) and self.sync_liked_songs:
      # liked_tracks is already fetched above
      liked_video_ids = {t.video_id for t in liked_tracks} if liked_tracks else set()
  ```
- If `like_indicator` is enabled but `sync_liked_songs` is False, we still need to fetch liked songs just for the set. Add a separate fetch in that case:
  ```python
  elif self.like_indicator.get("enabled", False) and not self.sync_liked_songs:
      try:
          indicator_liked = self.ytmusic.get_liked_songs()
          liked_video_ids = {t.video_id for t in indicator_liked} if indicator_liked else set()
      except Exception as e:
          logger.warning(f"Failed to fetch liked songs for like indicator: {e}")
  ```
- Pass `liked_video_ids` and a boolean `is_liked_songs_playlist` to `_sync_single_playlist_internal()`.

In `_sync_single_playlist_internal()`:
- Add parameters: `liked_video_ids: set[str] | None = None`
- Determine if this is the liked songs playlist: `is_liked_playlist = (playlist.id == "__LIKED_SONGS__")`
- Pass `liked_video_ids`, `is_liked_playlist`, and `self.like_indicator` to `mpd.create_or_replace_playlist()`.

**3. MPDClient changes (`ytmpd/mpd_client.py`)**

Update `create_or_replace_playlist()` signature to accept:
```python
liked_video_ids: set[str] | None = None,
like_indicator: dict | None = None,
is_liked_playlist: bool = False,
```

Add a private helper method:
```python
def _apply_like_indicator(self, title: str, video_id: str, liked_video_ids: set[str] | None, like_indicator: dict | None, is_liked_playlist: bool) -> str:
    """Apply like indicator to track title if the track is liked.

    Returns the title with indicator prepended/appended, or unchanged title.
    """
    if not like_indicator or not like_indicator.get("enabled", False):
        return title
    if is_liked_playlist:
        return title
    if not liked_video_ids or video_id not in liked_video_ids:
        return title

    tag = like_indicator.get("tag", "+1")
    indicator = f"[{tag}]"
    alignment = like_indicator.get("alignment", "right")

    if alignment == "left":
        return f"{indicator} {title}"
    else:
        return f"{title} {indicator}"
```

In `_create_m3u_playlist()`: Apply indicator to the `artist_title` string (the combined "Artist - Title" in EXTINF).

In `_create_xspf_playlist()`: Apply indicator to `track.title` (the `<title>` element). This way the artist field stays clean and only the title shows the marker.

Pass the new parameters through from `create_or_replace_playlist()` to both `_create_m3u_playlist()` and `_create_xspf_playlist()`.

**4. Daemon wiring (`ytmpd/daemon.py`)**

In `YTMPDaemon.__init__()`, pass the new config to SyncEngine (around line 111-125):
```python
like_indicator=self.config.get("like_indicator", {"enabled": False, "tag": "+1", "alignment": "right"}),
```

**5. Example config (`examples/config.yaml`)**

Add a new section after history_reporting:
```yaml
# ===== Like Indicator Settings =====

# Show a visual indicator in playlist track titles for liked songs.
# The indicator is applied during sync to all playlists EXCEPT "Liked Songs"
# (since all tracks there are liked by definition).
# No extra API calls -- uses the already-fetched liked songs data.
like_indicator:
  # Enable like indicator in playlist titles
  # Default: false
  enabled: false

  # Tag string shown inside brackets, e.g., "+1" produces "[+1]", "*" produces "[*]"
  # Default: "+1"
  tag: "+1"

  # Where to place the indicator: "left" or "right" of the track title
  # Left example:  "[+1] Artist - Track Name" (M3U) or "[+1] Track Name" (XSPF title)
  # Right example: "Artist - Track Name [+1]" (M3U) or "Track Name [+1]" (XSPF title)
  # Default: "right"
  alignment: right
```

#### Dependencies

**Requires**: None (Phase 1 is the first phase)

**Enables**: Phase 2 (Testing)

#### Completion Criteria

- [ ] `like_indicator` config section added with defaults and validation
- [ ] SyncEngine builds liked video ID set during sync without extra API calls (when `sync_liked_songs` is true)
- [ ] SyncEngine fetches liked songs for indicator when `sync_liked_songs` is false but `like_indicator.enabled` is true
- [ ] Like indicator applied to track titles in M3U playlists
- [ ] Like indicator applied to track titles in XSPF playlists
- [ ] Like indicator NOT applied to the "Liked Songs" playlist
- [ ] Both left and right alignment work correctly
- [ ] Daemon passes `like_indicator` config to SyncEngine
- [ ] Example config updated with documented `like_indicator` section
- [ ] All existing tests still pass (`uv run pytest tests/ -v`)

#### Testing Requirements

- Run existing test suite to verify no regressions
- Manual verification that code is syntactically correct
- Detailed testing deferred to Phase 2

#### Notes

- The liked songs are already fetched in `sync_all_playlists()` at line 174. The liked_video_ids set should be built right after that fetch, reusing the same `liked_tracks` variable.
- Be careful with the variable scope: `liked_tracks` is only assigned inside the `if self.sync_liked_songs:` block. When `like_indicator.enabled` is True but `sync_liked_songs` is False, a separate fetch is needed.
- For XSPF, the indicator goes on the `<title>` element only, not `<creator>` (artist). This keeps the artist metadata clean.
- For M3U, the indicator goes on the combined `artist_title` string in EXTINF, so it appears as `Artist - Track Name [+1]` in ncmpcpp.

---

### Phase 2: Testing

**Objective**: Write comprehensive unit tests for all like indicator functionality.

**Estimated Context Budget**: ~50k tokens

#### Deliverables

1. `tests/test_like_indicator.py` -- New test file with all like indicator tests

#### Detailed Requirements

**Test file: `tests/test_like_indicator.py`**

Group tests into these categories:

**1. Config validation tests:**
- Test default config includes `like_indicator` with correct defaults
- Test `like_indicator.enabled` must be bool (reject int, string, etc.)
- Test `like_indicator.tag` must be non-empty string (reject empty string, int, None)
- Test `like_indicator.alignment` must be `"left"` or `"right"` (reject `"center"`, `"top"`, etc.)
- Test valid config passes validation (enabled=true, tag="*", alignment="left")
- Test deep-merge works: user partial config merges with defaults

**2. Title formatting tests (MPDClient._apply_like_indicator):**
- Test right alignment: `"Song Title"` + liked -> `"Song Title [+1]"`
- Test left alignment: `"Song Title"` + liked -> `"[+1] Song Title"`
- Test custom tag: tag="*" -> `"Song Title [*]"`
- Test custom tag: tag="LIKED" -> `"Song Title [LIKED]"`
- Test not liked: title unchanged
- Test liked but is_liked_playlist=True: title unchanged
- Test like_indicator disabled: title unchanged
- Test like_indicator=None: title unchanged
- Test empty liked_video_ids set: title unchanged

**3. M3U playlist generation with like indicator:**
- Test M3U output contains `[+1]` in EXTINF line for liked tracks
- Test M3U output does NOT contain indicator for non-liked tracks
- Test M3U with left alignment
- Test M3U with indicator disabled

**4. XSPF playlist generation with like indicator:**
- Test XSPF `<title>` contains indicator for liked tracks
- Test XSPF `<creator>` does NOT contain indicator (artist stays clean)
- Test XSPF with left alignment

**5. SyncEngine integration tests (with mocks):**
- Test that `sync_all_playlists()` passes liked_video_ids to playlist generation
- Test that liked songs playlist does NOT get indicators
- Test that when `sync_liked_songs=False` and `like_indicator.enabled=True`, liked songs are fetched separately
- Test that when `like_indicator.enabled=False`, no liked set is built

Follow existing test patterns in the project (see `tests/test_config.py`, `tests/test_mpd_client.py`, `tests/test_sync_engine.py` for mocking patterns and style).

#### Dependencies

**Requires**: Phase 1 (Core Implementation)

**Enables**: None (final phase)

#### Completion Criteria

- [ ] `tests/test_like_indicator.py` created with all test categories
- [ ] All config validation tests pass
- [ ] All title formatting tests pass
- [ ] All M3U generation tests pass
- [ ] All XSPF generation tests pass
- [ ] All SyncEngine integration tests pass
- [ ] Full test suite passes (`uv run pytest tests/ -v`)
- [ ] No test relies on external services (all mocked)

#### Testing Requirements

- All tests must be runnable with `uv run pytest tests/test_like_indicator.py -v`
- Use `unittest.mock` for mocking (consistent with existing tests)
- Each test should be independent (no shared mutable state)

#### Notes

- Read `tests/test_mpd_client.py` and `tests/test_sync_engine.py` first to understand existing mock patterns
- The `_apply_like_indicator` method should be testable directly (it's a pure function on the MPDClient instance)
- For M3U/XSPF tests, use `tmp_path` fixture to write to temporary directories
- For SyncEngine tests, mock `ytmusic.get_liked_songs()`, `ytmusic.get_user_playlists()`, `ytmusic.get_playlist_tracks()`, and `mpd.create_or_replace_playlist()`

---

## Phase Dependencies Graph

```
Phase 1 (Core Implementation)
    |
    v
Phase 2 (Testing)
```

---

## Cross-Cutting Concerns

### Code Style

- Follow existing project style (see ruff configuration)
- Use type hints for all function signatures
- Use docstrings for all public functions (Google style, matching existing code)

### Error Handling

- Like indicator failures should never break sync
- Log warnings for unexpected states, don't raise exceptions
- If liked songs fetch fails for indicator purposes, log and continue without indicators

### Configuration

- New config in `like_indicator` nested dict in `config.yaml`
- Deep-merged with defaults (same pattern as `auto_auth` and `history_reporting`)
- Validated in `_validate_config()`

### Testing Strategy

- Unit tests for all new logic
- Mock external dependencies (MPD, YouTube Music API)
- Run full existing test suite to verify no regressions

---

## Integration Points

### SyncEngine <-> MPDClient

- SyncEngine passes `liked_video_ids: set[str]`, `like_indicator: dict`, and `is_liked_playlist: bool` to `MPDClient.create_or_replace_playlist()`
- MPDClient applies the indicator during playlist file generation

### Config <-> Daemon <-> SyncEngine

- Config loads and validates `like_indicator` section
- Daemon reads config and passes `like_indicator` dict to SyncEngine constructor
- SyncEngine stores it and uses it during sync

### Liked Songs Fetch Reuse

- When `sync_liked_songs=True`: The liked songs are already fetched for playlist creation. The video IDs are extracted from the same `liked_tracks` list -- zero extra API calls.
- When `sync_liked_songs=False` but `like_indicator.enabled=True`: One `get_liked_songs()` call is made specifically for building the indicator set.

---

## Glossary

**Like Indicator**: A visual marker (e.g., `[+1]`) added to track titles in MPD playlists to show that the track is in the user's YouTube Music "Liked Songs" collection.
**Tag**: The string inside the brackets of the like indicator (e.g., `+1`, `*`, `LIKED`).
**Alignment**: Whether the indicator appears at the beginning (left) or end (right) of the track title.

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

**Context Budget Note**: Each phase is designed to fit within ~10-15k tokens of reading plus ~20-30k for implementation, leaving buffer for thinking and output. If a phase exceeds this, note it in your summary.
