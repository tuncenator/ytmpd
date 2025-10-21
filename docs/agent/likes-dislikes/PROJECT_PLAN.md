# ytmpd - Project Plan

**Feature/Initiative**: likes-dislikes (Bidirectional Like/Dislike Support)
**Type**: New Feature
**Created**: 2025-10-20
**Estimated Total Phases**: 6
**Git Branch**: `feature/likes-dislikes`

---

## 📍 Project Location

**IMPORTANT: All paths in this document are relative to the project root.**

- **Project Root**: `/home/tunc/Sync/Programs/ytmpd`
- **Verify with**: `pwd` → should output `/home/tunc/Sync/Programs/ytmpd`

When you see a path like `ytmpd/rating.py`, it means `/home/tunc/Sync/Programs/ytmpd/ytmpd/rating.py`

---

## 🔀 Git Workflow

**CRITICAL: Before starting any phase:**

```bash
# 1. Verify you're on the correct branch
git branch --show-current  # Should output: feature/likes-dislikes

# 2. If not on the branch, check it out
git checkout feature/likes-dislikes

# 3. Ensure you're up to date
git pull origin feature/likes-dislikes
```

**After completing each phase:**

```bash
# 1. Stage your changes
git add <files>

# 2. Commit with a clear, descriptive message
git commit -m "Your commit message here"

# 3. Verify commit was created
git log -1
```

**Commit Message Guidelines:**

- ✅ DO: Use clear, descriptive messages about what was implemented
- ✅ DO: Focus on the technical changes (e.g., "Add RatingManager with toggle logic")
- ❌ DON'T: Mention AI, Claude, or automated tools
- ❌ DON'T: Use generic messages like "Update files"

**Examples of good commit messages:**
```
Add ytmusicapi rating method research and documentation
Implement RatingManager with toggle state machine
Add like/dislike commands to ytmpctl CLI
Add end-to-end tests for rating workflow
Update documentation for like/dislike feature
```

---

## Project Overview

### Purpose

Enable users to like or dislike the currently playing YouTube Music track directly from their MPD workflow, creating a seamless bidirectional sync experience. This allows natural music curation while listening - the same way users interact with YouTube Music's web/mobile interface.

Currently, ytmpd only syncs from YouTube Music to MPD (one-way: YT→MPD). This feature adds the reverse direction: marking tracks as liked or disliked from the MPD playback environment updates the user's YouTube Music library (MPD→YT).

### Scope

**In Scope**:
- `ytmpctl like` command - Toggle like status for current track
- `ytmpctl dislike` command - Toggle dislike status for current track
- Toggle semantics (like → neutral → like, or dislike → like)
- Query current rating state from YouTube Music API
- Update rating via YouTube Music API (rate_song method)
- Immediate playlist refresh after liking (trigger `ytmpctl sync`)
- User feedback on action taken ("Liked ✓", "Removed like", "Disliked ✗", etc.)
- Error handling (no track playing, network issues, not a YouTube track)

**Out of Scope**:
- Batch operations (liking multiple tracks at once)
- Undo last rating change
- Status command showing rating (`ytmpctl status --show-rating`)
- Social features or sharing
- Analytics/reports on liked/disliked songs
- GUI or web interface

### Success Criteria

- [ ] User can toggle like/dislike for current track via single command
- [ ] Toggle behavior works correctly for all state transitions (9 cases)
- [ ] Changes reflect in YouTube Music web interface immediately
- [ ] i3 keybinding integration is smooth and responsive
- [ ] User feedback clearly indicates the action taken
- [ ] Appropriate error handling (no track playing, network issues, etc.)
- [ ] Test coverage for all toggle state transitions
- [ ] Immediate sync triggered after liking (so liked songs appear in MPD quickly)

---

## Architecture Overview

### Key Components

1. **Rating Manager** (`ytmpd/rating.py`): State machine implementing toggle logic
2. **YouTube Music API Wrapper** (`ytmpd/ytmusic.py` extensions): Methods to get/set ratings
3. **ytmpctl Commands** (`bin/ytmpctl`): CLI commands for like/dislike
4. **Current Track Detection**: Query MPD for currently playing track's video_id
5. **Sync Trigger**: Call `ytmpctl sync` after rating changes

### Data Flow

```
User presses keybinding
    ↓
ytmpctl like/dislike
    ↓
Get current track from MPD (video_id)
    ↓
Query current rating from YouTube Music API
    ↓
Apply toggle logic (state machine)
    ↓
Set new rating via YouTube Music API
    ↓
Trigger immediate sync (ytmpctl sync)
    ↓
User sees feedback ("Liked ✓")
```

### Technology Stack

- **Language**: Python 3.13+
- **Package Manager**: uv
- **Key Libraries**:
  - `ytmusicapi` (1.11.1) - YouTube Music API client
  - `python-mpd2` - MPD client library
  - `pytest` - Testing
- **Integration Points**:
  - Existing `YTMusicClient` class in `ytmpd/ytmusic.py`
  - Existing `MPDClient` class in `ytmpd/mpd_client.py`
  - Existing `ytmpctl` CLI in `bin/ytmpctl`

### Toggle Logic State Machine

Current rating state + user action → new rating state:

| Current State | User Action | New State  | API Call         |
|---------------|-------------|------------|------------------|
| NEUTRAL       | like        | LIKED      | LIKE             |
| NEUTRAL       | dislike     | DISLIKED   | DISLIKE          |
| LIKED         | like        | NEUTRAL    | INDIFFERENT      |
| LIKED         | dislike     | DISLIKED   | DISLIKE          |
| DISLIKED      | like        | LIKED      | LIKE             |
| DISLIKED      | dislike     | NEUTRAL    | INDIFFERENT      |

**Important API Caveat**: YouTube Music API may return ambiguous data where INDIFFERENT and DISLIKE are indistinguishable in some responses. Phase 1 will research the best approach to handle this.

---

## Phase Breakdown

> **Note for Agents**: Only read the section for your assigned phase. Reading all phases wastes context.

---

### Phase 1: API Research & Discovery

**Objective**: Experimentally verify ytmusicapi's rating methods and determine the best approach for getting/setting ratings reliably.

**Estimated Context Budget**: ~35k tokens

#### Deliverables

1. Research document summarizing ytmusicapi rating capabilities
2. Test script demonstrating get/set rating operations
3. Decision on approach for querying current rating state
4. Documentation of API limitations and edge cases

#### Detailed Requirements

**Research Tasks**:

1. **Verify `rate_song` method**:
   - Test with `LikeStatus.LIKE`, `LikeStatus.DISLIKE`, `LikeStatus.INDIFFERENT`
   - Confirm return values and behavior
   - Test error cases (invalid video_id, network failure, etc.)

2. **Find method to get current rating**:
   - Test `get_watch_playlist(videoId)` - returns track info with `likeStatus` field
   - Test `get_song(videoId)` - check if it includes rating info
   - Verify if `get_liked_songs()` can be used as fallback to check if song is liked
   - Document which method is most reliable

3. **Test ambiguity handling**:
   - Verify the claim that INDIFFERENT and DISLIKE may be ambiguous
   - Test with freshly disliked songs vs. never-rated songs
   - Determine if we can distinguish them reliably

4. **Rate limiting and retry logic**:
   - Check if existing `YTMusicClient._retry_on_failure` is sufficient
   - Test rate limiting behavior with multiple rapid rating changes

**Test Script**:

Create `tests/research/test_rating_api.py` (or similar) that:
- Authenticates with ytmusicapi using existing browser.json
- Tests rating a test track (choose a track you can safely rate/unrate)
- Retrieves the rating state using candidate methods
- Documents findings in comments

**Output**:

Create a research summary in your phase summary that includes:
- Which method to use for getting current rating (and why)
- How to handle INDIFFERENT vs DISLIKE ambiguity
- Any API limitations or edge cases discovered
- Recommended approach for implementation in Phase 2-3

#### Dependencies

**Requires**: None (this is Phase 1)

**Enables**:
- Phase 2: Rating Manager design depends on API capabilities
- Phase 3: YouTube Music API Integration uses research findings

#### Completion Criteria

- [ ] `rate_song` method tested and documented
- [ ] Method for getting current rating identified and tested
- [ ] INDIFFERENT vs DISLIKE ambiguity understood and documented
- [ ] Test script created with working examples
- [ ] Research summary written with clear recommendations
- [ ] Any API limitations or workarounds documented
- [ ] **Git: Changes committed to `feature/likes-dislikes` branch**

#### Git Commit Checklist

After completing this phase:
- [ ] `git add` all new/modified files
- [ ] `git commit -m "Add ytmusicapi rating method research and documentation"`
- [ ] Verify commit: `git log -1`

#### Testing Requirements

- Manual testing with real YouTube Music account
- Test script that demonstrates get/set rating operations
- Test edge cases: invalid video_id, network failure, auth failure

#### Notes

- Use the existing `YTMusicClient` in `ytmpd/ytmusic.py` for testing
- Don't modify production code yet - this is pure research
- If you discover the API is unreliable or missing features, document this clearly
- Consider testing with both browser.json and oauth.json authentication if available
- This phase is critical - take time to understand the API thoroughly

---

### Phase 2: Core Toggle Logic & Rating Manager

**Objective**: Design and implement the state machine for toggle logic with comprehensive test coverage.

**Estimated Context Budget**: ~45k tokens

#### Deliverables

1. `ytmpd/rating.py` - Rating manager module
2. `RatingManager` class with toggle state machine
3. `tests/test_rating.py` - Comprehensive unit tests (all 6 state transitions)
4. Enums and types for rating states

#### Detailed Requirements

**Create `ytmpd/rating.py`**:

```python
from enum import Enum
from dataclasses import dataclass

class RatingState(Enum):
    """Represents the current rating state of a track."""
    NEUTRAL = "INDIFFERENT"     # No rating / indifferent
    LIKED = "LIKE"              # Liked (thumbs up)
    DISLIKED = "DISLIKE"        # Disliked (thumbs down)

class RatingAction(Enum):
    """Represents the user action to perform."""
    LIKE = "like"
    DISLIKE = "dislike"

@dataclass
class RatingTransition:
    """Result of applying a rating action to a current state."""
    current_state: RatingState
    action: RatingAction
    new_state: RatingState
    api_value: str  # The LikeStatus value to send to API
    user_message: str  # Feedback message for user

class RatingManager:
    """Manages rating state transitions and toggle logic."""

    def apply_action(
        self,
        current_state: RatingState,
        action: RatingAction
    ) -> RatingTransition:
        """Apply toggle logic to determine new state.

        Args:
            current_state: Current rating state of the track.
            action: User action (like or dislike).

        Returns:
            RatingTransition with new state, API value, and user message.
        """
        # Implement state machine here
        pass

    def parse_api_rating(self, api_rating: str) -> RatingState:
        """Convert API rating string to RatingState enum.

        Args:
            api_rating: Rating from API ("LIKE", "DISLIKE", "INDIFFERENT")

        Returns:
            RatingState enum value.
        """
        pass
```

**State Machine Implementation**:

Implement all 6 transitions:

1. NEUTRAL + like → LIKED (API: LIKE, message: "✓ Liked")
2. NEUTRAL + dislike → DISLIKED (API: DISLIKE, message: "✗ Disliked")
3. LIKED + like → NEUTRAL (API: INDIFFERENT, message: "Removed like")
4. LIKED + dislike → DISLIKED (API: DISLIKE, message: "✗ Disliked")
5. DISLIKED + like → LIKED (API: LIKE, message: "✓ Liked")
6. DISLIKED + dislike → NEUTRAL (API: INDIFFERENT, message: "Removed dislike")

**Error Handling**:

- Handle unknown/invalid current states gracefully
- Provide clear error messages for invalid inputs
- Consider edge case: API returns ambiguous INDIFFERENT/DISLIKE (use Phase 1 findings)

**Type Safety**:

- Use type hints for all function signatures
- Use enums for rating states and actions (no string literals)
- Use dataclasses for structured return values

#### Dependencies

**Requires**:
- Phase 1: API research to understand how to handle INDIFFERENT/DISLIKE ambiguity

**Enables**:
- Phase 3: YouTube Music API Integration will use RatingManager
- Phase 4: ytmpctl commands will use RatingManager

#### Completion Criteria

- [ ] `ytmpd/rating.py` created with all classes/enums
- [ ] `RatingManager.apply_action()` implements all 6 state transitions correctly
- [ ] `RatingManager.parse_api_rating()` converts API strings to RatingState
- [ ] All code has type hints and docstrings
- [ ] `tests/test_rating.py` created with comprehensive tests
- [ ] All 6 state transitions tested individually
- [ ] Edge cases tested (invalid states, unknown API values)
- [ ] All tests pass (`pytest tests/test_rating.py -v`)
- [ ] **Git: Changes committed to `feature/likes-dislikes` branch**

#### Git Commit Checklist

After completing this phase:
- [ ] `git add ytmpd/rating.py tests/test_rating.py`
- [ ] `git commit -m "Implement RatingManager with toggle state machine and tests"`
- [ ] Verify commit: `git log -1`

#### Testing Requirements

**Unit Tests (`tests/test_rating.py`)**:

Test all state transitions:
```python
def test_neutral_like_becomes_liked():
    """NEUTRAL + like → LIKED"""
    manager = RatingManager()
    result = manager.apply_action(RatingState.NEUTRAL, RatingAction.LIKE)
    assert result.new_state == RatingState.LIKED
    assert result.api_value == "LIKE"
    assert "Liked" in result.user_message

def test_liked_like_becomes_neutral():
    """LIKED + like → NEUTRAL (toggle off)"""
    manager = RatingManager()
    result = manager.apply_action(RatingState.LIKED, RatingAction.LIKE)
    assert result.new_state == RatingState.NEUTRAL
    assert result.api_value == "INDIFFERENT"
    assert "Removed" in result.user_message

# ... (continue for all 6 transitions)
```

Test edge cases:
- Invalid API rating strings
- Unknown enum values
- None/null handling

**Coverage Goal**: 100% for `ytmpd/rating.py`

#### Notes

- This phase is pure logic - no API calls or MPD integration
- Keep it simple and testable
- User messages should be concise and clear (for CLI output)
- Consider using a lookup table/dictionary for state transitions if cleaner than if/else
- If Phase 1 discovered INDIFFERENT/DISLIKE ambiguity, document how RatingManager handles it
- Don't worry about actual ytmusicapi integration yet - that's Phase 3

---

### Phase 3: YouTube Music API Integration

**Objective**: Create wrapper methods in `YTMusicClient` for getting and setting track ratings, with error handling and retry logic.

**Estimated Context Budget**: ~40k tokens

#### Deliverables

1. Updated `ytmpd/ytmusic.py` with new methods:
   - `get_track_rating(video_id: str) -> RatingState`
   - `set_track_rating(video_id: str, rating: RatingState) -> None`
2. Integration with existing `YTMusicClient` class
3. Error handling for API failures
4. `tests/test_ytmusic_rating.py` - Integration tests with mocked API

#### Detailed Requirements

**Extend `ytmpd/ytmusic.py`**:

Add these methods to the existing `YTMusicClient` class:

```python
def get_track_rating(self, video_id: str) -> RatingState:
    """Get the current rating/like status of a track.

    Uses the method identified in Phase 1 (likely get_watch_playlist).

    Args:
        video_id: YouTube video ID.

    Returns:
        RatingState enum (NEUTRAL, LIKED, or DISLIKED).

    Raises:
        YTMusicAPIError: If retrieving rating fails.
        YTMusicNotFoundError: If track is not found.
    """
    if not self._client:
        raise YTMusicAuthError("Client not initialized")

    logger.info(f"Getting rating for video_id: {video_id}")
    self._rate_limit()

    def _get_rating() -> str:
        # Implementation based on Phase 1 findings
        # Example: use get_watch_playlist or get_song
        pass

    try:
        api_rating = self._retry_on_failure(_get_rating)
        rating_manager = RatingManager()
        return rating_manager.parse_api_rating(api_rating)
    except Exception as e:
        logger.error(f"Failed to get track rating: {e}")
        raise YTMusicAPIError(f"Failed to get track rating: {e}") from e


def set_track_rating(self, video_id: str, rating: RatingState) -> None:
    """Set the rating/like status of a track.

    Args:
        video_id: YouTube video ID.
        rating: New rating state (NEUTRAL, LIKED, or DISLIKED).

    Raises:
        YTMusicAPIError: If setting rating fails.
        YTMusicAuthError: If not authenticated.
    """
    if not self._client:
        raise YTMusicAuthError("Client not initialized")

    logger.info(f"Setting rating for {video_id} to {rating.value}")
    self._rate_limit()

    def _set_rating() -> None:
        from ytmusicapi.models.content.enums import LikeStatus

        # Map RatingState to LikeStatus
        like_status_map = {
            RatingState.NEUTRAL: LikeStatus.INDIFFERENT,
            RatingState.LIKED: LikeStatus.LIKE,
            RatingState.DISLIKED: LikeStatus.DISLIKE,
        }

        api_rating = like_status_map[rating]
        self._client.rate_song(videoId=video_id, rating=api_rating)

    try:
        self._retry_on_failure(_set_rating)
        logger.info(f"Successfully set rating to {rating.value}")
    except Exception as e:
        logger.error(f"Failed to set track rating: {e}")
        raise YTMusicAPIError(f"Failed to set track rating: {e}") from e
```

**Error Handling**:

- Reuse existing `_retry_on_failure` logic (exponential backoff)
- Reuse existing `_rate_limit` logic
- Handle specific errors:
  - Invalid video_id → `YTMusicNotFoundError`
  - Auth errors → `YTMusicAuthError`
  - Network/API errors → `YTMusicAPIError`
- Log all errors with truncated messages (use `_truncate_error`)

**Integration with RatingManager**:

- Import `RatingState` and `RatingManager` from `ytmpd.rating`
- Use `RatingManager.parse_api_rating()` in `get_track_rating()`
- Map `RatingState` to ytmusicapi's `LikeStatus` in `set_track_rating()`

**Implementation Based on Phase 1**:

- Use the method identified in Phase 1 for getting current rating
- If get_watch_playlist was chosen, implement accordingly
- If there are workarounds for INDIFFERENT/DISLIKE ambiguity, implement them
- Document any limitations in docstrings

#### Dependencies

**Requires**:
- Phase 1: API research findings
- Phase 2: RatingManager class

**Enables**:
- Phase 4: ytmpctl commands will call these methods

#### Completion Criteria

- [ ] `get_track_rating()` added to `YTMusicClient` class
- [ ] `set_track_rating()` added to `YTMusicClient` class
- [ ] Both methods use existing retry/rate-limit logic
- [ ] Proper error handling and logging
- [ ] Type hints and docstrings following project style
- [ ] `tests/test_ytmusic_rating.py` created with mocked API tests
- [ ] Tests cover success cases and error cases
- [ ] All tests pass (`pytest tests/test_ytmusic_rating.py -v`)
- [ ] Integration with RatingManager works correctly
- [ ] **Git: Changes committed to `feature/likes-dislikes` branch**

#### Git Commit Checklist

After completing this phase:
- [ ] `git add ytmpd/ytmusic.py tests/test_ytmusic_rating.py`
- [ ] `git commit -m "Add YouTube Music API rating methods with error handling"`
- [ ] Verify commit: `git log -1`

#### Testing Requirements

**Integration Tests with Mocked API** (`tests/test_ytmusic_rating.py`):

```python
from unittest.mock import Mock, patch
import pytest
from ytmpd.ytmusic import YTMusicClient
from ytmpd.rating import RatingState
from ytmpd.exceptions import YTMusicAPIError, YTMusicNotFoundError


class TestRatingIntegration:
    """Tests for rating methods with mocked ytmusicapi."""

    def test_get_track_rating_liked(self, mock_ytmusic_client):
        """Test getting rating for a liked track."""
        # Mock API response with LIKE status
        # Assert get_track_rating returns RatingState.LIKED
        pass

    def test_get_track_rating_disliked(self, mock_ytmusic_client):
        """Test getting rating for a disliked track."""
        pass

    def test_get_track_rating_neutral(self, mock_ytmusic_client):
        """Test getting rating for a neutral/unrated track."""
        pass

    def test_set_track_rating_like(self, mock_ytmusic_client):
        """Test setting track rating to LIKE."""
        # Mock ytmusicapi.rate_song
        # Call set_track_rating with RatingState.LIKED
        # Assert rate_song called with LikeStatus.LIKE
        pass

    def test_set_track_rating_dislike(self, mock_ytmusic_client):
        """Test setting track rating to DISLIKE."""
        pass

    def test_set_track_rating_neutral(self, mock_ytmusic_client):
        """Test setting track rating to INDIFFERENT."""
        pass

    def test_get_rating_not_found(self, mock_ytmusic_client):
        """Test error handling when track not found."""
        # Mock API to raise error
        # Assert YTMusicNotFoundError raised
        pass

    def test_set_rating_api_error(self, mock_ytmusic_client):
        """Test error handling when API fails."""
        pass
```

**Fixtures**:
- `mock_ytmusic_client`: Fixture that creates YTMusicClient with mocked ytmusicapi

**Coverage Goal**: 90%+ for new methods

#### Notes

- Reuse existing `YTMusicClient` patterns (retry, rate limit, logging)
- Don't modify existing methods unless necessary
- Follow existing code style in `ytmpd/ytmusic.py`
- Use truncated error logging (`_truncate_error`) for consistency
- If Phase 1 found API limitations, document them in method docstrings
- Test with both mocked API and manual testing if possible

---

### Phase 4: ytmpctl Command Implementation

**Objective**: Add `like` and `dislike` commands to ytmpctl CLI, integrate with MPD for current track detection, implement rating logic, and trigger immediate sync.

**Estimated Context Budget**: ~45k tokens

#### Deliverables

1. Updated `bin/ytmpctl` with new commands:
   - `ytmpctl like` - Toggle like for current track
   - `ytmpctl dislike` - Toggle dislike for current track
2. Current track detection from MPD
3. Integration with `YTMusicClient` and `RatingManager`
4. Immediate sync trigger after rating change
5. User feedback messages
6. Error handling (no track, not YouTube track, etc.)
7. Updated help text

#### Detailed Requirements

**Add Commands to `bin/ytmpctl`**:

The current structure of `bin/ytmpctl` is a bash script that routes commands. You'll need to:

1. Add `like` and `dislike` to the command routing
2. Create Python handlers for these commands

**Implementation Approach**:

Based on existing ytmpctl structure, you may need to:
- Add like/dislike handlers to the main ytmpctl script
- Or create new Python module (e.g., `ytmpd/cli/rating.py`)

Check how existing commands like `status`, `sync`, `radio` are implemented and follow the same pattern.

**Like Command Flow**:

```python
def handle_like():
    """Handle ytmpctl like command."""
    try:
        # 1. Get current track from MPD
        video_id, title, artist = get_current_track_from_mpd()

        # 2. Initialize clients
        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        # 3. Get current rating
        current_rating = ytmusic.get_track_rating(video_id)

        # 4. Apply toggle logic
        transition = rating_mgr.apply_action(current_rating, RatingAction.LIKE)

        # 5. Set new rating
        ytmusic.set_track_rating(video_id, transition.new_state)

        # 6. Trigger immediate sync (if liked)
        if transition.new_state == RatingState.LIKED:
            trigger_sync()

        # 7. Show user feedback
        print(f"{transition.user_message}: {artist} - {title}")

    except NoTrackPlayingError:
        print("Error: No track currently playing", file=sys.stderr)
        sys.exit(1)
    except NotYouTubeTrackError:
        print("Error: Current track is not a YouTube Music track", file=sys.stderr)
        sys.exit(1)
    except YTMusicAPIError as e:
        print(f"Error: Failed to update rating - {e}", file=sys.stderr)
        sys.exit(1)
```

**Dislike Command Flow**: Same as like, but with `RatingAction.DISLIKE`

**Current Track Detection**:

```python
def get_current_track_from_mpd() -> tuple[str, str, str]:
    """Get currently playing track from MPD.

    Returns:
        Tuple of (video_id, title, artist).

    Raises:
        NoTrackPlayingError: If no track is playing.
        NotYouTubeTrackError: If track is not from YouTube Music.
    """
    # Use existing MPDClient or mpc command
    # Extract video_id from file path (format: http://localhost:6602/proxy/{video_id})
    # Parse title and artist from MPD metadata
    pass
```

**Sync Trigger**:

```python
def trigger_sync():
    """Trigger immediate playlist sync after rating change."""
    # Call: bin/ytmpctl sync
    # Or use subprocess.run(["bin/ytmpctl", "sync"])
    # Or import and call the sync function directly
    pass
```

**Error Handling**:

Define custom exceptions if needed:
```python
class NoTrackPlayingError(Exception):
    """No track is currently playing."""
    pass

class NotYouTubeTrackError(Exception):
    """Current track is not from YouTube Music."""
    pass
```

Handle errors gracefully:
- No track playing → Clear error message
- Not a YouTube track → Clear error message (file doesn't match proxy URL format)
- Network/API errors → Show error and suggest retry
- Auth errors → Suggest re-running setup

**Updated Help Text**:

Update `ytmpctl help` output to include:

```
Playback Control:
  ytmpctl like              Toggle like for current track
  ytmpctl dislike           Toggle dislike for current track

  Use mpc for playback control of synced playlists:
    mpc load "YT: Favorites"    Load YouTube playlist in MPD
    ...
```

**User Feedback Format**:

```
✓ Liked: Miles Davis - So What
Removed like: John Coltrane - Giant Steps
✗ Disliked: Artist - Title
Removed dislike: Artist - Title
```

#### Dependencies

**Requires**:
- Phase 2: RatingManager
- Phase 3: YTMusicClient rating methods

**Enables**:
- Phase 5: End-to-end testing will test these commands

#### Completion Criteria

- [ ] `ytmpctl like` command implemented and working
- [ ] `ytmpctl dislike` command implemented and working
- [ ] Current track detection from MPD works correctly
- [ ] Rating logic integrated (RatingManager + YTMusicClient)
- [ ] Immediate sync triggered after liking a song
- [ ] User feedback messages displayed correctly
- [ ] Error handling for all error cases
- [ ] Help text updated
- [ ] Manual testing shows commands work end-to-end
- [ ] Code follows project style (type hints, docstrings, logging)
- [ ] **Git: Changes committed to `feature/likes-dislikes` branch**

#### Git Commit Checklist

After completing this phase:
- [ ] `git add bin/ytmpctl` (and any new Python modules)
- [ ] `git commit -m "Add like/dislike commands to ytmpctl CLI"`
- [ ] Verify commit: `git log -1`

#### Testing Requirements

**Manual Testing**:

1. Start MPD and play a YouTube Music track
2. Run `ytmpctl like` → Verify:
   - Song is liked on YouTube Music (check web interface)
   - Feedback message shows "✓ Liked: Artist - Title"
   - Sync is triggered
   - On next sync or immediate sync, "Liked Songs" playlist updates
3. Run `ytmpctl like` again → Verify:
   - Like is removed
   - Feedback shows "Removed like: ..."
4. Run `ytmpctl dislike` → Verify similar behavior
5. Test error cases:
   - No track playing → Clear error message
   - Not a YouTube track (play local file) → Clear error message

**Integration Tests** (optional for this phase, required in Phase 5):

- Can be deferred to Phase 5 for comprehensive end-to-end tests

**Test Checklist**:

- [ ] Like neutral track → becomes liked
- [ ] Like liked track → becomes neutral
- [ ] Dislike neutral track → becomes disliked
- [ ] Dislike disliked track → becomes neutral
- [ ] Like disliked track → becomes liked
- [ ] Dislike liked track → becomes disliked
- [ ] No track playing → error
- [ ] Non-YouTube track → error
- [ ] Network failure → error shown

#### Notes

- Follow existing ytmpctl patterns and code style
- Reuse existing MPD client if available, or use `mpc` command
- Sync trigger should be non-blocking (async/background) if possible
- User feedback should be immediate (don't wait for sync to complete)
- Log all rating changes for debugging
- Consider rate limiting if user spams like/dislike commands
- Video ID extraction: MPD file format is `http://localhost:6602/proxy/{video_id}`
- Test with both browser.json and oauth.json auth if applicable
- Document any assumptions about MPD state or track format

---

### Phase 5: End-to-End Testing & Validation

**Objective**: Create comprehensive end-to-end integration tests, verify all toggle state transitions work in real scenarios, and validate sync behavior.

**Estimated Context Budget**: ~40k tokens

#### Deliverables

1. `tests/integration/test_rating_workflow.py` - E2E integration tests
2. Test fixtures for MPD and YouTube Music mocking
3. Validation of all 6 state transitions in realistic scenarios
4. Error path testing
5. Sync trigger validation
6. Test report documenting all test cases

#### Detailed Requirements

**End-to-End Integration Tests** (`tests/integration/test_rating_workflow.py`):

Create integration tests that simulate the full user workflow:

```python
import pytest
from unittest.mock import Mock, patch
from ytmpd.ytmusic import YTMusicClient
from ytmpd.rating import RatingManager, RatingState, RatingAction
from ytmpd.exceptions import YTMusicAPIError


class TestLikeDislikeWorkflow:
    """End-to-end tests for like/dislike workflow."""

    def test_like_neutral_track_full_flow(self, mock_mpd, mock_ytmusic):
        """Test liking a neutral track through ytmpctl."""
        # Setup: MPD playing a track, track is neutral on YTM
        # Execute: ytmpctl like
        # Verify:
        #   - get_track_rating called
        #   - RatingManager.apply_action called with NEUTRAL, LIKE
        #   - set_track_rating called with LIKED
        #   - Sync triggered
        #   - User sees "✓ Liked: Artist - Title"
        pass

    def test_like_liked_track_removes_like(self, mock_mpd, mock_ytmusic):
        """Test toggling off a like."""
        # Setup: Track is already liked
        # Execute: ytmpctl like
        # Verify: Rating set to NEUTRAL, message shows "Removed like"
        pass

    def test_dislike_neutral_track(self, mock_mpd, mock_ytmusic):
        """Test disliking a neutral track."""
        pass

    def test_like_disliked_track_switches_to_like(self, mock_mpd, mock_ytmusic):
        """Test switching from dislike to like."""
        pass

    def test_dislike_liked_track_switches_to_dislike(self, mock_mpd, mock_ytmusic):
        """Test switching from like to dislike."""
        pass

    def test_dislike_disliked_track_removes_dislike(self, mock_mpd, mock_ytmusic):
        """Test toggling off a dislike."""
        pass

    def test_no_track_playing_error(self, mock_mpd):
        """Test error handling when no track is playing."""
        # Setup: MPD not playing anything
        # Execute: ytmpctl like
        # Verify: Error message shown, exit code 1
        pass

    def test_non_youtube_track_error(self, mock_mpd):
        """Test error handling for non-YouTube tracks."""
        # Setup: MPD playing local file (not YouTube proxy URL)
        # Execute: ytmpctl like
        # Verify: Error message shown
        pass

    def test_api_error_handling(self, mock_mpd, mock_ytmusic):
        """Test handling of YouTube Music API errors."""
        # Setup: Mock API to raise YTMusicAPIError
        # Execute: ytmpctl like
        # Verify: Error message shown, no crash
        pass

    def test_sync_triggered_after_like(self, mock_mpd, mock_ytmusic, mock_sync):
        """Test that sync is triggered after liking a song."""
        # Execute: ytmpctl like (neutral → liked)
        # Verify: sync function called
        pass

    def test_sync_not_triggered_after_removing_like(self, mock_mpd, mock_ytmusic, mock_sync):
        """Test that sync may not be triggered when removing like (optional behavior)."""
        # This depends on implementation - decide if sync should happen on all changes
        pass
```

**Test Fixtures**:

```python
@pytest.fixture
def mock_mpd():
    """Mock MPD client with currently playing track."""
    with patch('ytmpd.mpd_client.MPDClient') as mock:
        # Mock current track: video_id, title, artist
        yield mock

@pytest.fixture
def mock_ytmusic():
    """Mock YouTube Music client."""
    with patch('ytmpd.ytmusic.YTMusicClient') as mock:
        # Mock get_track_rating and set_track_rating
        yield mock

@pytest.fixture
def mock_sync():
    """Mock sync trigger."""
    with patch('ytmpd.cli.trigger_sync') as mock:
        yield mock
```

**Error Path Testing**:

Test all error scenarios:
1. No track playing
2. Non-YouTube track (local file, radio stream)
3. Network failure during get_track_rating
4. Network failure during set_track_rating
5. Auth failure (expired credentials)
6. Invalid video_id (track not found on YouTube Music)
7. Sync trigger failure

**Validation Checklist**:

Test all 6 state transitions:
- [ ] NEUTRAL + like → LIKED
- [ ] NEUTRAL + dislike → DISLIKED
- [ ] LIKED + like → NEUTRAL
- [ ] LIKED + dislike → DISLIKED
- [ ] DISLIKED + like → LIKED
- [ ] DISLIKED + dislike → NEUTRAL

Test error handling:
- [ ] No track playing
- [ ] Non-YouTube track
- [ ] API errors (get_track_rating)
- [ ] API errors (set_track_rating)
- [ ] Auth errors
- [ ] Sync trigger failure

**Manual Testing Checklist**:

Perform manual tests with real YouTube Music and MPD:
1. [ ] Like a neutral song → Verify on YTM web interface
2. [ ] Unlike (toggle off) → Verify on YTM web interface
3. [ ] Dislike a neutral song → Verify on YTM web interface
4. [ ] Remove dislike → Verify on YTM web interface
5. [ ] Like a disliked song → Verify transition
6. [ ] Dislike a liked song → Verify transition
7. [ ] Verify sync triggers and liked songs appear in MPD
8. [ ] Test i3 keybinding integration (if applicable)

**Test Report**:

Document test results in your phase summary:
- All automated tests passed
- Manual test results
- Any issues discovered
- Performance notes (latency, API response times)
- Edge cases or limitations found

#### Dependencies

**Requires**:
- Phase 4: ytmpctl commands implemented

**Enables**:
- Phase 6: Documentation can reference validated behavior

#### Completion Criteria

- [ ] `tests/integration/test_rating_workflow.py` created
- [ ] All 6 state transition tests pass
- [ ] All error path tests pass
- [ ] Sync trigger test passes
- [ ] Manual testing completed for all scenarios
- [ ] Test report documented in phase summary
- [ ] All automated tests pass (`pytest tests/integration/test_rating_workflow.py -v`)
- [ ] Code coverage for rating features is >85%
- [ ] **Git: Changes committed to `feature/likes-dislikes` branch**

#### Git Commit Checklist

After completing this phase:
- [ ] `git add tests/integration/test_rating_workflow.py`
- [ ] `git commit -m "Add end-to-end tests for like/dislike workflow"`
- [ ] Verify commit: `git log -1`

#### Testing Requirements

**Automated Tests**:
- 6 tests for state transitions
- 7 tests for error paths
- 2 tests for sync trigger behavior
- Total: ~15 integration tests

**Manual Tests**:
- 8 manual test scenarios with real YTM and MPD
- Verify changes on YouTube Music web interface
- Test keybinding integration if applicable

**Coverage**:
- Run coverage report: `pytest --cov=ytmpd --cov-report=html`
- Ensure rating.py, ytmusic.py (rating methods), and ytmpctl commands are covered

#### Notes

- This is the quality gate - don't proceed to Phase 6 if critical tests fail
- Document any bugs found and fix them before marking phase complete
- If you find edge cases not covered by earlier phases, document them
- Consider performance: measure latency from command to YTM update
- Test with both browser.json and oauth.json if applicable
- Verify that immediate sync actually updates the MPD playlist
- If any limitations are found, document them for Phase 6 (documentation)

---

### Phase 6: Documentation & Polish

**Objective**: Update all project documentation, add usage examples, update help text, create user guide, and prepare changelog entry.

**Estimated Context Budget**: ~30k tokens

#### Deliverables

1. Updated `README.md` with like/dislike feature documentation
2. User guide for like/dislike workflow
3. Updated `--help` text in ytmpctl
4. Changelog entry
5. Code comments and docstrings review
6. Example keybinding configurations (i3wm, sway, etc.)
7. Troubleshooting guide

#### Detailed Requirements

**Update `README.md`**:

Add section documenting the like/dislike feature:

```markdown
## Liking and Disliking Tracks

ytmpd supports bidirectional sync - you can like or dislike tracks from your MPD playback environment, and changes will sync to YouTube Music.

### Commands

ytmpctl like              Toggle like for currently playing track
ytmpctl dislike           Toggle dislike for currently playing track


### Toggle Behavior

Both commands use toggle logic:

**Like command:**
- Neutral song → like → Liked ✓
- Liked song → like → Neutral (removed from liked songs)
- Disliked song → like → Liked ✓

**Dislike command:**
- Neutral song → dislike → Disliked ✗
- Disliked song → dislike → Neutral (dislike removed)
- Liked song → dislike → Disliked ✗

### Keybinding Example (i3wm)

Add to your `~/.config/i3/config`:

bindsym $mod+plus exec ytmpctl like
bindsym $mod+minus exec ytmpctl dislike


### Sync Behavior

When you like a song, ytmpd immediately triggers a sync to update your playlists. The liked song will appear in your "Liked Songs" playlist in MPD.

### Requirements

- MPD must be playing a YouTube Music track (synced via ytmpd)
- YouTube Music authentication must be configured

### Error Messages

- "Error: No track currently playing" - Start playback first
- "Error: Current track is not a YouTube Music track" - Only works with synced YouTube tracks
- "Error: Failed to update rating" - Check network connection and authentication
```

**User Guide** (`docs/user/like-dislike-guide.md` or add to existing docs):

Create a comprehensive user guide:
- Overview of the feature
- Step-by-step setup (authentication, MPD setup)
- Usage examples
- Keybinding setup for various window managers (i3, sway, awesome, etc.)
- Troubleshooting common issues
- FAQ

**Updated Help Text** (`bin/ytmpctl help`):

Ensure help text is clear and includes:
- Command syntax
- Brief description of toggle behavior
- Examples
- Link to documentation

**Changelog Entry**:

Create entry for next version (format depends on existing changelog format):

```markdown
## [Unreleased]

### Added
- Bidirectional like/dislike support for YouTube Music tracks
  - `ytmpctl like` - Toggle like status for current track
  - `ytmpctl dislike` - Toggle dislike status for current track
  - Immediate sync trigger after liking songs
  - Toggle semantics: pressing same command twice reverts action
  - Support for all rating state transitions (like, dislike, neutral)

### Changed
- Extended `YTMusicClient` with rating methods (`get_track_rating`, `set_track_rating`)

### Technical
- New module: `ytmpd/rating.py` - Rating state machine and toggle logic
- New integration tests for rating workflow
- Comprehensive error handling for rating operations
```

**Code Review**:

Review all code from Phases 1-5:
- Ensure all public functions have docstrings
- Verify type hints are complete and correct
- Check for TODO comments and address them
- Ensure logging is consistent
- Verify error messages are user-friendly
- Check for any hardcoded values that should be configurable

**Example Configurations**:

Provide keybinding examples for popular window managers:

**i3wm:**
```
bindsym $mod+plus exec ytmpctl like
bindsym $mod+minus exec ytmpctl dislike
```

**Sway:**
```
bindsym $mod+plus exec ytmpctl like
bindsym $mod+minus exec ytmpctl dislike
```

**Awesome WM:**
```lua
awful.key({ modkey }, "=", function() awful.spawn("ytmpctl like") end),
awful.key({ modkey }, "-", function() awful.spawn("ytmpctl dislike") end),
```

**Troubleshooting Guide**:

Common issues and solutions:
1. **"No track currently playing"**
   - Solution: Start MPD playback first (`mpc play`)

2. **"Not a YouTube Music track"**
   - Solution: Load a synced YouTube playlist (`mpc load "YT: Favorites"`)

3. **"Failed to update rating"**
   - Check authentication: `ls ~/.config/ytmpd/browser.json`
   - Re-authenticate if needed: `python -m ytmpd.ytmusic setup-browser`
   - Check network connection

4. **Liked song doesn't appear in playlist**
   - Trigger manual sync: `ytmpctl sync`
   - Check sync status: `ytmpctl status`
   - Verify "Liked Songs" playlist exists on YouTube Music

5. **Rate limiting errors**
   - Don't spam like/dislike commands too quickly
   - Wait a few seconds between rating changes

#### Dependencies

**Requires**:
- Phase 5: Testing validated that everything works

**Enables**:
- Feature is complete and ready for users

#### Completion Criteria

- [ ] `README.md` updated with like/dislike documentation
- [ ] User guide created (or added to existing docs)
- [ ] `ytmpctl help` text updated
- [ ] Changelog entry created
- [ ] All code has proper docstrings and type hints
- [ ] Keybinding examples provided for multiple window managers
- [ ] Troubleshooting guide created
- [ ] All documentation is clear and user-friendly
- [ ] Code reviewed and polished
- [ ] No TODO comments left unaddressed
- [ ] **Git: Changes committed to `feature/likes-dislikes` branch**

#### Git Commit Checklist

After completing this phase:
- [ ] `git add README.md CHANGELOG.md bin/ytmpctl` (and any docs)
- [ ] `git commit -m "Update documentation for like/dislike feature"`
- [ ] Verify commit: `git log -1`

#### Testing Requirements

**Documentation Testing**:
- [ ] Follow your own user guide and verify instructions work
- [ ] Test keybinding examples on at least one window manager
- [ ] Verify all links in documentation are valid
- [ ] Ensure code examples in docs are accurate

**User Acceptance**:
- [ ] Feature is usable without reading source code
- [ ] Error messages are helpful
- [ ] Help text is clear
- [ ] Setup process is documented

#### Notes

- This phase is about user experience - make it easy to use
- Assume users are not developers - explain clearly
- Include screenshots or examples where helpful
- Ensure consistency with existing documentation style
- Proofread all documentation for clarity and correctness
- Consider adding a demo/example video or GIF if applicable

---

## Cross-Cutting Concerns

### Code Style

- Follow PEP 8 for Python code
- Use type hints for all function signatures
- Maximum line length: 100 characters (matching existing ytmpd style)
- Use docstrings for all public functions (Google style)
- Use enums instead of string literals for states/actions
- Use dataclasses for structured data

### Error Handling

- Use custom exceptions from `ytmpd.exceptions`
- Log all errors before raising
- Provide user-friendly error messages
- Don't expose internal implementation details in error messages
- Use existing error handling patterns from ytmpd codebase

### Logging

- Use Python's `logging` module (already configured in ytmpd)
- Log levels:
  - INFO: Rating changes, API calls
  - WARNING: Retries, recoverable errors
  - ERROR: Failed operations
  - DEBUG: State transitions, detailed flow
- Log format: Follow existing ytmpd format
- Truncate long error messages using `_truncate_error`

### Configuration

- No new configuration needed for this feature
- Use existing ytmpd config system
- Reuse existing auth files (browser.json / oauth.json)

### Testing Strategy

- Unit tests for RatingManager (Phase 2)
- Integration tests with mocked API (Phase 3)
- End-to-end workflow tests (Phase 5)
- Manual testing with real YouTube Music
- Minimum 85% code coverage for new code
- Use pytest with fixtures for common setups

---

## Integration Points

### RatingManager ↔ YTMusicClient

**How they work together:**
- YTMusicClient calls `RatingManager.parse_api_rating()` to convert API strings to enums
- YTMusicClient uses `RatingState` enums for method signatures
- RatingManager provides the toggle logic, YTMusicClient provides the API access

**Data flow:**
```
API (string) → YTMusicClient.get_track_rating() → RatingState (enum)
RatingState + Action → RatingManager.apply_action() → RatingTransition
RatingTransition.new_state → YTMusicClient.set_track_rating() → API (LikeStatus)
```

### ytmpctl ↔ MPD

**Current track detection:**
- ytmpctl queries MPD for currently playing track
- Extracts video_id from MPD file path: `http://localhost:6602/proxy/{video_id}`
- Gets artist and title from MPD metadata

### ytmpctl ↔ Sync

**Immediate sync trigger:**
- After liking a song, ytmpctl triggers sync
- Can be implemented as:
  - `subprocess.run(["bin/ytmpctl", "sync"])`
  - Or direct function call to sync logic
  - Should be non-blocking (don't wait for sync to complete)

---

## Data Schemas

### RatingState Enum

```python
class RatingState(Enum):
    NEUTRAL = "INDIFFERENT"     # No rating / indifferent
    LIKED = "LIKE"              # Liked (thumbs up)
    DISLIKED = "DISLIKE"        # Disliked (thumbs down)
```

### RatingAction Enum

```python
class RatingAction(Enum):
    LIKE = "like"
    DISLIKE = "dislike"
```

### RatingTransition Dataclass

```python
@dataclass
class RatingTransition:
    current_state: RatingState
    action: RatingAction
    new_state: RatingState
    api_value: str              # "LIKE", "DISLIKE", "INDIFFERENT"
    user_message: str           # "✓ Liked", "Removed like", etc.
```

### YouTube Music API

**rate_song method:**
```python
ytmusicapi.rate_song(
    videoId: str,
    rating: LikeStatus  # LikeStatus.LIKE, DISLIKE, or INDIFFERENT
) -> dict | None
```

**get_watch_playlist response** (excerpt):
```json
{
  "tracks": [
    {
      "videoId": "dQw4w9WgXcQ",
      "title": "Song Title",
      "artists": [{"name": "Artist Name"}],
      "likeStatus": "LIKE"  // or "DISLIKE" or "INDIFFERENT"
    }
  ]
}
```

---

## Glossary

**INDIFFERENT**: YouTube Music API term for "no rating" or "neutral" state
**LikeStatus**: ytmusicapi enum for rating values (LIKE, DISLIKE, INDIFFERENT)
**MPD**: Music Player Daemon
**ytmpd**: YouTube Music to MPD sync daemon
**ytmpctl**: CLI control tool for ytmpd
**Toggle Logic**: Pressing same command twice reverts the action
**Bidirectional Sync**: Changes flow both YT→MPD and MPD→YT

---

## Future Enhancements

Features not in current scope but potentially valuable later:

- [ ] `ytmpctl status --show-rating` - Show current track's rating in status output
- [ ] Batch operations: Like multiple tracks from a playlist
- [ ] Undo last rating change
- [ ] Rating history / audit log
- [ ] Desktop notifications for rating changes
- [ ] Integration with other music services (Spotify, etc.)
- [ ] Auto-dislike songs from certain artists (block list)

---

## References

- [ytmusicapi Documentation](https://ytmusicapi.readthedocs.io/)
- [ytmusicapi GitHub](https://github.com/sigma67/ytmusicapi)
- [ytmpd Project Documentation](../../README.md)
- [MPD Protocol](https://www.musicpd.org/doc/protocol/)

---

**Instructions for Agents**:
1. **First**: Run `pwd` and verify you're in `/home/tunc/Sync/Programs/ytmpd`
2. **Second**: Run `git branch --show-current` and verify you're on `feature/likes-dislikes`
3. Read ONLY your assigned phase section
4. Check the dependencies to understand what should already exist
5. Follow the detailed requirements exactly
6. Meet all completion criteria before marking phase complete
7. **Commit your changes** after completing the phase (see Git Commit Checklist)
8. Create your summary in `docs/agent/likes-dislikes/summaries/PHASE_XX_SUMMARY.md`
9. Update `STATUS.md` when complete

**Remember**: All file paths in this plan are relative to `/home/tunc/Sync/Programs/ytmpd`

**Context Budget Note**: Each phase is designed to fit within ~120k tokens total. If a phase exceeds this, note it in your summary and suggest splitting it.
