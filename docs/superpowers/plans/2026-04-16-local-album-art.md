# Local-track album art implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `extras/airplay-bridge/mpd_owntone_metadata.py` fetch album art for local tracks (embedded → folder → iTunes → MusicBrainz/CAA) via an async worker that never blocks the MPD idle loop.

**Architecture:** A chain of resolver functions (pure, each returns `bytes | None`) runs inside an `ArtWorker` background thread. The main metadata loop emits a text-only block immediately, then hands the song to the worker through a latest-wins single-slot request box. On success the worker emits a second block with a PICT frame, guarded by a track-key check so stale fetches are dropped.

**Tech Stack:** Python 3 stdlib only (`socket`, `urllib.request`, `urllib.parse`, `json`, `hashlib`, `threading`). No new dependencies. Lives in `extras/airplay-bridge/` which has no test suite — verification is manual per the design spec (non-goal: tests).

**Spec:** `docs/superpowers/specs/2026-04-16-local-album-art-design.md`

**Branch:** `feature/local-album-art` (already cut off `main`).

---

## File impact

**Modified:** `extras/airplay-bridge/mpd_owntone_metadata.py` (only file touched).

No new files. No test files (consistent with the existing `extras/` convention).

---

## Task 1: Constants and album cache helpers

Adds module-level configuration and the positive/negative cache for online lookups. Pure functions — no behavior change visible yet because nothing calls them.

**Files:**
- Modify: `extras/airplay-bridge/mpd_owntone_metadata.py`

- [ ] **Step 1: Add new imports**

At the top of the file, replace the current import block (everything from `import base64` through `from pathlib import Path`) with:

```python
import base64
import hashlib
import json
import logging
import os
import re
import signal
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
```

- [ ] **Step 2: Add new constants**

Immediately after the existing `YT_PROXY_RE = re.compile(...)` line, add:

```python
# Album-art cache for online lookups (iTunes / MusicBrainz+CAA). Keyed on
# sha1(artist|album) to tolerate arbitrary Unicode and filesystem-unsafe
# characters in tag values. `.jpg` = hit, `.miss` = fresh negative marker.
ALBUM_CACHE_DIR = ART_CACHE_DIR / "albums"
NEG_CACHE_TTL_SEC = 30 * 24 * 3600  # 30 days

# Required by MusicBrainz; polite everywhere else.
ART_HTTP_USER_AGENT = "ytmpd-airplay-bridge/1.0 (+https://github.com/tyildirim/ytmpd)"

# Opt-out: set this env var to any non-empty value to disable iTunes/MB lookups.
# MPD-local resolvers (embedded + folder art) stay active regardless.
ONLINE_ART_DISABLED = bool(os.environ.get("YTMPD_AIRPLAY_NO_ONLINE_ART"))
```

- [ ] **Step 3: Add cache helper functions**

Insert the following helpers immediately before the existing `fetch_album_art` function:

```python
def _album_cache_key(artist: str, album: str) -> str:
    return hashlib.sha1(f"{artist}|{album}".encode("utf-8")).hexdigest()


def _album_cache_lookup(artist: str, album: str) -> bytes | str | None:
    """Return JPEG bytes on hit, the string 'miss' if a fresh miss marker
    exists, or None if the album has never been resolved (or the marker
    has aged past NEG_CACHE_TTL_SEC).
    """
    key = _album_cache_key(artist, album)
    hit_path = ALBUM_CACHE_DIR / f"{key}.jpg"
    miss_path = ALBUM_CACHE_DIR / f"{key}.miss"
    if hit_path.exists():
        try:
            return hit_path.read_bytes()
        except OSError as e:
            log.warning("Could not read cached album art %s: %s", hit_path, e)
            return None
    if miss_path.exists():
        age = time.time() - miss_path.stat().st_mtime
        if age < NEG_CACHE_TTL_SEC:
            return "miss"
    return None


def _album_cache_store(artist: str, album: str, data: bytes | None) -> None:
    """Persist a resolved art blob, or mark a negative-cache miss."""
    try:
        ALBUM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("Could not create album cache dir %s: %s", ALBUM_CACHE_DIR, e)
        return
    key = _album_cache_key(artist, album)
    hit_path = ALBUM_CACHE_DIR / f"{key}.jpg"
    miss_path = ALBUM_CACHE_DIR / f"{key}.miss"
    if data:
        try:
            hit_path.write_bytes(data)
            miss_path.unlink(missing_ok=True)
        except OSError as e:
            log.warning("Could not write cached album art %s: %s", hit_path, e)
    else:
        try:
            miss_path.touch()
        except OSError as e:
            log.warning("Could not mark album-art miss %s: %s", miss_path, e)
```

- [ ] **Step 4: Verify the module still imports cleanly**

Run:
```bash
python -c "import sys; sys.path.insert(0, 'extras/airplay-bridge'); import mpd_owntone_metadata; print('ok')"
```
Expected: `ok`. Any `SyntaxError` or `ImportError` means a typo in the additions.

- [ ] **Step 5: Commit**

```bash
git add extras/airplay-bridge/mpd_owntone_metadata.py
git commit -m "airplay-bridge: add album cache helpers and online-art constants"
```

---

## Task 2: MPD binary fetcher and MPD-local resolvers

Adds a chunked reader for MPD's `readpicture` / `albumart` commands, plus the two resolver functions that call it. Still no behavior change — not yet wired into `fetch_album_art`.

**Files:**
- Modify: `extras/airplay-bridge/mpd_owntone_metadata.py`

- [ ] **Step 1: Add the binary fetcher**

Insert immediately after `_album_cache_store` (i.e. just before `fetch_album_art`):

```python
def _mpd_binary_fetch(cmd: str, uri: str) -> bytes | None:
    """Run an MPD binary command ('albumart' or 'readpicture') to completion.

    Opens a fresh short-lived TCP connection so we don't collide with the
    metadata daemon's idle socket. Returns the full image bytes, or None
    on any error / when the server has no art.

    MPD wire format per chunk:
        size: <total>
        type: <mime>       (optional, varies per command)
        binary: <chunk_n>
        <chunk_n bytes>\n
        OK\n
    Loop with an incrementing offset until offset >= size.
    """
    try:
        sock = socket.create_connection(
            (MPD_HOST, MPD_PORT), timeout=ART_FETCH_TIMEOUT_SEC
        )
    except OSError as e:
        log.debug("MPD %s: connect failed: %s", cmd, e)
        return None

    buf = b""

    def _readline() -> bytes:
        nonlocal buf
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("MPD closed during binary fetch")
            buf += chunk
        line, _, buf = buf.partition(b"\n")
        return line

    def _read_exact(n: int) -> bytes:
        nonlocal buf
        while len(buf) < n:
            chunk = sock.recv(max(4096, n - len(buf)))
            if not chunk:
                raise ConnectionError("MPD closed during binary fetch")
            buf += chunk
        head, buf = buf[:n], buf[n:]
        return head

    try:
        banner = _readline()
        if not banner.startswith(b"OK MPD"):
            return None
        quoted_uri = uri.replace("\\", "\\\\").replace('"', '\\"')
        accumulated = bytearray()
        offset = 0
        total_size: int | None = None
        while True:
            sock.sendall(f'{cmd} "{quoted_uri}" {offset}\n'.encode("utf-8"))
            chunk_size: int | None = None
            while True:
                line = _readline()
                if line.startswith(b"ACK"):
                    log.debug("MPD %s %r: %s", cmd, uri, line.decode("ascii", "replace"))
                    return None
                if line.startswith(b"binary: "):
                    chunk_size = int(line[len(b"binary: "):].strip())
                    break
                if line.startswith(b"size: "):
                    total_size = int(line[len(b"size: "):].strip())
                # 'type:' and other keys are ignored
            if chunk_size is None or chunk_size == 0:
                return None
            accumulated.extend(_read_exact(chunk_size))
            _read_exact(1)  # trailing newline after the binary block
            ok = _readline()
            if not ok.startswith(b"OK"):
                return None
            offset += chunk_size
            if total_size is not None and offset >= total_size:
                return bytes(accumulated)
    except (OSError, ConnectionError, ValueError) as e:
        log.debug("MPD %s %r: %s", cmd, uri, e)
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass
```

- [ ] **Step 2: Add the MPD-local resolvers**

Insert immediately below `_mpd_binary_fetch`:

```python
def _resolve_mpd_readpicture(song: dict) -> bytes | None:
    file_uri = song.get("file", "")
    if not file_uri or "://" in file_uri:
        return None
    return _mpd_binary_fetch("readpicture", file_uri)


def _resolve_mpd_albumart(song: dict) -> bytes | None:
    file_uri = song.get("file", "")
    if not file_uri or "://" in file_uri:
        return None
    return _mpd_binary_fetch("albumart", file_uri)
```

- [ ] **Step 3: Verify module still imports**

Run:
```bash
python -c "import sys; sys.path.insert(0, 'extras/airplay-bridge'); import mpd_owntone_metadata; print('ok')"
```
Expected: `ok`.

- [ ] **Step 4: Smoke-test the binary fetcher against running MPD**

Pick any local file currently in the MPD DB and feed its URI to both commands. Use `mpc` to grab a currently-playing URI (if nothing's playing, use `mpc -p 6601 listall | grep -v '://' | head -1`):

```bash
LOCAL_URI=$(mpc -p 6601 current -f '%file%' 2>/dev/null)
if [ -z "$LOCAL_URI" ] || echo "$LOCAL_URI" | grep -q '://'; then
    LOCAL_URI=$(mpc -p 6601 listall 2>/dev/null | grep -v '://' | head -1)
fi
echo "Testing with: $LOCAL_URI"
python - "$LOCAL_URI" <<'PY'
import sys
sys.path.insert(0, "extras/airplay-bridge")
import mpd_owntone_metadata as m
uri = sys.argv[1]
for cmd in ("readpicture", "albumart"):
    r = m._mpd_binary_fetch(cmd, uri)
    print(f"{cmd}:", len(r) if r else None)
PY
```
Expected: either a non-zero byte count from at least one command (if the library has art for that file) or `None` from both. Any Python traceback = bug.

- [ ] **Step 5: Commit**

```bash
git add extras/airplay-bridge/mpd_owntone_metadata.py
git commit -m "airplay-bridge: add MPD binary fetcher and local art resolvers"
```

---

## Task 3: iTunes and MusicBrainz fetchers

Adds two pure fetcher functions that talk to the online services. Neither touches the album cache — caching is layered on top in Task 4. Still not wired into `fetch_album_art`.

**Files:**
- Modify: `extras/airplay-bridge/mpd_owntone_metadata.py`

- [ ] **Step 1: Add the iTunes fetcher**

Insert immediately after `_resolve_mpd_albumart`:

```python
def _fetch_itunes(artist: str, album: str) -> bytes | None:
    """Search the iTunes Search API for an album and download its artwork.

    iTunes returns `artworkUrl100` (100x100). Replacing the size token with
    '600x600bb' upgrades to 600x600 JPEG on the same CDN path. ~20 req/min
    per IP; a polite UA stays under whatever unwritten enforcement exists.
    """
    term = urllib.parse.quote(f"{artist} {album}")
    search_url = (
        f"https://itunes.apple.com/search?term={term}&entity=album&limit=1"
    )
    try:
        req = urllib.request.Request(
            search_url, headers={"User-Agent": ART_HTTP_USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=ART_FETCH_TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read())
    except Exception as e:  # noqa: BLE001
        log.debug("iTunes search failed (%r / %r): %s", artist, album, e)
        return None
    results = payload.get("results") or []
    if not results:
        return None
    art_url = results[0].get("artworkUrl100")
    if not art_url:
        return None
    art_url = art_url.replace("100x100bb", "600x600bb")
    try:
        req = urllib.request.Request(
            art_url, headers={"User-Agent": ART_HTTP_USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=ART_FETCH_TIMEOUT_SEC) as resp:
            return resp.read()
    except Exception as e:  # noqa: BLE001
        log.debug("iTunes art download failed (%s): %s", art_url, e)
        return None
```

- [ ] **Step 2: Add the MusicBrainz + Cover Art Archive fetcher**

Insert immediately after `_fetch_itunes`:

```python
def _fetch_musicbrainz(artist: str, album: str) -> bytes | None:
    """Look up a release via MusicBrainz, then fetch its cover via CAA.

    MB rate-limits to 1 req/sec (503 on exceed); CAA itself has no rate
    limit. Both free, no API key. UA is required by MB.
    """
    safe_artist = artist.replace('"', "")
    safe_album = album.replace('"', "")
    lucene = f'artist:"{safe_artist}" AND release:"{safe_album}"'
    mb_url = (
        "https://musicbrainz.org/ws/2/release/"
        f"?query={urllib.parse.quote(lucene)}&fmt=json&limit=1"
    )
    try:
        req = urllib.request.Request(
            mb_url, headers={"User-Agent": ART_HTTP_USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=ART_FETCH_TIMEOUT_SEC) as resp:
            payload = json.loads(resp.read())
    except Exception as e:  # noqa: BLE001
        log.debug("MusicBrainz search failed (%r / %r): %s", artist, album, e)
        return None
    releases = payload.get("releases") or []
    if not releases:
        return None
    mbid = releases[0].get("id")
    if not mbid:
        return None
    caa_url = f"https://coverartarchive.org/release/{mbid}/front-500"
    try:
        req = urllib.request.Request(
            caa_url, headers={"User-Agent": ART_HTTP_USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=ART_FETCH_TIMEOUT_SEC) as resp:
            return resp.read()
    except Exception as e:  # noqa: BLE001
        log.debug("CAA art fetch failed (%s): %s", mbid, e)
        return None
```

- [ ] **Step 3: Verify the fetchers independently**

Pick a popular, well-known album on your machine. Example:

```bash
python - <<'PY'
import sys
sys.path.insert(0, "extras/airplay-bridge")
import mpd_owntone_metadata as m
art = m._fetch_itunes("Radiohead", "OK Computer")
print("iTunes:", len(art) if art else None)
art = m._fetch_musicbrainz("Radiohead", "OK Computer")
print("MB/CAA:", len(art) if art else None)
PY
```
Expected: both print a byte count in the tens of thousands. A `None` from either is a red flag (network, ToS change, outage). Both must work before continuing.

- [ ] **Step 4: Commit**

```bash
git add extras/airplay-bridge/mpd_owntone_metadata.py
git commit -m "airplay-bridge: add iTunes and MusicBrainz art fetchers"
```

---

## Task 4: Online-resolver cache wrapper

Combines the two fetchers behind a single `_resolve_online(song)` entry point that consults the album cache, respects the opt-out env var, and records results (positive or miss) for future plays.

**Files:**
- Modify: `extras/airplay-bridge/mpd_owntone_metadata.py`

- [ ] **Step 1: Add `_resolve_online`**

Insert immediately after `_fetch_musicbrainz`:

```python
def _resolve_online(song: dict) -> bytes | None:
    """Cache-aware online lookup: iTunes then MusicBrainz/CAA.

    Skipped if YTMPD_AIRPLAY_NO_ONLINE_ART is set, or if Artist+Album tags
    aren't both present. Writes either the successful blob or a negative
    marker, so a second play of the same album never re-hits the network.
    """
    if ONLINE_ART_DISABLED:
        return None
    artist = (song.get("Artist") or song.get("AlbumArtist") or "").strip()
    album = (song.get("Album") or "").strip()
    if not artist or not album:
        return None

    cached = _album_cache_lookup(artist, album)
    if isinstance(cached, bytes):
        return cached
    if cached == "miss":
        return None

    for fetcher in (_fetch_itunes, _fetch_musicbrainz):
        try:
            art = fetcher(artist, album)
        except Exception as e:  # noqa: BLE001 - belt-and-suspenders
            log.warning("%s raised: %s", fetcher.__name__, e)
            art = None
        if art:
            _album_cache_store(artist, album, art)
            log.info(
                "Online art hit via %s for %r / %r (%d bytes)",
                fetcher.__name__,
                artist,
                album,
                len(art),
            )
            return art

    _album_cache_store(artist, album, None)
    log.info("No online art found for %r / %r (cached miss)", artist, album)
    return None
```

- [ ] **Step 2: Verify end-to-end with cache round-trip**

```bash
python - <<'PY'
import sys, shutil
sys.path.insert(0, "extras/airplay-bridge")
import mpd_owntone_metadata as m
# Fresh cache
shutil.rmtree(m.ALBUM_CACHE_DIR, ignore_errors=True)
song = {"Artist": "Radiohead", "Album": "OK Computer"}
# First call: hits network
art1 = m._resolve_online(song)
print("first:", len(art1) if art1 else None)
# Second call: must come from disk cache (should log no fetch)
art2 = m._resolve_online(song)
print("second (cached):", len(art2) if art2 else None)
assert art1 == art2, "cache round-trip mismatch"
# Obscure miss → negative cache marker
fake = {"Artist": "zzz-no-such-artist-xyz-9999", "Album": "nothing"}
art3 = m._resolve_online(fake)
print("miss:", art3)
miss_file = m.ALBUM_CACHE_DIR / f"{m._album_cache_key('zzz-no-such-artist-xyz-9999', 'nothing')}.miss"
print("miss marker exists:", miss_file.exists())
assert miss_file.exists(), "negative cache not written"
print("OK")
PY
```
Expected final line: `OK`, plus byte counts matching between first and second calls, and `miss marker exists: True`.

- [ ] **Step 3: Commit**

```bash
git add extras/airplay-bridge/mpd_owntone_metadata.py
git commit -m "airplay-bridge: add cached online album-art resolver"
```

---

## Task 5: Replace `fetch_album_art` with the resolver chain

Rewrites `fetch_album_art` as a thin dispatcher over an ordered resolver tuple. The YouTube-proxy logic moves into its own named resolver so the list is uniform. After this task `fetch_album_art` is **synchronous** and the metadata loop will briefly block on misses — that's temporary; Task 6 makes the whole thing async.

**Files:**
- Modify: `extras/airplay-bridge/mpd_owntone_metadata.py`

- [ ] **Step 1: Extract the YouTube-proxy resolver**

Insert immediately after `_resolve_online`:

```python
def _resolve_yt_proxy(song: dict) -> bytes | None:
    """Fetch YouTube thumbnail for tracks served via ytmpd's proxy URL.

    Cached per-video-id on disk under ART_CACHE_DIR. Cache hits are a local
    Path.read_bytes() so this resolver stays fast even for repeated plays.
    """
    file_uri = song.get("file", "")
    m = YT_PROXY_RE.search(file_uri)
    if not m:
        return None
    video_id = m.group(1)
    cache_path = ART_CACHE_DIR / f"{video_id}.jpg"
    if cache_path.exists():
        try:
            return cache_path.read_bytes()
        except OSError as e:
            log.warning("Could not read cached art %s: %s", cache_path, e)
    url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
    try:
        ART_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=ART_FETCH_TIMEOUT_SEC) as resp:
            data = resp.read()
        cache_path.write_bytes(data)
        log.info("Fetched YT art for %s (%d bytes)", video_id, len(data))
        return data
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to fetch YT art for %s: %s", video_id, e)
        return None
```

- [ ] **Step 2: Replace the existing `fetch_album_art`**

Locate the current `fetch_album_art` function (starts with `def fetch_album_art(song: dict) -> bytes | None:`) and replace it **entirely** with:

```python
_RESOLVERS = (
    _resolve_yt_proxy,
    _resolve_mpd_readpicture,
    _resolve_mpd_albumart,
    _resolve_online,
)


def fetch_album_art(song: dict) -> bytes | None:
    """Run the resolver chain and return the first non-None JPEG, or None."""
    for resolver in _RESOLVERS:
        try:
            art = resolver(song)
        except Exception as e:  # noqa: BLE001
            log.warning("resolver %s raised: %s", resolver.__name__, e)
            continue
        if art:
            return art
    return None
```

Leave `derive_album`, `make_track_payload`, `safe_write`, and everything below untouched for this task.

- [ ] **Step 3: Verify module still imports and fetches for YouTube tracks**

Import check:
```bash
python -c "import sys; sys.path.insert(0, 'extras/airplay-bridge'); import mpd_owntone_metadata; print('ok')"
```
Expected: `ok`.

Regression check for the YouTube path:
```bash
python - <<'PY'
import sys
sys.path.insert(0, "extras/airplay-bridge")
import mpd_owntone_metadata as m
song = {"file": "http://localhost:6602/proxy/dQw4w9WgXcQ"}
print("YT:", len(m.fetch_album_art(song)) if m.fetch_album_art(song) else None)
PY
```
Expected: a byte count (~10-30 KB). `None` would be a regression against pre-refactor behavior.

- [ ] **Step 4: Commit**

```bash
git add extras/airplay-bridge/mpd_owntone_metadata.py
git commit -m "airplay-bridge: refactor fetch_album_art to resolver chain"
```

---

## Task 6: Two-phase async emission

Introduces `ArtWorker` and rewires `metadata_loop` + `make_track_payload` to emit text metadata immediately and art later, all serialized through the existing `write_lock`.

**Files:**
- Modify: `extras/airplay-bridge/mpd_owntone_metadata.py`

- [ ] **Step 1: Change `make_track_payload` to take `art` as a parameter**

Replace the existing `make_track_payload` function **entirely** with:

```python
def make_track_payload(song: dict, art: bytes | None) -> bytes:
    """Build the XML payload for a complete track-change metadata block.

    `art` is None for the immediate text-only emission, and JPEG bytes for
    the follow-up emission from the art worker.
    """
    artist = song.get("Artist") or song.get("AlbumArtist") or ""
    title = song.get("Title") or os.path.basename(song.get("file", "")) or ""
    album = derive_album(song)
    track_id = song.get("Id") or song.get("Pos") or "0"

    log.info(
        "Track: %r / %r / %r (art: %s bytes)",
        artist,
        title,
        album,
        len(art) if art else "n/a",
    )

    chunks = [make_item(TYPE_SSNC, CODE_MDST)]
    if track_id:
        chunks.append(make_item(TYPE_CORE, CODE_MPER, str(track_id).encode("utf-8")))
    if artist:
        chunks.append(make_item(TYPE_CORE, CODE_ASAR, artist.encode("utf-8")))
    if title:
        chunks.append(make_item(TYPE_CORE, CODE_MINM, title.encode("utf-8")))
    if album:
        chunks.append(make_item(TYPE_CORE, CODE_ASAL, album.encode("utf-8")))
    if art:
        chunks.append(make_item(TYPE_SSNC, CODE_PICT, art))
    chunks.append(make_item(TYPE_SSNC, CODE_MDEN))
    return b"".join(chunks)
```

- [ ] **Step 2: Add the `ArtWorker` class**

Insert the class immediately after the `safe_write` function and before the `MPDClient` class:

```python
class ArtWorker:
    """Latest-wins async album-art resolver.

    The main loop calls `request(song)` once per track change. Only the most
    recent request is honored — writing over a pending request discards it,
    so rapid track-skipping can never queue up stale fetches.

    On a successful resolve the worker acquires `write_lock`, re-checks that
    the current track still matches what it fetched for, and emits a second
    MDST/MDEN block with the PICT frame. If the user already moved on, the
    blob is dropped.
    """

    def __init__(
        self,
        fd: int,
        write_lock: threading.Lock,
        current_key_getter,
    ) -> None:
        self._fd = fd
        self._write_lock = write_lock
        self._current_key_getter = current_key_getter
        self._cond = threading.Condition()
        self._pending: dict | None = None
        self._thread = threading.Thread(
            target=self._run, name="art-worker", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def request(self, song: dict) -> None:
        with self._cond:
            self._pending = song  # latest wins; any older pending is dropped
            self._cond.notify()

    def _run(self) -> None:
        while True:
            with self._cond:
                while self._pending is None:
                    self._cond.wait()
                song = self._pending
                self._pending = None
            song_key = (song.get("file"), song.get("Id"))
            try:
                art = fetch_album_art(song)
            except Exception as e:  # noqa: BLE001
                log.warning("art worker: fetch raised for %r: %s", song_key, e)
                continue
            if not art:
                continue
            with self._write_lock:
                if self._current_key_getter() != song_key:
                    log.debug(
                        "art worker: track changed, dropping art for %r",
                        song_key,
                    )
                    continue
                try:
                    os.write(self._fd, make_track_payload(song, art))
                except (BlockingIOError, OSError) as e:
                    log.warning("art worker: pipe write failed: %s", e)
```

- [ ] **Step 3: Rewrite `metadata_loop` to use the worker**

Replace the existing `metadata_loop` function **entirely** with:

```python
def metadata_loop(fd: int, lock: threading.Lock) -> None:
    """Subscribe to MPD `idle` and emit track-change blocks on every change.

    Two-phase per track:
      1. Emit text-only block immediately (no PICT).
      2. Hand the song to ArtWorker, which later emits a second block with
         PICT if the track hasn't changed by the time art is resolved.

    current_key_slot is a single-element list protected by the shared
    write_lock; the worker reads it under the same lock to guard against
    stale emissions.
    """
    current_key_slot: list = [None]
    art_worker = ArtWorker(fd, lock, lambda: current_key_slot[0])
    art_worker.start()

    def _emit_text(song: dict, key: tuple) -> None:
        with lock:
            current_key_slot[0] = key
            try:
                os.write(fd, make_track_payload(song, art=None))
            except BlockingIOError:
                log.warning("Metadata pipe write would block, dropping update")
            except OSError as e:
                log.error("Metadata pipe write failed: %s", e)

    while True:
        client = MPDClient(MPD_HOST, MPD_PORT)
        _reemit_active_client[0] = client
        last_song_key: tuple[str | None, str | None] | None = None
        try:
            client.connect()
            song = client.currentsong()
            key = (song.get("file"), song.get("Id"))
            if song:
                _emit_text(song, key)
                art_worker.request(song)
                last_song_key = key
            while True:
                changed = client.idle("player", "playlist")
                log.debug("idle event: %s", changed)
                song = client.currentsong()
                key = (song.get("file"), song.get("Id"))
                if song and key != last_song_key:
                    _emit_text(song, key)
                    art_worker.request(song)
                    last_song_key = key
        except (ConnectionError, OSError, RuntimeError) as e:
            log.info("metadata: reconnect (%s); re-emit on next connect", e)
            client.close()
            _reemit_active_client[0] = None
            if _reemit_pending[0]:
                _reemit_pending[0] = False
                time.sleep(0.2)
            else:
                time.sleep(RECONNECT_DELAY_SEC)
```

`safe_write` is now unused but leaving it in place is fine — it's cheap, self-contained, and other code paths may want it later. Do not delete.

- [ ] **Step 4: Verify module still imports**

```bash
python -c "import sys; sys.path.insert(0, 'extras/airplay-bridge'); import mpd_owntone_metadata; print('ok')"
```
Expected: `ok`.

- [ ] **Step 5: Dry-run the daemon against live MPD for ~10s**

This confirms startup, idle connection, and text-block emission without requiring AirPlay hardware. The metadata FIFO is a named pipe; if the OwnTone-bridge service isn't already holding the reader end, piping a reader is enough.

Terminal A (reader):
```bash
cat /var/lib/owntone-stream/mpd.pcm.metadata
```
Terminal B (daemon):
```bash
timeout 10 python extras/airplay-bridge/mpd_owntone_metadata.py || true
```
Then in a third terminal skip tracks:
```bash
mpc -p 6601 next
mpc -p 6601 next
```

Expected in terminal A: two or three `<item>...<code>6d647374...` (MDST) blocks appearing **immediately** on each skip (text-only first), possibly followed by a second MDST..MDEN block with a large `PICT` payload a moment later when art resolves. Nothing should hang.

If the OwnTone bridge service is already running and holding the reader end, stop it first:
```bash
systemctl --user stop mpd-owntone-metadata
```
...then run the above, then re-start the service:
```bash
systemctl --user start mpd-owntone-metadata
```

- [ ] **Step 6: Commit**

```bash
git add extras/airplay-bridge/mpd_owntone_metadata.py
git commit -m "airplay-bridge: async two-phase emission via ArtWorker"
```

---

## Task 7: Live verification on the real AirPlay chain

End-to-end checks from the design spec's Testing section. Requires the user's Denon (or any AirPlay receiver with a display) powered on and routed via `speaker`.

**Files:** none modified in this task — pure runtime verification.

- [ ] **Step 1: Deploy the new daemon**

```bash
systemctl --user restart mpd-owntone-metadata
journalctl --user -u mpd-owntone-metadata -f &
JOURNAL_PID=$!
```
Expected: log shows `Opening metadata pipe /var/lib/owntone-stream/mpd.pcm.metadata` and `Connected to MPD: OK MPD ...`.

- [ ] **Step 2: Play a local file with embedded ID3/FLAC art**

Pick a known local FLAC / MP3 with embedded cover and play it:
```bash
mpc -p 6601 clear
mpc -p 6601 add "<local-file-uri-here>"
mpc -p 6601 play
```
Expected journal lines: `Track: 'Artist' / 'Title' / 'Album' (art: n/a bytes)` immediately, then (within ~1 sec) a second `Track: ... (art: <N> bytes)` line where N > 1000. Denon display shows the album cover.

- [ ] **Step 3: Play a local file with only a folder cover.jpg**

Pick a file whose directory contains `cover.jpg` / `folder.jpg` but no embedded art. Expected: same two-line pattern; art comes from `albumart`, not `readpicture`. Denon shows cover.

- [ ] **Step 4: Play a tagged local file with no embedded / folder art but a findable album**

Pick (or fake, by renaming) a file with `Artist` + `Album` tags matching something popular (e.g. a track tagged "Radiohead / OK Computer" sourced from a copy with no cover).

Expected:
- First play: text appears immediately; 1-3 sec later a second emission with art from iTunes (preferred) or MB/CAA. Journal: `Online art hit via _fetch_itunes for 'Radiohead' / 'OK Computer' (... bytes)`.
- Second play (same track): instant text, instant art (positive cache hit, no `_fetch_*` log line).

- [ ] **Step 5: Play a local file with an obscure / missing album**

Pick a track whose tags won't be in iTunes or MB (bootleg, demo, etc).

Expected:
- First play: text emits, no second emission. Journal: `No online art found for ... (cached miss)`.
- Second play: instant text, no network calls. Journal shows the resolver chain ran but `_resolve_online` returned None without hitting the network.
- Verify the miss marker exists:
  ```bash
  ls ~/.cache/mpd-owntone-metadata/albums/*.miss
  ```

- [ ] **Step 6: Rapid skip stress test**

```bash
for i in 1 2 3 4 5; do mpc -p 6601 next; sleep 0.3; done
```
Expected: the journal shows five text-only emissions, at most one `art worker: track changed, dropping art` line for superseded requests, and one final second-block emission for the last track. No pile-up of fetches, no zombie threads.

- [ ] **Step 7: Opt-out path**

```bash
systemctl --user stop mpd-owntone-metadata
YTMPD_AIRPLAY_NO_ONLINE_ART=1 python extras/airplay-bridge/mpd_owntone_metadata.py &
DAEMON=$!
mpc -p 6601 play <some local file with no embedded / folder art>
sleep 10
kill $DAEMON
```
Expected: only text emission. No `_resolve_online` calls in the log. No HTTP traffic (verify with `ss -t state established '( dport = :443 )'` or simply by absence of iTunes/MB log lines).

Restart the normal service:
```bash
systemctl --user start mpd-owntone-metadata
```

- [ ] **Step 8: Kill the journal follower**

```bash
kill $JOURNAL_PID 2>/dev/null
```

- [ ] **Step 9: Commit nothing**

This task produced no file changes — no commit. If any of the above steps failed, STOP and fix before proceeding to Task 8.

---

## Task 8: Final verification and merge to main

- [ ] **Step 1: Invoke `superpowers:verification-before-completion`**

Before claiming done, run that skill (it enforces evidence-before-assertions). It will walk through: did every task actually complete, do the logs from Task 7 actually show the expected output, were all commits made on `feature/local-album-art`.

- [ ] **Step 2: Merge to main with `--no-ff`**

Per user's git rules:
```bash
git checkout main
git merge --no-ff feature/local-album-art -m "Merge feature/local-album-art: fetch album art for local tracks"
```

- [ ] **Step 3: Confirm**

```bash
git log --oneline -10
git branch
```
Expected: merge commit on `main`, feature branch still exists (do not delete without asking).
