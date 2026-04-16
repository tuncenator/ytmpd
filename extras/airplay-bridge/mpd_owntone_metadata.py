#!/usr/bin/env python3
"""Bridge MPD track metadata to OwnTone via a Shairport-Sync-style metadata pipe.

OwnTone watches `<audio-pipe>.metadata` for shairport-sync's XML+DMAP frames and
forwards them as DACP metadata to the active AirPlay receiver. This daemon
subscribes to MPD `idle player playlist` and emits a fresh metadata block on
every track change containing artist/title/album/track-id/album-art. Album is
tagged "ytmpd" for YouTube tracks served via ytmpd's proxy, the file's own
album tag for local files (falling back to "local"), "stream" otherwise.

Note: progress is NOT supported. OwnTone v29's pipe-input metadata reader
silently drops both shairport `prgr` (logged as "unexpected") and DAAP `astm`
(silently ignored), so neither track-length nor elapsed time can be conveyed
to the AVR through this path. The Denon shows session-elapsed time and 0:00
total. Fixing this requires either patching OwnTone or re-architecting around
its queue API (each MPD track becomes a queue item with native duration).
"""

from __future__ import annotations

import base64
import hashlib
import json  # noqa: F401 - used by Task 3
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

MPD_HOST = "localhost"
MPD_PORT = 6601
META_PIPE = "/var/lib/owntone-stream/mpd.pcm.metadata"
RECONNECT_DELAY_SEC = 3.0

# Album-art lookup
ART_CACHE_DIR = Path.home() / ".cache" / "mpd-owntone-metadata"
ART_FETCH_TIMEOUT_SEC = 5.0
# ytmpd serves YouTube tracks via http://localhost:<port>/proxy/<11-char video_id>
YT_PROXY_RE = re.compile(r"/proxy/([A-Za-z0-9_-]{11})(?:[?#/]|$)")

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

# DMAP type codes (4 ASCII bytes, hex-encoded for the XML wire format)
TYPE_CORE = "636f7265"  # 'core' - DAAP standard codes
TYPE_SSNC = "73736e63"  # 'ssnc' - Shairport Sync Native Codes

# Per-frame codes
CODE_MDST = "6d647374"  # 'mdst' - metadata-stream start (begin track)
CODE_MDEN = "6d64656e"  # 'mden' - metadata-stream end   (commit track)
CODE_MPER = "6d706572"  # 'mper' - persistent track id
CODE_ASAR = "61736172"  # 'asar' - artist
CODE_MINM = "6d696e6d"  # 'minm' - title (track name)
CODE_ASAL = "6173616c"  # 'asal' - album
CODE_PICT = "50494354"  # 'PICT' - album art (JPEG or PNG bytes)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("mpd-owntone-metadata")


def handle_signal(signum: int, _frame) -> None:
    log.info("Received signal %d, exiting", signum)
    sys.exit(0)


# Re-emit trigger, set by SIGUSR1 (e.g. when the `speaker` CLI changes the
# active AirPlay output — the new RTSP session needs the metadata re-sent).
_reemit_active_client: list = [None]  # single-slot box; populated by metadata_loop
_reemit_pending: list = [False]  # true => next reconnect is fast-path


def handle_reemit(_signum: int, _frame) -> None:
    log.info("Re-emit requested via SIGUSR1")
    _reemit_pending[0] = True
    client = _reemit_active_client[0]
    if client is None or client.sock is None:
        return
    # Shutdown the idle socket; metadata_loop's recv() unwinds into the
    # reconnect path, which re-issues currentsong and writes metadata fresh.
    try:
        client.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGUSR1, handle_reemit)


def make_item(type_hex: str, code_hex: str, payload: bytes | None = None) -> bytes:
    """Encode one shairport-sync metadata item as XML bytes."""
    if payload is None:
        return (
            f"<item><type>{type_hex}</type><code>{code_hex}</code>" f"<length>0</length></item>\n"
        ).encode()
    b64 = base64.b64encode(payload).decode("ascii")
    return (
        f"<item><type>{type_hex}</type><code>{code_hex}</code>"
        f"<length>{len(payload)}</length>"
        f'<data encoding="base64">\n{b64}\n</data></item>\n'
    ).encode()


def _album_cache_key(artist: str, album: str) -> str:
    return hashlib.sha1(f"{artist}|{album}".encode()).hexdigest()


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


def fetch_album_art(song: dict) -> bytes | None:
    """Return JPEG bytes for the song's album art, or None.

    Currently handles YouTube tracks served via ytmpd's proxy URL by extracting
    the video_id and pulling YouTube's hqdefault thumbnail. Cached on disk so
    repeated plays of the same track don't re-fetch.
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
        log.info("Fetched art for %s (%d bytes)", video_id, len(data))
        return data
    except Exception as e:  # noqa: BLE001 - log and continue
        log.warning("Failed to fetch art for %s: %s", video_id, e)
        return None


def derive_album(song: dict) -> str:
    """Tag album by source: 'ytmpd' for YouTube proxy URLs, MPD's album for
    local files (falling back to 'local' if the file has no album tag),
    'stream' for other HTTP sources.
    """
    file_uri = song.get("file", "")
    if YT_PROXY_RE.search(file_uri):
        return "ytmpd"
    if "://" in file_uri:
        return song.get("Album") or "stream"
    return song.get("Album") or "local"


def make_track_payload(song: dict) -> bytes:
    """Build the XML payload for a complete track-change metadata block."""
    artist = song.get("Artist") or song.get("AlbumArtist") or ""
    title = song.get("Title") or os.path.basename(song.get("file", "")) or ""
    album = derive_album(song)
    track_id = song.get("Id") or song.get("Pos") or "0"
    art = fetch_album_art(song)

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


def safe_write(fd: int, lock: threading.Lock, payload: bytes) -> None:
    """Write to the metadata FIFO under a lock; log and swallow non-fatal errors."""
    with lock:
        try:
            os.write(fd, payload)
        except BlockingIOError:
            log.warning("Metadata pipe write would block, dropping update")
        except OSError as e:
            log.error("Metadata pipe write failed: %s", e)


class MPDClient:
    """Minimal MPD text-protocol client over TCP."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None
        self.buf = b""

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        banner = self._readline()
        if not banner.startswith(b"OK MPD"):
            raise RuntimeError(f"unexpected MPD banner: {banner!r}")
        log.info("Connected to MPD: %s", banner.decode("ascii", "replace").strip())
        self.sock.settimeout(None)

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
            self.buf = b""

    def _readline(self) -> bytes:
        while b"\n" not in self.buf:
            assert self.sock is not None
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("MPD closed connection")
            self.buf += chunk
        line, _, self.buf = self.buf.partition(b"\n")
        return line + b"\n"

    def _send(self, cmd: str) -> None:
        assert self.sock is not None
        self.sock.sendall(cmd.encode("utf-8") + b"\n")

    def _read_kv(self) -> dict[str, str]:
        result: dict[str, str] = {}
        while True:
            line = self._readline().decode("utf-8", "replace").rstrip("\n")
            if line == "OK":
                return result
            if line.startswith("ACK "):
                raise RuntimeError(f"MPD error: {line}")
            key, _, value = line.partition(": ")
            result[key] = value

    def idle(self, *subsystems: str) -> list[str]:
        self._send("idle " + " ".join(subsystems))
        changed: list[str] = []
        while True:
            line = self._readline().decode("utf-8", "replace").rstrip("\n")
            if line == "OK":
                return changed
            if line.startswith("ACK "):
                raise RuntimeError(f"MPD error: {line}")
            key, _, value = line.partition(": ")
            if key == "changed":
                changed.append(value)

    def currentsong(self) -> dict[str, str]:
        self._send("currentsong")
        return self._read_kv()


def metadata_loop(fd: int, lock: threading.Lock) -> None:
    """Subscribe to MPD `idle` and emit a track-change block on every change.

    On reconnect (including SIGUSR1-induced socket shutdown), the current song
    is always re-emitted — that path is how we refresh metadata into a new
    AirPlay RTSP session after a speaker switch.
    """
    while True:
        client = MPDClient(MPD_HOST, MPD_PORT)
        _reemit_active_client[0] = client
        last_song_key: tuple[str | None, str | None] | None = None
        try:
            client.connect()
            song = client.currentsong()
            key = (song.get("file"), song.get("Id"))
            if song:
                safe_write(fd, lock, make_track_payload(song))
                last_song_key = key
            while True:
                changed = client.idle("player", "playlist")
                log.debug("idle event: %s", changed)
                song = client.currentsong()
                key = (song.get("file"), song.get("Id"))
                if song and key != last_song_key:
                    safe_write(fd, lock, make_track_payload(song))
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


def main() -> int:
    log.info("Opening metadata pipe %s", META_PIPE)
    fd = os.open(META_PIPE, os.O_RDWR | os.O_NONBLOCK)
    write_lock = threading.Lock()
    metadata_loop(fd, write_lock)
    return 0


if __name__ == "__main__":
    sys.exit(main())
