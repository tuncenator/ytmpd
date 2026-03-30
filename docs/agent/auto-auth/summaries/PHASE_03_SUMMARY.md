# Phase 3: Notifications, CLI, and i3blocks Integration - Summary

**Date Completed:** 2026-03-30

---

## Objective

Add user-facing notifications and commands for auto-auth status and manual triggers.

---

## Work Completed

### What Was Built

- `ytmpd/notify.py` with `send_notification()` using `notify-send` subprocess call
- Module-level rate limiting (max 1 notification per hour) to prevent spam
- Notification triggers in daemon: proactive refresh failure (normal urgency) and reactive refresh failure (critical urgency)
- `ytmpctl auth --auto` command that invokes `FirefoxCookieExtractor.build_browser_json()` directly from CLI
- Updated `ytmpctl status` to display auto-auth enabled/disabled, last refresh time, and failure count
- Updated `bin/ytmpd-status` i3blocks widget with auth-aware color coding:
  - Red (#FF0000) when auth is invalid
  - Orange (#FFA500) when auto_refresh_failures > 0
  - Applied in all states: playing, paused, stopped, MPD unavailable
- Updated `get_auth_status()` return type to include `auto_refresh_failures` from daemon status
- Updated help text with `auth --auto` command
- 11 unit tests for notification module

### Files Created

- `ytmpd/notify.py` - Desktop notification helper with rate limiting
- `tests/test_notify.py` - 11 tests for notification sending and rate limiting

### Files Modified

- `ytmpd/daemon.py` - Added `send_notification` import and notification calls after proactive/reactive refresh failures
- `bin/ytmpctl` - Added `auth --auto` command, updated status display with auto-auth info, updated help text, updated dispatch
- `bin/ytmpd-status` - Updated `get_auth_status()` to return 3-tuple with `auto_refresh_failures`, added orange/red color overrides in all output paths

### Key Design Decisions

- **Module-level rate limiting**: Used module globals (`_last_notification_time`) rather than a class, since `send_notification()` is a simple function called from multiple places in the daemon
- **Rate limit at the notification layer**: The 1-hour cooldown is in `notify.py` itself, not in the caller, so all notification sources share the same rate limit
- **`get_auth_status()` returns 3-tuple**: Extended the existing function rather than adding a separate call, since it already queries the daemon status socket and `auto_refresh_failures` is in the same response
- **Color override during playback**: Auth failure colors override the normal track-type colors even during active playback, so users see the warning immediately

---

## Completion Criteria Status

- [x] `notify-send` fires on unrecoverable auth failure
- [x] Notifications are rate-limited (max 1 per hour)
- [x] `ytmpctl auth --auto` extracts cookies and updates browser.json
- [x] `ytmpctl status` shows auto-auth information
- [x] i3blocks widget changes color on auth failure
- [x] Help text updated
- [x] Graceful handling when notify-send is not installed
- [x] All existing tests still pass (same 7 pre-existing failures)

---

## Testing

### Tests Written

- `tests/test_notify.py` - 11 tests across 2 test classes:
  - `TestSendNotification` (6 tests): basic send, custom urgency, custom icon, missing notify-send, timeout, generic exception
  - `TestRateLimiting` (5 tests): first notification sent, second rate-limited, after cooldown, before cooldown expires, failed notification doesn't update timestamp

### Test Results

```
11 passed in 0.03s
```

Full suite: 516 passed, 7 failed (pre-existing), 4 skipped.

---

## Challenges & Solutions

### Challenge: Rate limiting test with mocked time

Initial mock time values (1000.0) were too close to the initial `_last_notification_time` of 0.0, causing the first notification to be rate-limited since `1000 - 0 = 1000 < 3600`.

**Solution:** Used mock time values starting at 10000.0 so the first notification always passes the cooldown check (`10000 - 0 >= 3600`).

---

## Code Quality

- Code formatted with ruff format
- All ruff checks pass for modified/new files
- Type hints on all new function signatures
- Docstrings on all new public methods

---

## Dependencies

### Required by This Phase
- Phase 2: Daemon Auto-Refresh Integration (auto-auth state, status fields, `_attempt_auto_refresh()`)

### Unblocked Phases
- Phase 4: Integration Testing and Documentation

---

## Notes for Future Phases

- `send_notification()` is a standalone function -- import and call from anywhere
- The rate limit is shared across all callers via module globals; reset it in tests using the `reset_rate_limit` fixture pattern
- The `get_auth_status()` function in `bin/ytmpd-status` now returns a 3-tuple `(bool, str, int)` -- any new callers must unpack all three values
- The `ytmpctl auth --auto` command works independently of the daemon -- it reads config and writes browser.json directly

---

## Integration Points

- `send_notification()` is called by `_auto_auth_loop()` and `_perform_sync()` in `daemon.py`
- `ytmpctl auth --auto` creates `FirefoxCookieExtractor` directly from config, bypassing the daemon
- `bin/ytmpd-status` queries daemon status via Unix socket to get `auto_refresh_failures`
- `ytmpctl status` displays `auto_auth_enabled`, `last_auto_refresh`, `auto_refresh_failures` from daemon status response

---

## Next Steps

**Next Phase:** 4 - Integration Testing and Documentation

**Recommended Actions:**
1. Create `tests/integration/test_auto_auth.py` with full extraction flow tests
2. Add edge case hardening to `ytmpd/cookie_extract.py` (locked database retry, corrupt database handling)
3. Update `README.md` with auto-auth documentation section
4. Run full test suite to verify no regressions
