# ytmpd Auto-Auth - Project Plan

**Feature/Initiative**: auto-auth
**Type**: New Feature
**Created**: 2026-03-30
**Estimated Total Phases**: 4

---

## Project Location

**IMPORTANT: All paths in this document are relative to the project root.**

- **Project Root**: `/home/tunc/Sync/Programs/ytmpd`
- **Verify with**: `pwd` -> should output `/home/tunc/Sync/Programs/ytmpd`

When you see a path like `ytmpd/cookie_extract.py`, it means `/home/tunc/Sync/Programs/ytmpd/ytmpd/cookie_extract.py`

---

## Project Overview

### Purpose

Automate YouTube Music authentication for ytmpd by extracting cookies directly from the user's Firefox browser. Currently, when browser.json credentials expire (every few days), users must manually open DevTools, copy request headers, and paste them into `ytmpctl auth`. This feature eliminates that manual step entirely by reading cookies from Firefox's SQLite database and rebuilding browser.json automatically.

### Scope

**In Scope**:
- Firefox cookie extraction (standard and Developer Edition)
- Firefox Multi-Account Container support (filter by container or no-container)
- Firefox profile auto-detection and manual override
- Automatic browser.json generation from extracted cookies
- Proactive periodic cookie refresh in the daemon (configurable interval)
- Reactive refresh on auth failure
- Desktop notification via `notify-send` when auto-refresh fails
- i3blocks widget auth status color indicator
- `ytmpctl auth --auto` command for manual trigger
- Configuration options in config.yaml
- Unit and integration tests

**Out of Scope**:
- Chrome/Chromium browser support (can be added later)
- OAuth authentication (unreliable with ytmusicapi as of 2026)
- Browser automation (Selenium/Playwright)
- Encrypting or securing browser.json beyond file permissions

### Success Criteria

- [ ] Cookie extraction from Firefox Dev Edition works reliably
- [ ] Daemon proactively refreshes browser.json without user intervention
- [ ] Auth failures trigger auto-recovery via cookie re-extraction
- [ ] Desktop notification fires when auto-recovery also fails
- [ ] i3blocks widget shows auth status with appropriate color
- [ ] Zero manual header-pasting required as long as user has active Firefox session
- [ ] Existing manual `ytmpctl auth` flow continues to work unchanged

---

## Architecture Overview

### Key Components

1. **CookieExtractor** (`ytmpd/cookie_extract.py`): Reads Firefox's cookies.sqlite, filters by domain/container, builds browser.json-compatible headers
2. **Auto-refresh logic** (in `ytmpd/daemon.py`): Periodic timer + reactive trigger that calls CookieExtractor and reinitializes YTMusicClient
3. **Notification system**: `notify-send` calls on unrecoverable auth failure
4. **CLI integration** (`bin/ytmpctl`): `auth --auto` subcommand
5. **Status integration** (`bin/ytmpd-status`): Auth-aware color output

### Data Flow

```
Firefox cookies.sqlite -> CookieExtractor -> browser.json -> YTMusicClient reinit -> sync resumes
                                                                |
                                                          (on failure)
                                                                |
                                                          notify-send desktop notification
```

### Technology Stack

- **Language**: Python 3.12+
- **Cookie extraction**: stdlib `sqlite3` (Firefox stores cookies unencrypted)
- **Notification**: `notify-send` CLI (libnotify, standard on Linux desktops)
- **Testing**: pytest with mocked Firefox database
- **Config**: YAML (existing config.yaml pattern)

---

## Phase Breakdown

> **Note for Agents**: Only read the section for your assigned phase. Reading all phases wastes context.

---

### Phase 1: Cookie Extraction Module

**Objective**: Build a standalone module that extracts YouTube Music cookies from Firefox and generates a valid browser.json file.

**Estimated Context Budget**: ~60k tokens

#### Deliverables

1. `ytmpd/cookie_extract.py` - Cookie extraction module
2. `tests/test_cookie_extract.py` - Unit tests
3. Updated `examples/config.yaml` with `auto_auth` section

#### Detailed Requirements

Create `ytmpd/cookie_extract.py` with the following:

**Class: `FirefoxCookieExtractor`**

```python
class FirefoxCookieExtractor:
    def __init__(self, browser: str = "firefox", profile: str | None = None, container: str | None = None)
    def find_profile_dir(self) -> Path
    def extract_cookies(self, domain: str = ".youtube.com") -> list[dict]
    def build_browser_json(self, output_path: Path) -> Path
    def validate_cookies(self, cookies: list[dict]) -> bool
```

**Implementation details**:

1. **`find_profile_dir()`**:
   - Read `~/.mozilla/firefox/profiles.ini` to find profiles
   - For `browser="firefox"`: find the profile with `Default=` under `[Install...]` section (non-dev-edition install ID)
   - For `browser="firefox-dev"`: find the profile with `Default=` under the dev-edition install ID (`Install46F492E0ACFF84D4`)
   - If `profile` is explicitly set, use that directory name directly
   - Return the full path: `~/.mozilla/firefox/{profile_dir}`

2. **`extract_cookies()`**:
   - Copy `cookies.sqlite` (and `-wal`, `-shm` files if they exist) to a temp directory to avoid locking issues with running Firefox
   - Open the copy with sqlite3
   - Query `moz_cookies` table for the given domain
   - Filter by `originAttributes`:
     - If `container` is None: filter `originAttributes = ''` (no container)
     - If `container` is a string: look up `containers.json` to find the `userContextId` for that container name, then filter `originAttributes = '^userContextId={id}'`
   - Return list of dicts with keys: `name`, `value`, `host`, `expiry`, `isSecure`
   - Clean up temp files

3. **`build_browser_json()`**:
   - Call `extract_cookies()` to get YouTube cookies
   - Build the cookie header string: `"name1=value1; name2=value2; ..."`
   - Extract `__Secure-3PAPISID` (or fall back to `SAPISID`) for SAPISIDHASH computation
   - Compute SAPISIDHASH: `sha1(f"{unix_timestamp} {sapisid} {origin}")` where origin is `https://music.youtube.com`
   - Construct headers dict matching ytmusicapi browser auth format:
     ```python
     {
         "accept": "*/*",
         "accept-encoding": "gzip, deflate",
         "authorization": f"SAPISIDHASH {ts}_{hash}",
         "content-encoding": "gzip",
         "content-type": "application/json",
         "cookie": cookie_string,
         "origin": "https://music.youtube.com",
         "user-agent": "Mozilla/5.0 (X11; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
         "x-goog-authuser": "0",
         "x-origin": "https://music.youtube.com",
     }
     ```
   - Write JSON to `output_path`
   - Return the path

4. **`validate_cookies()`**:
   - Check that all required cookies are present: at minimum `SAPISID` or `__Secure-3PAPISID`, plus `SID`, `HSID`, `SSID`
   - Check that cookies are not expired (compare `expiry` against current time)
   - Return True if valid, False otherwise

**Error handling**:
- `CookieExtractionError(YTMPDError)` - new exception in `exceptions.py`
- Raise if: profile not found, cookies.sqlite missing, required cookies missing, SQLite errors
- Log warnings for: expired cookies, missing optional cookies

**Config additions** (add to `examples/config.yaml` and `config.py` defaults):

```yaml
# Auto-authentication settings
auto_auth:
  enabled: false
  browser: firefox-dev
  container: null
  profile: null
  refresh_interval_hours: 12
```

Add validation for `auto_auth` in `_validate_config()`:
- `enabled` must be bool
- `browser` must be `"firefox"` or `"firefox-dev"`
- `container` must be null or string
- `profile` must be null or string
- `refresh_interval_hours` must be positive number

#### Dependencies

**Requires**: None (first phase)

**Enables**: Phase 2 (daemon integration needs this module)

#### Completion Criteria

- [ ] `FirefoxCookieExtractor` can find Firefox Dev Edition profile automatically
- [ ] Can extract YouTube cookies filtered by container (or no container)
- [ ] Can generate a valid `browser.json` that passes ytmusicapi auth
- [ ] Validates required cookies are present and not expired
- [ ] Config loading supports `auto_auth` section with proper defaults and validation
- [ ] Handles edge cases: missing WAL files, locked database, missing profile
- [ ] Unit tests cover: profile detection, cookie extraction, browser.json generation, validation, error cases
- [ ] All existing tests still pass

#### Testing Requirements

- Create a test fixture with a minimal SQLite database mimicking Firefox's `moz_cookies` schema
- Test `find_profile_dir()` with mocked `profiles.ini`
- Test `extract_cookies()` with the fixture database
- Test `build_browser_json()` produces valid JSON with correct structure
- Test `validate_cookies()` with valid and invalid/expired cookie sets
- Test container filtering with mocked `containers.json`
- Test error cases: missing files, empty database, missing required cookies
- Test config validation for `auto_auth` section

#### Notes

- The Firefox Dev Edition install ID is `Install46F492E0ACFF84D4` (found in profiles.ini)
- Standard Firefox install ID is `Install4F96D1932A9F858E`
- Always copy the SQLite database before reading -- never open Firefox's live database
- The `-wal` and `-shm` files are important for getting the latest data -- copy them too if they exist
- `originAttributes = ''` means no container (the user's primary Google account)
- The SAPISIDHASH in browser.json is only for type detection -- ytmusicapi recomputes it on each API call

---

### Phase 2: Daemon Auto-Refresh Integration

**Objective**: Integrate cookie extraction into the daemon for proactive and reactive authentication refresh.

**Estimated Context Budget**: ~60k tokens

#### Deliverables

1. Modified `ytmpd/daemon.py` - Auto-refresh timer thread + reactive refresh
2. Modified `ytmpd/ytmusic.py` - Method to reinitialize client with new auth
3. `tests/test_auto_auth_daemon.py` - Integration tests for daemon auto-refresh
4. Updated `ytmpd/daemon.py` status command with auto-auth info

#### Detailed Requirements

**YTMusicClient changes** (`ytmpd/ytmusic.py`):

Add a method to reinitialize the client with a new auth file:

```python
def refresh_auth(self, auth_file: Path | None = None) -> bool:
    """Reinitialize the client with fresh credentials.

    Args:
        auth_file: Path to new browser.json. If None, uses self.auth_file.

    Returns:
        True if reinitialization succeeded, False otherwise.
    """
```

This should:
- Update `self.auth_file` if a new path is provided
- Call `_init_client()` again
- Reset the auth cache (`_auth_cache_time = 0`)
- Return True on success, False on failure (log the error, don't raise)

**Daemon changes** (`ytmpd/daemon.py`):

1. **Add auto-auth refresh thread**:
   - New method `_auto_auth_loop()` running as daemon thread
   - Sleeps for `refresh_interval_hours` (from config), then:
     a. Creates `FirefoxCookieExtractor` with config values
     b. Calls `build_browser_json()` to regenerate `~/.config/ytmpd/browser.json`
     c. Calls `self.ytmusic_client.refresh_auth()` to reload
     d. Logs success/failure
   - Only runs if `auto_auth.enabled` is True in config

2. **Add reactive refresh on auth failure**:
   - In `_perform_sync()`, after catching auth errors, attempt auto-refresh:
     a. Check if auto_auth is enabled
     b. Try cookie extraction + browser.json rebuild
     c. If successful, reinitialize client and retry sync once
     d. If extraction also fails, log error and trigger notification (Phase 3 will add actual notification)
   - Add a cooldown to prevent rapid repeated extraction attempts (minimum 5 minutes between reactive refreshes)

3. **Update `__init__`**:
   - Store auto_auth config: `self.auto_auth_config = self.config.get("auto_auth", {})`
   - Initialize `_last_reactive_refresh` timestamp
   - Create auto-auth thread if enabled

4. **Update `run()`**:
   - Start `_auto_auth_thread` if auto_auth is enabled

5. **Update `_cmd_status()`**:
   - Add `auto_auth_enabled` (bool) to status response
   - Add `last_auto_refresh` (ISO timestamp or None) to status response
   - Add `auto_refresh_failures` (count) to status response

6. **State persistence**:
   - Save `last_auto_refresh` and `auto_refresh_failures` in sync_state.json

#### Dependencies

**Requires**: Phase 1 (CookieExtractor module)

**Enables**: Phase 3 (notifications use the failure state from this phase)

#### Completion Criteria

- [ ] Daemon starts auto-auth refresh thread when `auto_auth.enabled = true`
- [ ] Proactive refresh runs on configured schedule
- [ ] Reactive refresh triggers on auth failure during sync
- [ ] `refresh_auth()` reinitializes ytmusicapi client without daemon restart
- [ ] Cooldown prevents rapid repeated extraction attempts
- [ ] Status command includes auto-auth information
- [ ] State persists across daemon restarts
- [ ] Auto-auth disabled by default (existing behavior unchanged)
- [ ] All existing tests still pass
- [ ] New tests cover: proactive refresh, reactive refresh, cooldown, config disabled

#### Testing Requirements

- Mock `FirefoxCookieExtractor` to test daemon integration without real Firefox
- Test proactive refresh thread triggers at correct interval
- Test reactive refresh triggers on auth failure
- Test cooldown prevents rapid re-extraction
- Test status response includes auto-auth fields
- Test with auto_auth disabled (existing behavior)
- Test `YTMusicClient.refresh_auth()` reinitializes correctly

#### Notes

- The auto-auth thread should be a daemon thread (like existing threads)
- Use `threading.Event` for clean shutdown (not just sleep)
- The reactive refresh in `_perform_sync()` should NOT block the sync thread indefinitely
- Keep the extraction + reinit atomic-ish: write browser.json to a temp file, then rename

---

### Phase 3: Notifications, CLI, and i3blocks Integration

**Objective**: Add user-facing notifications and commands for auto-auth status and manual triggers.

**Estimated Context Budget**: ~50k tokens

#### Deliverables

1. Modified `bin/ytmpctl` - `auth --auto` command + updated status display
2. Modified `bin/ytmpd-status` - Auth-aware color coding
3. `ytmpd/notify.py` - Desktop notification helper
4. Modified `ytmpd/daemon.py` - Notification triggers on auth failure
5. `tests/test_notify.py` - Notification tests
6. Updated `bin/ytmpctl` help text

#### Detailed Requirements

**Desktop notification** (`ytmpd/notify.py`):

Create a simple notification helper:

```python
def send_notification(title: str, message: str, urgency: str = "normal", icon: str = "dialog-warning") -> bool:
    """Send desktop notification via notify-send.

    Returns True if notification was sent, False if notify-send not available.
    """
```

- Use `subprocess.run(["notify-send", ...])` with timeout
- Catch `FileNotFoundError` if notify-send isn't installed
- Log warning if notification fails (don't raise)

**Daemon notification triggers** (`ytmpd/daemon.py`):

- After reactive refresh fails in `_perform_sync()`, call:
  ```python
  send_notification(
      "ytmpd: Authentication Failed",
      "Auto-refresh failed. Open YouTube Music in Firefox to refresh cookies.",
      urgency="critical"
  )
  ```
- After proactive refresh fails in `_auto_auth_loop()`, call notification with `urgency="normal"`
- Rate-limit notifications: maximum one per hour to avoid spam

**CLI changes** (`bin/ytmpctl`):

1. **`ytmpctl auth --auto`** command:
   - Directly invoke `FirefoxCookieExtractor.build_browser_json()` with config values
   - Print success/failure message
   - On success, print "browser.json updated. Daemon will pick up new credentials automatically."
   - On failure, print error and suggest checking Firefox is running with an active Google session

2. **Updated `cmd_status()`**:
   - If `auto_auth_enabled` is True in status response, show:
     ```
     Auto-auth: Enabled (firefox-dev)
     Last refresh: 2026-03-30 14:00:00
     Refresh failures: 0
     ```
   - If disabled, show:
     ```
     Auto-auth: Disabled
     ```

3. **Updated help text**: Add `auth --auto` to the help message

**i3blocks integration** (`bin/ytmpd-status`):

- Modify `get_auth_status()` or the main output logic:
  - If `auth_valid` is False: use red color (`#FF0000`) for the entire status line
  - If `auth_valid` is True but `auto_refresh_failures > 0`: use orange/warning color (`#FFA500`)
  - Otherwise: keep existing color scheme
- The i3blocks format already supports color via the third line of output

#### Dependencies

**Requires**: Phase 2 (daemon auto-refresh state and status fields)

**Enables**: Phase 4 (testing depends on all components being in place)

#### Completion Criteria

- [ ] `notify-send` fires on unrecoverable auth failure
- [ ] Notifications are rate-limited (max 1 per hour)
- [ ] `ytmpctl auth --auto` extracts cookies and updates browser.json
- [ ] `ytmpctl status` shows auto-auth information
- [ ] i3blocks widget changes color on auth failure
- [ ] Help text updated
- [ ] Graceful handling when notify-send is not installed
- [ ] All existing tests still pass

#### Testing Requirements

- Mock `subprocess.run` for notify-send tests
- Test notification rate limiting
- Test `ytmpctl auth --auto` with mocked CookieExtractor
- Test i3blocks color output with various auth states

#### Notes

- `notify-send` is part of libnotify and is standard on most Linux desktops
- The i3blocks script outputs 3 lines: full_text, short_text, color
- Keep the notification module simple -- it's just a subprocess call wrapper

---

### Phase 4: Integration Testing and Documentation

**Objective**: End-to-end integration tests, edge case handling, and documentation updates.

**Estimated Context Budget**: ~50k tokens

#### Deliverables

1. `tests/integration/test_auto_auth.py` - Integration tests
2. Updated `README.md` - Auto-auth documentation section
3. Updated `examples/config.yaml` - Documented auto_auth section
4. Edge case hardening in `ytmpd/cookie_extract.py`

#### Detailed Requirements

**Integration tests** (`tests/integration/test_auto_auth.py`):

1. **Full extraction flow**: Create a temp Firefox profile structure with cookies.sqlite, containers.json, profiles.ini. Run full `build_browser_json()` and verify output format.

2. **Edge cases to test**:
   - Firefox not installed (no `~/.mozilla/firefox/` directory)
   - Profile exists but cookies.sqlite is missing
   - cookies.sqlite exists but is locked (simulate with open write lock)
   - Database exists but has no YouTube cookies
   - Database has YouTube cookies but they're all expired
   - Multiple profiles, correct one selected
   - Container specified but doesn't exist in containers.json
   - Container specified and found, correct cookies filtered
   - WAL file missing (should still work, just less recent data)
   - Very large cookie database (performance)

3. **Daemon flow**: Test that when auto_auth is enabled, the daemon's status response includes the correct fields.

**Edge case hardening** (`ytmpd/cookie_extract.py`):

- Handle `sqlite3.OperationalError: database is locked` with retry (up to 3 attempts with 1s delay)
- Handle corrupt cookies.sqlite gracefully (log error, return empty)
- Handle missing `containers.json` when container is specified (raise clear error)
- Handle profile directory that exists but is not a valid Firefox profile

**README updates**:

Add a new section "Auto-Authentication" to README.md covering:
- What it does and why
- Prerequisites (Firefox with active Google session)
- Configuration options
- How to enable it
- What happens when cookies expire
- Troubleshooting (Firefox not found, wrong profile, wrong container)
- Manual trigger: `ytmpctl auth --auto`

**Config documentation**:

Update `examples/config.yaml` with commented auto_auth section explaining each option.

#### Dependencies

**Requires**: Phases 1, 2, 3

**Enables**: None (final phase)

#### Completion Criteria

- [ ] Integration tests pass with realistic Firefox profile fixtures
- [ ] All edge cases handled gracefully (no crashes, clear error messages)
- [ ] README documents auto-auth feature completely
- [ ] Example config includes documented auto_auth section
- [ ] Full test suite passes (existing + new)
- [ ] No regressions in existing functionality

#### Testing Requirements

- Integration tests use temporary directories with crafted SQLite databases
- Test the full pipeline: profile detection -> cookie extraction -> browser.json generation -> validation
- Test all edge cases listed above
- Run full test suite to verify no regressions

#### Notes

- Integration tests should be in `tests/integration/` directory
- Use `tmp_path` pytest fixture for temporary directories
- The README section should be practical and concise -- users want to know how to enable it, not implementation details
- Consider mentioning the "2 months without Firefox" scenario and what to expect

---

## Phase Dependencies Graph

```
Phase 1 (Cookie Extraction Module)
    |
Phase 2 (Daemon Auto-Refresh)
    |
Phase 3 (Notifications, CLI, i3blocks)
    |
Phase 4 (Integration Testing & Docs)
```

All phases are sequential -- each depends on the previous.

---

## Cross-Cutting Concerns

### Code Style

- Follow existing codebase conventions (ruff format, ruff check)
- Type hints on all function signatures
- Docstrings on all public methods (existing Google-style pattern)
- Keep line length consistent with existing code

### Error Handling

- New exception: `CookieExtractionError(YTMPDError)` in `exceptions.py`
- Cookie extraction errors should never crash the daemon
- Always log errors before returning failure
- Auth refresh failures are recoverable -- daemon continues running

### Logging

- Use `logging.getLogger(__name__)` pattern
- INFO: successful refresh, cookie count
- WARNING: missing optional cookies, expired cookies, notification failures
- ERROR: extraction failure, profile not found, database errors

### Testing Strategy

- Unit tests for cookie extraction module (mocked filesystem)
- Unit tests for daemon integration (mocked extractor)
- Integration tests with realistic file fixtures
- All new tests must pass alongside existing 154 tests

---

## Integration Points

### CookieExtractor <-> Daemon
- Daemon creates `FirefoxCookieExtractor` from config values
- Calls `build_browser_json()` on schedule and on auth failure
- Passes output path as `~/.config/ytmpd/browser.json`

### Daemon <-> YTMusicClient
- Daemon calls `ytmusic_client.refresh_auth()` after browser.json is rebuilt
- Client reinitializes internal ytmusicapi instance

### Daemon <-> Notification
- Daemon calls `send_notification()` when auto-refresh fails
- Rate-limited to prevent spam

### CLI <-> CookieExtractor
- `ytmpctl auth --auto` creates extractor and calls `build_browser_json()` directly
- Does not go through daemon

---

## Data Schemas

### Firefox profiles.ini

```ini
[Install46F492E0ACFF84D4]     # Firefox Dev Edition
Default=4wkrywqj.dev-edition-default

[Install4F96D1932A9F858E]     # Standard Firefox
Default=doqoab3a.default-release

[Profile0]
Name=dev-edition-default
IsRelative=1
Path=4wkrywqj.dev-edition-default
```

### Firefox containers.json

```json
{
  "identities": [
    {"userContextId": 12, "name": "ACCOUNT_004", "public": true},
    {"userContextId": 16, "name": "ACCOUNT_002", "public": true}
  ]
}
```

### moz_cookies table

```sql
CREATE TABLE moz_cookies (
    id INTEGER PRIMARY KEY,
    originAttributes TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    value TEXT NOT NULL,
    host TEXT NOT NULL,
    path TEXT NOT NULL,
    expiry INTEGER NOT NULL,
    lastAccessed INTEGER NOT NULL,
    creationTime INTEGER NOT NULL,
    isSecure INTEGER NOT NULL,
    isHttpOnly INTEGER NOT NULL,
    ...
);
```

---

## Glossary

**browser.json**: JSON file containing HTTP request headers used by ytmusicapi for browser-style authentication
**SAPISIDHASH**: Authentication hash computed from SAPISID cookie + timestamp + origin, used by YouTube/Google APIs
**Multi-Account Containers**: Firefox extension that isolates cookies per "container" tab
**originAttributes**: Firefox cookie column that stores container identity (empty = no container)
**Proactive refresh**: Refreshing cookies on a timer before they expire
**Reactive refresh**: Refreshing cookies in response to an auth failure

---

## References

- ytmusicapi browser auth docs: https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html
- SAPISIDHASH reverse engineering: https://stackoverflow.com/a/32065323/5726546
- Firefox cookie storage: cookies.sqlite with moz_cookies table
- ytmusicapi source (auth detection): `ytmusicapi/auth/auth_parse.py`

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
