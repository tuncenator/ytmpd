# Security and Stability Fixes - Summary

**Branch:** `fix/critical-security-stability`
**Date:** 2025-10-20
**Status:** ✅ All tests passing (226/226)

## Overview

This document summarizes the critical security and stability fixes applied to ytmpd based on a comprehensive code review. Four immediate vulnerabilities were identified and fixed.

---

## 🔴 Critical Issues Fixed

### 1. Path Traversal Vulnerability
**Location:** `ytmpd/mpd_client.py:251-253`, `ytmpd/mpd_client.py:306-308`
**Severity:** Critical
**CVE Potential:** Yes

#### Problem
Playlist names were not validated before use in file paths, allowing path traversal attacks:
```python
playlist_file = playlist_dir / f"{name}.m3u"
```

An attacker could provide `../../../etc/passwd` as a playlist name, writing arbitrary files outside the playlist directory.

#### Fix
Added validation to reject playlist names containing path separators:
```python
if '/' in name or '\\' in name or '..' in name:
    raise ValueError(f"Invalid playlist name (contains path separators): {name}")
```

Applied to:
- `_create_m3u_playlist()`
- `_create_xspf_playlist()`

#### Tests Added
- `test_m3u_playlist_rejects_path_with_slash`
- `test_m3u_playlist_rejects_path_with_backslash`
- `test_m3u_playlist_rejects_path_with_dotdot`
- `test_xspf_playlist_rejects_path_traversal`
- `test_m3u_playlist_accepts_valid_name`

---

### 2. Thread Safety in TrackStore
**Location:** `ytmpd/track_store.py:150-157`, `ytmpd/track_store.py:126-128`
**Severity:** High
**Impact:** Data corruption, race conditions

#### Problem 1: Unprotected Reads
Database reads were not protected by locks while writes were:
```python
def get_track(self, video_id: str):
    cursor = self.conn.execute(...)  # No lock!
    row = cursor.fetchone()
    return dict(row) if row else None
```

Multiple threads could read during writes, causing:
- Stale data reads
- Potential database corruption
- Race conditions

#### Fix
Protected read operations with the same lock as writes:
```python
def get_track(self, video_id: str):
    with self._lock:  # Now protected
        cursor = self.conn.execute(...)
        row = cursor.fetchone()
        return dict(row) if row else None
```

#### Problem 2: Incorrect Timestamp Updates
When saving metadata without URLs (`stream_url=None`), the `updated_at` timestamp was still being updated:
```python
updated_at = excluded.updated_at  # Always updated!
```

This reset the expiry timer even when the URL didn't actually refresh.

#### Fix
Only update timestamp when URL is actually provided:
```python
updated_at = CASE WHEN excluded.stream_url IS NOT NULL
             THEN excluded.updated_at
             ELSE updated_at END
```

#### Tests Added
- `test_concurrent_reads_are_safe` (20 concurrent threads)
- `test_concurrent_read_write_are_safe` (20 concurrent threads)
- `test_updated_at_not_changed_when_stream_url_none`

---

### 3. URL Validation in ICY Proxy
**Location:** `ytmpd/icy_proxy.py:303-314`
**Severity:** High
**Impact:** Proxy server crashes

#### Problem
Stream URLs were not validated before HTTP redirect:
```python
return web.HTTPTemporaryRedirect(stream_url)  # stream_url could be None!
```

If `stream_url` was `None` or malformed, the proxy would crash with an exception.

#### Fix
Added comprehensive URL validation:
```python
# Validate stream URL before redirecting
if not stream_url:
    logger.error(f"[PROXY] stream_url is None for {video_id}")
    raise web.HTTPBadGateway(
        text=f"Stream URL is missing for video_id: {video_id}"
    )

if not isinstance(stream_url, str) or not stream_url.startswith(('http://', 'https://')):
    logger.error(f"[PROXY] Invalid stream_url format for {video_id}: {stream_url[:100]}")
    raise web.HTTPBadGateway(
        text=f"Invalid stream URL format for video_id: {video_id}"
    )
```

#### Tests Added
- `test_proxy_rejects_none_stream_url`
- `test_proxy_rejects_invalid_stream_url`
- `test_proxy_accepts_valid_stream_url`

---

### 4. Socket Timeout Protection
**Location:** `ytmpd/daemon.py:485-486`, `ytmpd/daemon.py:530-536`
**Severity:** High
**Impact:** Daemon hangs indefinitely

#### Problem
Socket connections had no timeout:
```python
data = conn.recv(1024).decode("utf-8").strip()  # Can block forever!
```

A slow or malicious client could cause the daemon to hang indefinitely.

#### Fix
Added 5-second timeout and explicit timeout exception handling:
```python
# Set timeout to prevent indefinite blocking (5 seconds)
conn.settimeout(5.0)

# Read command (up to 1KB)
data = conn.recv(1024).decode("utf-8").strip()
```

```python
except socket.timeout:
    logger.warning("Socket connection timed out waiting for command")
    try:
        error_response = {"success": False, "error": "Connection timeout"}
        conn.sendall((json.dumps(error_response) + "\n").encode("utf-8"))
    except Exception:
        pass
```

#### Tests Added
- `test_socket_has_timeout_set`

---

## Test Results

### Before Fixes
- Tests: 214/214 passing

### After Fixes
- Tests: 226/226 passing ✅
- New security tests: 12
- No regressions

### Test Coverage
All fixes are covered by automated tests:
- **Path traversal:** 5 tests
- **Thread safety:** 3 tests
- **URL validation:** 3 tests
- **Socket timeout:** 1 test

---

## Files Changed

| File | Lines Changed | Description |
|------|---------------|-------------|
| `ytmpd/mpd_client.py` | +6 | Path traversal validation |
| `ytmpd/track_store.py` | +8 | Thread safety improvements |
| `ytmpd/icy_proxy.py` | +14 | URL validation |
| `ytmpd/daemon.py` | +9 | Socket timeout handling |
| `tests/test_security_fixes.py` | +347 (new) | Security test suite |

**Total:** 390 insertions, 7 deletions

---

## Remaining Issues (Not Fixed Yet)

### Short Term (Recommended)
6. **Atomic cache writes** (`stream_resolver.py:385`) - Cache corruption risk
7. **Missing stream URL saves** (`daemon.py:841-845`) - Inefficiency
8. **Infinite loop potential** (`daemon.py:306`) - With large sync_interval values

### Medium Priority
9. **Hardcoded buffer size** (`daemon.py:486`) - 1024 bytes may truncate commands
10. **No cache cleanup** (`stream_resolver.py`) - Memory leak over time
11. **Missing retry limit** (`mpd_client.py:419-435`) - Can retry forever
12. **Duplicate code** (multiple duration parsing methods) - Maintenance burden

### Low Priority
13-16. Style issues, magic numbers, logging inconsistencies

### Security Concerns
17. **No auth on Unix socket** - Local privilege escalation risk
18. **No rate limiting** - DoS vulnerability
19. **Proxy has no auth** - Multi-user system risk

---

## Recommendations

### Deploy Immediately
These fixes address critical security vulnerabilities and should be deployed ASAP:
1. ✅ Path traversal vulnerability (CRITICAL)
2. ✅ Thread safety issues (HIGH)
3. ✅ URL validation (HIGH)
4. ✅ Socket timeout (HIGH)

### Next Sprint
Address these issues in the next development cycle:
- Atomic cache writes (#6)
- Stream URL saving (#7)
- Infinite loop protection (#8)

### Long Term
- Add authentication to socket and proxy
- Implement rate limiting
- Add comprehensive security audit

---

## How to Review

```bash
# Checkout the fix branch
git checkout fix/critical-security-stability

# View the changes
git diff main..fix/critical-security-stability

# Run tests
source .venv/bin/activate
pytest tests/ -v

# Run only security tests
pytest tests/test_security_fixes.py -v
```

---

## Sign-off

**Reviewed by:** Code Review
**Tested by:** Automated test suite (226/226 passing)
**Ready for:** Merge to main
**Breaking changes:** None
**Migration required:** None
