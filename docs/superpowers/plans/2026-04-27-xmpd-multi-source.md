# xmpd Multi-Source Implementation Plan (Phases B–E)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add provider abstraction, Tidal provider, AirPlay album-art for Tidal-served tracks, and install-script migration to the renamed `xmpd` codebase produced by `2026-04-26-xmpd-rename.md`.

**Architecture:** Define a `Provider` Protocol; refactor existing YT-Music code into `YTMusicProvider`; add `TidalProvider`. Track store keyed by `(provider, track_id)`. Stream proxy routes `/proxy/<provider>/<id>`. Daemon iterates over enabled+authenticated providers. AirPlay bridge consumes Tidal album art via `track_store.art_url`. `install.sh` migrates old config shape and DB schema idempotently.

**Tech Stack:** Python 3.11+, ytmusicapi, tidalapi (new), aiohttp, sqlite3, pytest, pyperclip or subprocess shell-out for clipboard, ruamel.yaml for comment-preserving YAML rewrite.

**Reference spec:** `docs/superpowers/specs/2026-04-26-xmpd-tidal-design.md` (Phases B–E).

**Working directory:** `~/Sync/Programs/xmpd/` (created by `2026-04-26-xmpd-rename.md`).

**Commit strategy:** Multiple commits per stage. Each task ends with a commit. Stage boundaries are clear cut points where the implementing AI may pause for review/approval.

**Out of scope:** cross-provider liked-tracks sync (future spec). The `Track.liked_signature` field is reserved here but not populated.

---

## Stage B — Provider abstraction (refactor; no behavior change)

Outcome of stage B: existing YT functionality flows through a `Provider` interface; tests pass; daemon behaves identically to post-rename state. Sets up the seam where `TidalProvider` slots in during Stage C.

### Task B1: Create empty providers package

**Files:**
- Create: `xmpd/providers/__init__.py`
- Create: `xmpd/auth/__init__.py`

- [ ] **Step 1: Create the package directories**

```bash
cd ~/Sync/Programs/xmpd
mkdir -p xmpd/providers xmpd/auth
touch xmpd/providers/__init__.py xmpd/auth/__init__.py
```

- [ ] **Step 2: Verify**

```bash
ls xmpd/providers/ xmpd/auth/
```

Expected: each shows `__init__.py`.

- [ ] **Step 3: Commit**

```bash
git add xmpd/providers/__init__.py xmpd/auth/__init__.py
git commit -m "providers: scaffold xmpd/providers and xmpd/auth packages"
```

### Task B2: Define Track / Playlist / TrackMetadata dataclasses

**Files:**
- Create: `xmpd/providers/base.py`
- Test: `tests/test_providers_base.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_providers_base.py`:

```python
"""Tests for the Provider Protocol and shared dataclasses."""

from xmpd.providers.base import Track, TrackMetadata, Playlist


def test_track_metadata_construction():
    md = TrackMetadata(
        title="So What",
        artist="Miles Davis",
        album="Kind of Blue",
        duration_seconds=562,
        art_url="https://example.com/cover.jpg",
    )
    assert md.title == "So What"
    assert md.artist == "Miles Davis"
    assert md.album == "Kind of Blue"


def test_track_construction_with_provider():
    md = TrackMetadata(title="t", artist="a", album="al", duration_seconds=120, art_url=None)
    track = Track(provider="yt", track_id="abc12345_-9", metadata=md, liked=True)
    assert track.provider == "yt"
    assert track.track_id == "abc12345_-9"
    assert track.metadata.title == "t"
    assert track.liked is True
    assert track.liked_signature is None


def test_playlist_construction():
    pl = Playlist(
        provider="tidal",
        playlist_id="12345",
        name="Favorites",
        track_count=42,
        is_owned=True,
        is_favorites=True,
    )
    assert pl.provider == "tidal"
    assert pl.is_favorites is True
```

- [ ] **Step 2: Run test, expect ImportError**

```bash
cd ~/Sync/Programs/xmpd
source .venv/bin/activate
pytest tests/test_providers_base.py -v
```

Expected: `ImportError: cannot import name 'Track' from 'xmpd.providers.base'` or similar (the file doesn't exist yet).

- [ ] **Step 3: Implement `xmpd/providers/base.py` (dataclasses only; Protocol next task)**

```python
"""Provider abstraction: shared dataclasses for the Provider Protocol.

The Protocol itself is defined in this module too; see Provider class below.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TrackMetadata:
    """Per-track metadata shared across providers.

    art_url is the provider's canonical album/track art URL. None if the
    provider doesn't expose one.
    """

    title: str
    artist: str | None
    album: str | None
    duration_seconds: int | None
    art_url: str | None


@dataclass(frozen=True)
class Track:
    """A track in the multi-source library.

    Identified by the compound key (provider, track_id). `liked_signature`
    is reserved for a future cross-provider sync layer; populate during
    sync via a normalized hash, leave None until then.
    """

    provider: str
    track_id: str
    metadata: TrackMetadata
    liked: bool | None = None
    liked_signature: str | None = None


@dataclass(frozen=True)
class Playlist:
    """A playlist in the multi-source library.

    `is_owned` distinguishes user-created playlists from favorited ones
    (relevant for Tidal where the distinction is sharp). `is_favorites`
    flags the special "Liked Songs" / "Favorites" pseudo-playlist.
    """

    provider: str
    playlist_id: str
    name: str
    track_count: int
    is_owned: bool
    is_favorites: bool
```

- [ ] **Step 4: Run test, expect pass**

```bash
pytest tests/test_providers_base.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/base.py tests/test_providers_base.py
git commit -m "providers: add Track, TrackMetadata, Playlist dataclasses"
```

### Task B3: Define Provider Protocol

**Files:**
- Modify: `xmpd/providers/base.py`
- Test: `tests/test_providers_base.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_providers_base.py`:

```python
from xmpd.providers.base import Provider


class _StubProvider:
    """Minimal Protocol-conformant stub for testing isinstance checks."""

    name = "stub"

    def is_enabled(self) -> bool:
        return True

    def is_authenticated(self) -> bool:
        return True

    def list_playlists(self):
        return []

    def get_playlist_tracks(self, playlist_id):
        return []

    def get_favorites(self):
        return []

    def resolve_stream(self, track_id):
        return f"http://example.com/{track_id}"

    def get_track_metadata(self, track_id):
        return TrackMetadata(title="t", artist=None, album=None, duration_seconds=None, art_url=None)

    def search(self, query, limit=25):
        return []

    def get_radio(self, seed_track_id, limit=25):
        return []

    def like(self, track_id):
        pass

    def dislike(self, track_id):
        pass

    def unlike(self, track_id):
        pass

    def get_like_state(self, track_id):
        return False

    def report_play(self, track_id, duration_seconds):
        pass


def test_stub_satisfies_provider_protocol():
    stub = _StubProvider()
    assert isinstance(stub, Provider)
```

- [ ] **Step 2: Run test, expect ImportError on Provider**

```bash
pytest tests/test_providers_base.py -v
```

Expected: ImportError on `Provider`.

- [ ] **Step 3: Add Protocol to `xmpd/providers/base.py`**

Append to `xmpd/providers/base.py`:

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class Provider(Protocol):
    """Multi-source provider Protocol.

    Implementations live under xmpd/providers/{ytmusic,tidal}.py.
    Concrete classes set `name` to the canonical short form ("yt", "tidal").
    """

    name: str

    def is_enabled(self) -> bool: ...
    def is_authenticated(self) -> bool: ...

    # Library
    def list_playlists(self) -> list[Playlist]: ...
    def get_playlist_tracks(self, playlist_id: str) -> list[Track]: ...
    def get_favorites(self) -> list[Track]: ...

    # Stream
    def resolve_stream(self, track_id: str) -> str: ...
    def get_track_metadata(self, track_id: str) -> TrackMetadata: ...

    # Discovery
    def search(self, query: str, limit: int = 25) -> list[Track]: ...
    def get_radio(self, seed_track_id: str, limit: int = 25) -> list[Track]: ...

    # Ratings
    def like(self, track_id: str) -> None: ...
    def dislike(self, track_id: str) -> None: ...
    def unlike(self, track_id: str) -> None: ...
    def get_like_state(self, track_id: str) -> bool: ...

    # History
    def report_play(self, track_id: str, duration_seconds: int) -> None: ...
```

- [ ] **Step 4: Run test, expect pass**

```bash
pytest tests/test_providers_base.py -v
```

Expected: all tests pass including `test_stub_satisfies_provider_protocol`.

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/base.py tests/test_providers_base.py
git commit -m "providers: define Provider Protocol with full method surface"
```

### Task B4: Provider registry skeleton

**Files:**
- Modify: `xmpd/providers/__init__.py`
- Test: `tests/test_providers_registry.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_providers_registry.py`:

```python
"""Tests for the provider registry."""

import pytest
from xmpd.providers import build_registry, get_enabled_provider_names


def test_build_registry_empty_when_no_providers_enabled():
    config = {"yt": {"enabled": False}, "tidal": {"enabled": False}}
    registry = build_registry(config)
    assert registry == {}


def test_get_enabled_provider_names_returns_yt_only():
    config = {"yt": {"enabled": True}, "tidal": {"enabled": False}}
    names = get_enabled_provider_names(config)
    assert names == ["yt"]


def test_get_enabled_provider_names_returns_both():
    config = {"yt": {"enabled": True}, "tidal": {"enabled": True}}
    names = get_enabled_provider_names(config)
    assert sorted(names) == ["tidal", "yt"]
```

- [ ] **Step 2: Run test, expect ImportError**

```bash
pytest tests/test_providers_registry.py -v
```

Expected: ImportError on `build_registry`.

- [ ] **Step 3: Implement `xmpd/providers/__init__.py`**

```python
"""Provider registry.

Reads config and instantiates enabled providers. Authentication failures
mark a provider as unauthenticated; the daemon decides what to do (warn
and continue, typically).
"""

from typing import Any

from xmpd.providers.base import Provider


def get_enabled_provider_names(config: dict[str, Any]) -> list[str]:
    """Return the canonical names of enabled providers from config."""
    enabled: list[str] = []
    for name in ("yt", "tidal"):
        section = config.get(name, {})
        if section.get("enabled", False):
            enabled.append(name)
    return enabled


def build_registry(config: dict[str, Any]) -> dict[str, Provider]:
    """Build a name-to-provider map for enabled providers.

    Authentication failures during construction surface as warnings via
    each provider's own logging; they're still included in the registry
    but `is_authenticated()` returns False.

    Returns an empty dict if no providers are enabled.
    """
    registry: dict[str, Provider] = {}

    if "yt" in get_enabled_provider_names(config):
        # Lazy import to avoid circular dependencies when only Tidal is enabled.
        from xmpd.providers.ytmusic import YTMusicProvider

        registry["yt"] = YTMusicProvider(config["yt"])

    if "tidal" in get_enabled_provider_names(config):
        from xmpd.providers.tidal import TidalProvider

        registry["tidal"] = TidalProvider(config["tidal"])

    return registry
```

Note: This will fail to fully exercise until `YTMusicProvider` exists (Task B6) and `TidalProvider` exists (Stage C). The registry tests above only exercise the empty-registry and name-listing paths, so they pass.

- [ ] **Step 4: Run test, expect pass**

```bash
pytest tests/test_providers_registry.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/__init__.py tests/test_providers_registry.py
git commit -m "providers: add registry with enabled-only iteration"
```

### Task B5: Move ytmusic.py into providers/ and rename module

**Files:**
- Rename: `xmpd/ytmusic.py` → `xmpd/providers/ytmusic.py`

- [ ] **Step 1: git mv the module**

```bash
cd ~/Sync/Programs/xmpd
git mv xmpd/ytmusic.py xmpd/providers/ytmusic.py
```

- [ ] **Step 2: Fix imports across the codebase**

```bash
cd ~/Sync/Programs/xmpd
find . -path ./.git -prune -o -path ./.venv -prune -o -name '*.py' -print | \
xargs sed -i \
  -e 's/from xmpd\.ytmusic import/from xmpd.providers.ytmusic import/g' \
  -e 's/from xmpd\.ytmusic /from xmpd.providers.ytmusic /g' \
  -e 's/import xmpd\.ytmusic/import xmpd.providers.ytmusic/g'
```

- [ ] **Step 3: Verify no stale imports remain**

```bash
grep -rn "from xmpd\.ytmusic\|import xmpd\.ytmusic" --include='*.py' . 2>/dev/null
```

Expected: no output.

- [ ] **Step 4: Run all tests**

```bash
pytest -q 2>&1 | tail -10
```

Expected: same pass count as the post-rename baseline.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "providers: move xmpd/ytmusic.py into xmpd/providers/"
```

### Task B6: Create YTMusicProvider class wrapping YTMusicClient

**Files:**
- Modify: `xmpd/providers/ytmusic.py`
- Test: `tests/test_providers_ytmusic.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_providers_ytmusic.py`:

```python
"""Tests for YTMusicProvider — wraps YTMusicClient to satisfy Provider Protocol."""

from unittest.mock import MagicMock

from xmpd.providers.base import Provider
from xmpd.providers.ytmusic import YTMusicProvider


def test_ytmusic_provider_satisfies_protocol():
    config = {"enabled": True, "auto_auth": {"enabled": False}}
    p = YTMusicProvider(config)
    assert isinstance(p, Provider)
    assert p.name == "yt"


def test_ytmusic_provider_is_enabled():
    p = YTMusicProvider({"enabled": True})
    assert p.is_enabled() is True
    p2 = YTMusicProvider({"enabled": False})
    assert p2.is_enabled() is False
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_providers_ytmusic.py -v
```

Expected: ImportError or AttributeError on YTMusicProvider.

- [ ] **Step 3: Add YTMusicProvider class to xmpd/providers/ytmusic.py**

At the top of `xmpd/providers/ytmusic.py`, add (preserving existing content):

```python
from typing import Any

from xmpd.providers.base import Playlist, Provider, Track, TrackMetadata


class YTMusicProvider:
    """Provider implementation for YouTube Music.

    Wraps the existing YTMusicClient (defined later in this file). Each
    Provider Protocol method delegates to YTMusicClient and converts
    return values into the shared (Track, Playlist, TrackMetadata) types.
    """

    name = "yt"

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        # YTMusicClient construction is lazy — we don't connect to the
        # service until the first call that needs it. is_authenticated()
        # checks the auth file directly.
        self._client: Any = None

    def is_enabled(self) -> bool:
        return bool(self._config.get("enabled", False))

    def is_authenticated(self) -> bool:
        # Defer to the existing browser.json check used by YTMusicClient.
        from pathlib import Path
        return Path("~/.config/xmpd/browser.json").expanduser().is_file()

    def _ensure_client(self):
        if self._client is None:
            self._client = YTMusicClient()  # existing constructor in this file
        return self._client
```

- [ ] **Step 4: Run test, expect pass**

```bash
pytest tests/test_providers_ytmusic.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/ytmusic.py tests/test_providers_ytmusic.py
git commit -m "providers: scaffold YTMusicProvider implementing Protocol"
```

### Task B7: Implement YTMusicProvider.list_playlists

**Files:**
- Modify: `xmpd/providers/ytmusic.py`
- Test: `tests/test_providers_ytmusic.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_providers_ytmusic.py`:

```python
def test_list_playlists_returns_playlist_objects():
    p = YTMusicProvider({"enabled": True})
    p._client = MagicMock()
    p._client.get_library_playlists.return_value = [
        {"id": "PL_abc", "title": "My Mix", "trackCount": 25},
        {"id": "PL_xyz", "title": "Workout", "trackCount": 10},
    ]
    p._client.get_liked_songs.return_value = {"id": "LM", "trackCount": 100}
    playlists = p.list_playlists()
    names = sorted(pl.name for pl in playlists)
    assert names == ["Liked Songs", "My Mix", "Workout"]
    favorites = next(pl for pl in playlists if pl.is_favorites)
    assert favorites.name == "Liked Songs"
    assert favorites.track_count == 100
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_providers_ytmusic.py::test_list_playlists_returns_playlist_objects -v
```

Expected: AttributeError on `list_playlists`.

- [ ] **Step 3: Implement `list_playlists`**

Add to `YTMusicProvider`:

```python
def list_playlists(self) -> list[Playlist]:
    client = self._ensure_client()
    user_playlists = client.get_library_playlists()
    liked = client.get_liked_songs()

    playlists: list[Playlist] = []
    for raw in user_playlists:
        playlists.append(Playlist(
            provider="yt",
            playlist_id=raw["id"],
            name=raw["title"],
            track_count=raw.get("trackCount", 0),
            is_owned=True,
            is_favorites=False,
        ))
    if liked:
        playlists.append(Playlist(
            provider="yt",
            playlist_id=liked.get("id", "LM"),
            name="Liked Songs",
            track_count=liked.get("trackCount", 0),
            is_owned=True,
            is_favorites=True,
        ))
    return playlists
```

- [ ] **Step 4: Run test, expect pass**

```bash
pytest tests/test_providers_ytmusic.py::test_list_playlists_returns_playlist_objects -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/ytmusic.py tests/test_providers_ytmusic.py
git commit -m "providers: YTMusicProvider.list_playlists wraps existing client"
```

### Task B8: Implement YTMusicProvider.get_playlist_tracks

**Files:**
- Modify: `xmpd/providers/ytmusic.py`
- Test: `tests/test_providers_ytmusic.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_providers_ytmusic.py`:

```python
def test_get_playlist_tracks_returns_track_objects():
    p = YTMusicProvider({"enabled": True})
    p._client = MagicMock()
    p._client.get_playlist_tracks.return_value = [
        {
            "videoId": "abc12345_-9",
            "title": "So What",
            "artists": [{"name": "Miles Davis"}],
            "album": {"name": "Kind of Blue"},
            "duration_seconds": 562,
            "thumbnails": [{"url": "https://example.com/yt.jpg"}],
            "liked": True,
        }
    ]
    tracks = p.get_playlist_tracks("PL_abc")
    assert len(tracks) == 1
    t = tracks[0]
    assert t.provider == "yt"
    assert t.track_id == "abc12345_-9"
    assert t.metadata.title == "So What"
    assert t.metadata.artist == "Miles Davis"
    assert t.metadata.album == "Kind of Blue"
    assert t.liked is True
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_providers_ytmusic.py::test_get_playlist_tracks_returns_track_objects -v
```

Expected: AttributeError.

- [ ] **Step 3: Implement `get_playlist_tracks`**

Add to `YTMusicProvider`:

```python
@staticmethod
def _to_track(raw: dict) -> Track:
    """Convert a ytmusicapi track dict into a Track."""
    artists = raw.get("artists") or []
    artist_name = artists[0]["name"] if artists else None
    album_obj = raw.get("album")
    album_name = album_obj["name"] if isinstance(album_obj, dict) else None
    thumbnails = raw.get("thumbnails") or []
    art_url = thumbnails[-1]["url"] if thumbnails else None
    md = TrackMetadata(
        title=raw["title"],
        artist=artist_name,
        album=album_name,
        duration_seconds=raw.get("duration_seconds"),
        art_url=art_url,
    )
    return Track(
        provider="yt",
        track_id=raw["videoId"],
        metadata=md,
        liked=raw.get("liked"),
    )

def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
    client = self._ensure_client()
    raw_tracks = client.get_playlist_tracks(playlist_id)
    return [self._to_track(r) for r in raw_tracks]
```

- [ ] **Step 4: Run test, expect pass**

```bash
pytest tests/test_providers_ytmusic.py::test_get_playlist_tracks_returns_track_objects -v
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/ytmusic.py tests/test_providers_ytmusic.py
git commit -m "providers: YTMusicProvider.get_playlist_tracks with Track conversion"
```

### Task B9: Implement YTMusicProvider.get_favorites

**Files:**
- Modify: `xmpd/providers/ytmusic.py`
- Test: `tests/test_providers_ytmusic.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_get_favorites_returns_liked_songs_tracks():
    p = YTMusicProvider({"enabled": True})
    p._client = MagicMock()
    p._client.get_liked_songs.return_value = {
        "tracks": [
            {
                "videoId": "abc12345_-9",
                "title": "So What",
                "artists": [{"name": "Miles Davis"}],
                "album": {"name": "Kind of Blue"},
                "duration_seconds": 562,
                "thumbnails": [{"url": "https://example.com/x.jpg"}],
                "liked": True,
            }
        ]
    }
    tracks = p.get_favorites()
    assert len(tracks) == 1
    assert tracks[0].track_id == "abc12345_-9"
    assert tracks[0].liked is True
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_providers_ytmusic.py::test_get_favorites_returns_liked_songs_tracks -v
```

- [ ] **Step 3: Implement**

```python
def get_favorites(self) -> list[Track]:
    client = self._ensure_client()
    liked = client.get_liked_songs() or {}
    raw_tracks = liked.get("tracks", [])
    return [self._to_track(r) for r in raw_tracks]
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_providers_ytmusic.py::test_get_favorites_returns_liked_songs_tracks -v
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/ytmusic.py tests/test_providers_ytmusic.py
git commit -m "providers: YTMusicProvider.get_favorites returns liked-songs tracks"
```

### Task B10: Implement YTMusicProvider.resolve_stream and get_track_metadata

**Files:**
- Modify: `xmpd/providers/ytmusic.py`
- Test: `tests/test_providers_ytmusic.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_resolve_stream_delegates_to_stream_resolver(monkeypatch):
    from xmpd import stream_resolver
    monkeypatch.setattr(
        stream_resolver,
        "resolve_video_id",
        lambda vid: f"https://googlevideo.example/{vid}.m4a",
        raising=False,
    )
    # If resolve_video_id is a method on a class, patch the class as needed.
    p = YTMusicProvider({"enabled": True})
    url = p.resolve_stream("abc12345_-9")
    assert url.startswith("https://")
    assert "abc12345_-9" in url


def test_get_track_metadata_returns_track_metadata():
    p = YTMusicProvider({"enabled": True})
    p._client = MagicMock()
    p._client.get_song.return_value = {
        "videoDetails": {
            "videoId": "abc12345_-9",
            "title": "So What",
            "author": "Miles Davis",
            "lengthSeconds": "562",
            "thumbnail": {"thumbnails": [{"url": "https://example.com/x.jpg"}]},
        },
    }
    md = p.get_track_metadata("abc12345_-9")
    assert md.title == "So What"
    assert md.artist == "Miles Davis"
    assert md.duration_seconds == 562
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_providers_ytmusic.py -v 2>&1 | tail -20
```

- [ ] **Step 3: Implement**

```python
from xmpd.stream_resolver import StreamResolver

# inside YTMusicProvider:
def resolve_stream(self, track_id: str) -> str:
    """Resolve a YT video_id to a playable HTTP URL via yt-dlp."""
    resolver = StreamResolver(cache_hours=self._config.get("stream_cache_hours", 5))
    return resolver.resolve_video_id(track_id)

def get_track_metadata(self, track_id: str) -> TrackMetadata:
    client = self._ensure_client()
    raw = client.get_song(track_id) or {}
    details = raw.get("videoDetails", {}) or {}
    thumbs = details.get("thumbnail", {}).get("thumbnails", []) or []
    art_url = thumbs[-1]["url"] if thumbs else None
    duration = details.get("lengthSeconds")
    return TrackMetadata(
        title=details.get("title", ""),
        artist=details.get("author"),
        album=None,
        duration_seconds=int(duration) if duration else None,
        art_url=art_url,
    )
```

- [ ] **Step 4: Run tests, expect pass**

```bash
pytest tests/test_providers_ytmusic.py -v 2>&1 | tail -20
```

If `test_resolve_stream_delegates_to_stream_resolver` fails because the existing StreamResolver has a different shape, adapt the test to match the actual existing class while preserving the contract: `resolve_stream(track_id)` returns a string URL.

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/ytmusic.py tests/test_providers_ytmusic.py
git commit -m "providers: YTMusicProvider.resolve_stream and get_track_metadata"
```

### Task B11: Implement YTMusicProvider.search

**Files:**
- Modify: `xmpd/providers/ytmusic.py`
- Test: `tests/test_providers_ytmusic.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_search_returns_tracks():
    p = YTMusicProvider({"enabled": True})
    p._client = MagicMock()
    p._client.search.return_value = [
        {
            "videoId": "abc12345_-9",
            "title": "So What",
            "artists": [{"name": "Miles Davis"}],
            "album": {"name": "Kind of Blue"},
            "duration_seconds": 562,
            "thumbnails": [],
            "resultType": "song",
        },
        # Non-song results should be filtered:
        {"resultType": "album", "browseId": "abcdef"},
    ]
    tracks = p.search("miles davis", limit=10)
    assert len(tracks) == 1
    assert tracks[0].metadata.title == "So What"
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_providers_ytmusic.py::test_search_returns_tracks -v
```

- [ ] **Step 3: Implement**

```python
def search(self, query: str, limit: int = 25) -> list[Track]:
    client = self._ensure_client()
    raw_results = client.search(query, filter="songs") or []
    tracks: list[Track] = []
    for r in raw_results[:limit]:
        if r.get("resultType") and r["resultType"] != "song":
            continue
        if not r.get("videoId"):
            continue
        tracks.append(self._to_track(r))
    return tracks
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_providers_ytmusic.py::test_search_returns_tracks -v
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/ytmusic.py tests/test_providers_ytmusic.py
git commit -m "providers: YTMusicProvider.search filters to songs"
```

### Task B12: Implement YTMusicProvider.get_radio

**Files:**
- Modify: `xmpd/providers/ytmusic.py`
- Test: `tests/test_providers_ytmusic.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_get_radio_returns_radio_tracks():
    p = YTMusicProvider({"enabled": True})
    p._client = MagicMock()
    p._client.get_song_related.return_value = [
        {
            "videoId": "rad1xxxxx_-",
            "title": "Freddie Freeloader",
            "artists": [{"name": "Miles Davis"}],
            "album": {"name": "Kind of Blue"},
            "duration_seconds": 573,
            "thumbnails": [],
        }
    ]
    tracks = p.get_radio("abc12345_-9", limit=25)
    assert len(tracks) == 1
    assert tracks[0].track_id == "rad1xxxxx_-"
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_providers_ytmusic.py::test_get_radio_returns_radio_tracks -v
```

- [ ] **Step 3: Implement**

If the existing YTMusicClient builds radio playlists via `get_song_related` plus playlist tracks, follow that pattern. Adjust this implementation if existing code uses a different method:

```python
def get_radio(self, seed_track_id: str, limit: int = 25) -> list[Track]:
    client = self._ensure_client()
    raw = client.get_song_related(seed_track_id) or []
    tracks: list[Track] = []
    for r in raw[:limit]:
        if not r.get("videoId"):
            continue
        tracks.append(self._to_track(r))
    return tracks
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_providers_ytmusic.py::test_get_radio_returns_radio_tracks -v
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/ytmusic.py tests/test_providers_ytmusic.py
git commit -m "providers: YTMusicProvider.get_radio for track-seeded radio"
```

### Task B13: Implement YTMusicProvider.like / dislike / unlike / get_like_state

**Files:**
- Modify: `xmpd/providers/ytmusic.py`
- Test: `tests/test_providers_ytmusic.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
def test_like_calls_rate_song_with_LIKE():
    p = YTMusicProvider({"enabled": True})
    p._client = MagicMock()
    p.like("abc12345_-9")
    p._client.rate_song.assert_called_once_with("abc12345_-9", "LIKE")


def test_dislike_calls_rate_song_with_DISLIKE():
    p = YTMusicProvider({"enabled": True})
    p._client = MagicMock()
    p.dislike("abc12345_-9")
    p._client.rate_song.assert_called_once_with("abc12345_-9", "DISLIKE")


def test_unlike_calls_rate_song_with_INDIFFERENT():
    p = YTMusicProvider({"enabled": True})
    p._client = MagicMock()
    p.unlike("abc12345_-9")
    p._client.rate_song.assert_called_once_with("abc12345_-9", "INDIFFERENT")


def test_get_like_state_uses_track_metadata_liked_field():
    p = YTMusicProvider({"enabled": True})
    p._client = MagicMock()
    # YTMusicClient.get_song does NOT return like state directly; existing
    # ytmpd code reads it from search/library responses. For now, query
    # via get_song_lyrics or another endpoint that returns rating.
    # If the existing implementation uses a specific call, mirror it here:
    p._client.get_song.return_value = {"videoDetails": {"likeStatus": "LIKE"}}
    assert p.get_like_state("abc12345_-9") is True
    p._client.get_song.return_value = {"videoDetails": {"likeStatus": "INDIFFERENT"}}
    assert p.get_like_state("abc12345_-9") is False
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_providers_ytmusic.py -v 2>&1 | tail -20
```

- [ ] **Step 3: Implement**

```python
def like(self, track_id: str) -> None:
    self._ensure_client().rate_song(track_id, "LIKE")

def dislike(self, track_id: str) -> None:
    self._ensure_client().rate_song(track_id, "DISLIKE")

def unlike(self, track_id: str) -> None:
    self._ensure_client().rate_song(track_id, "INDIFFERENT")

def get_like_state(self, track_id: str) -> bool:
    raw = self._ensure_client().get_song(track_id) or {}
    return raw.get("videoDetails", {}).get("likeStatus") == "LIKE"
```

If the existing rating module uses different YTMusicClient methods, mirror those here. The tests above describe the contract; implementation details follow existing conventions.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_providers_ytmusic.py -v 2>&1 | tail -20
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/ytmusic.py tests/test_providers_ytmusic.py
git commit -m "providers: YTMusicProvider rating methods (like/dislike/unlike/get_like_state)"
```

### Task B14: Implement YTMusicProvider.report_play

**Files:**
- Modify: `xmpd/providers/ytmusic.py`
- Test: `tests/test_providers_ytmusic.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_report_play_below_threshold_is_noop():
    p = YTMusicProvider({"enabled": True})
    p._client = MagicMock()
    # Per spec, threshold is enforced upstream by history_reporter, not here.
    # The provider just calls the API. Verify the call.
    p.report_play("abc12345_-9", duration_seconds=120)
    p._client.add_history_item.assert_called_once_with("abc12345_-9")
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_providers_ytmusic.py::test_report_play_below_threshold_is_noop -v
```

- [ ] **Step 3: Implement**

```python
def report_play(self, track_id: str, duration_seconds: int) -> None:
    """Report a play to YT Music history. Best-effort; logs on failure."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        self._ensure_client().add_history_item(track_id)
    except Exception as e:
        logger.warning(f"YT history report failed for {track_id}: {e}")
```

If the existing history reporter calls a different method on YTMusicClient (e.g. `report_play` with different args), use that name. The contract from history_reporter.py is `provider.report_play(track_id, duration_seconds)`; the provider translates to whatever the backing API needs.

- [ ] **Step 4: Run test**

```bash
pytest tests/test_providers_ytmusic.py::test_report_play_below_threshold_is_noop -v
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/ytmusic.py tests/test_providers_ytmusic.py
git commit -m "providers: YTMusicProvider.report_play with best-effort error handling"
```

### Task B15: Move cookie_extract.py to auth/ytmusic_cookie.py

**Files:**
- Rename: `xmpd/cookie_extract.py` → `xmpd/auth/ytmusic_cookie.py`

- [ ] **Step 1: git mv**

```bash
cd ~/Sync/Programs/xmpd
git mv xmpd/cookie_extract.py xmpd/auth/ytmusic_cookie.py
```

- [ ] **Step 2: Update imports across codebase**

```bash
cd ~/Sync/Programs/xmpd
find . -path ./.git -prune -o -path ./.venv -prune -o -name '*.py' -print | \
xargs sed -i \
  -e 's/from xmpd\.cookie_extract import/from xmpd.auth.ytmusic_cookie import/g' \
  -e 's/from xmpd\.cookie_extract /from xmpd.auth.ytmusic_cookie /g' \
  -e 's/import xmpd\.cookie_extract/import xmpd.auth.ytmusic_cookie/g'
```

- [ ] **Step 3: Verify**

```bash
grep -rn "cookie_extract" --include='*.py' . 2>/dev/null
```

Expected: no output.

- [ ] **Step 4: Run tests**

```bash
pytest -q 2>&1 | tail -10
```

Expected: same pass count.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "auth: move cookie_extract.py to auth/ytmusic_cookie.py"
```

### Task B16: Rename icy_proxy.py to stream_proxy.py

**Files:**
- Rename: `xmpd/icy_proxy.py` → `xmpd/stream_proxy.py`
- Class rename: `ICYProxyServer` → `StreamRedirectProxy`

- [ ] **Step 1: git mv**

```bash
cd ~/Sync/Programs/xmpd
git mv xmpd/icy_proxy.py xmpd/stream_proxy.py
```

- [ ] **Step 2: Rename class and update test file**

```bash
cd ~/Sync/Programs/xmpd
sed -i 's/\bICYProxyServer\b/StreamRedirectProxy/g' xmpd/stream_proxy.py
git mv tests/test_icy_proxy.py tests/test_stream_proxy.py
sed -i 's/\bICYProxyServer\b/StreamRedirectProxy/g; s/icy_proxy/stream_proxy/g' tests/test_stream_proxy.py
```

- [ ] **Step 3: Update imports across codebase**

```bash
cd ~/Sync/Programs/xmpd
find . -path ./.git -prune -o -path ./.venv -prune -o -name '*.py' -print | \
xargs sed -i \
  -e 's/from xmpd\.icy_proxy import ICYProxyServer/from xmpd.stream_proxy import StreamRedirectProxy/g' \
  -e 's/from xmpd\.icy_proxy /from xmpd.stream_proxy /g' \
  -e 's/import xmpd\.icy_proxy/import xmpd.stream_proxy/g' \
  -e 's/\bICYProxyServer\b/StreamRedirectProxy/g'
```

- [ ] **Step 4: Verify**

```bash
grep -rn "icy_proxy\|ICYProxyServer" --include='*.py' . 2>/dev/null
```

Expected: no output.

- [ ] **Step 5: Update log tag from `[PROXY]` to `[STREAM]` (cosmetic, optional)**

The existing `icy_proxy.py` logs with `[PROXY]` prefix. Replace with `[STREAM]` to match the renamed module. This affects log search recipes in docs:

```bash
sed -i 's/\[PROXY\]/[STREAM]/g' xmpd/stream_proxy.py
sed -i 's/\[PROXY\]/[STREAM]/g' tests/test_stream_proxy.py
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_stream_proxy.py -v 2>&1 | tail -20
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "stream_proxy: rename icy_proxy module and ICYProxyServer class

The original name was wrong: this module returns 307 redirects, no ICY
metadata is injected. StreamRedirectProxy describes what it actually does."
```

### Task B17: Replace ICY_PROXY.md with STREAM_PROXY.md

**Files:**
- Create: `docs/STREAM_PROXY.md`
- (Already deleted in Plan 1: `docs/ICY_PROXY.md`)

- [ ] **Step 1: Write the new doc**

Create `docs/STREAM_PROXY.md`:

```markdown
# Stream Redirect Proxy — Technical Documentation

## Overview

`xmpd/stream_proxy.py` runs a small aiohttp server that resolves and serves
playable URLs for tracks listed in MPD playlists. Each playlist entry is
`http://localhost:<port>/proxy/<provider>/<track_id>`. When MPD requests a
track, the proxy looks up the (provider, track_id) in the track store,
refreshes the upstream URL if expired, and returns an HTTP 307 redirect to
the resolved upstream URL. MPD then streams directly from upstream.

The previous name `ICYProxyServer` was wrong: this module does NOT inject
ICY metadata. MPD reads track metadata from playlist files (XSPF tags or
m3u `#EXTINF` lines), not from headers.

## Architecture

```
        sync engine            stream proxy
            |                      |
            v                      v
    +----------------+      +----------------+
    |  TrackStore    |<---->| StreamRedirect |
    |  (provider,id) |      |   Proxy        |
    +----------------+      +----------------+
                                   ^
                                   |
                              MPD requests:
                              GET /proxy/yt/<id>
                              GET /proxy/tidal/<id>
                                   |
                                   v
                              HTTP 307 -> upstream URL
```

## URL pattern

`/proxy/<provider>/<track_id>`

- `<provider>` is one of the registered enabled providers (`yt`, `tidal`).
- `<track_id>` matches the per-provider regex:
  - YT: `^[A-Za-z0-9_-]{11}$`
  - Tidal: `^\d{1,20}$`

Bad provider returns HTTP 404. Bad track_id format returns HTTP 400.

## Refresh logic

Each track-store row has an `updated_at` timestamp. On request:

1. Lookup row.
2. If `time.time() - updated_at > stream_cache_hours`, call
   `provider.resolve_stream(track_id)` to get a fresh URL.
3. Update the row with the new URL.
4. Return HTTP 307 to the (possibly fresh) URL.

`stream_cache_hours` is per-provider. YT defaults 5h (URLs expire ~6h on
YouTube). Tidal defaults 1h (TTL is shorter and the implementing AI tunes
this during integration).

## Error handling

- Missing track in store: 404
- Bad provider: 404
- Bad track_id format: 400
- Resolution failure: 502
- Concurrent connection limit reached: 503
```

- [ ] **Step 2: Run sanity check**

```bash
ls docs/STREAM_PROXY.md
```

Expected: file exists.

- [ ] **Step 3: Commit**

```bash
git add docs/STREAM_PROXY.md
git commit -m "docs: add STREAM_PROXY.md documenting the redirect-proxy behavior"
```

### Task B18: Track store schema migration with PRAGMA user_version

**Files:**
- Modify: `xmpd/track_store.py`
- Test: `tests/test_track_store.py`

- [ ] **Step 1: Write failing test for schema migration**

Append to `tests/test_track_store.py`:

```python
import sqlite3


def _create_old_schema_db(path):
    conn = sqlite3.connect(str(path))
    conn.executescript('''
        CREATE TABLE tracks (
            video_id TEXT PRIMARY KEY,
            stream_url TEXT,
            title TEXT NOT NULL,
            artist TEXT,
            updated_at REAL NOT NULL
        );
        INSERT INTO tracks VALUES ('abc12345_-9', 'http://example/a', 'So What', 'Miles Davis', 1700000000.0);
    ''')
    conn.commit()
    conn.close()


def test_migration_preserves_existing_yt_data(tmp_path):
    db_path = tmp_path / "track_mapping.db"
    _create_old_schema_db(db_path)
    from xmpd.track_store import TrackStore
    store = TrackStore(str(db_path))
    # The migration must add provider column with default 'yt' for existing rows.
    track = store.get_track(provider="yt", track_id="abc12345_-9")
    assert track is not None
    assert track["title"] == "So What"
    assert track["artist"] == "Miles Davis"


def test_migration_adds_album_duration_arturl_columns(tmp_path):
    db_path = tmp_path / "track_mapping.db"
    _create_old_schema_db(db_path)
    from xmpd.track_store import TrackStore
    store = TrackStore(str(db_path))
    track = store.get_track(provider="yt", track_id="abc12345_-9")
    assert "album" in track
    assert "duration_seconds" in track
    assert "art_url" in track
    assert track["album"] is None  # nullable, no value for old rows
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_track_store.py -v 2>&1 | tail -10
```

Expected: failures (TrackStore.get_track signature changed; migration not implemented).

- [ ] **Step 3: Implement migration in `xmpd/track_store.py`**

Modify the existing TrackStore to:
- Add a `_run_migrations(conn)` helper that uses PRAGMA user_version
- Migration 1: add `provider TEXT NOT NULL DEFAULT 'yt'`, rename `video_id` to `track_id`, add new columns, recreate compound unique index
- Update `get_track`, `add_track`, `update_stream_url` to take `provider` and `track_id` separately

Replace the existing class with the migration-aware version. Key shape:

```python
import sqlite3
import time
from pathlib import Path
from typing import Any

CURRENT_SCHEMA_VERSION = 1


class TrackStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = str(Path(db_path).expanduser())
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            self._run_migrations(conn)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        cur = conn.execute("PRAGMA user_version")
        version = cur.fetchone()[0]
        if version >= CURRENT_SCHEMA_VERSION:
            return

        # Detect whether we're starting from a v0 (old ytmpd) DB or a fresh DB.
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tracks'"
        )
        existing = cur.fetchone()

        if existing is None:
            # Fresh DB: create v1 schema directly.
            conn.executescript('''
                CREATE TABLE tracks (
                    provider TEXT NOT NULL,
                    track_id TEXT NOT NULL,
                    stream_url TEXT,
                    title TEXT NOT NULL,
                    artist TEXT,
                    album TEXT,
                    duration_seconds INTEGER,
                    art_url TEXT,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (provider, track_id)
                );
            ''')
        else:
            # Existing v0 DB: in-place migration.
            conn.executescript('''
                ALTER TABLE tracks RENAME COLUMN video_id TO track_id;
                ALTER TABLE tracks ADD COLUMN provider TEXT NOT NULL DEFAULT 'yt';
                ALTER TABLE tracks ADD COLUMN album TEXT;
                ALTER TABLE tracks ADD COLUMN duration_seconds INTEGER;
                ALTER TABLE tracks ADD COLUMN art_url TEXT;
            ''')
            # SQLite doesn't allow modifying primary key; the existing PK
            # (track_id alone) is fine semantically because old rows were
            # all yt and 11-char IDs. Add a unique index for the compound
            # key for future inserts.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS tracks_provider_track_id_idx "
                "ON tracks(provider, track_id)"
            )

        conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
        conn.commit()

    def get_track(self, provider: str, track_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM tracks WHERE provider=? AND track_id=?",
                (provider, track_id),
            ).fetchone()
            return dict(row) if row else None

    def add_track(
        self,
        provider: str,
        track_id: str,
        stream_url: str | None,
        title: str,
        artist: str | None = None,
        album: str | None = None,
        duration_seconds: int | None = None,
        art_url: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute('''
                INSERT INTO tracks
                  (provider, track_id, stream_url, title, artist, album,
                   duration_seconds, art_url, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(provider, track_id) DO UPDATE SET
                  stream_url=excluded.stream_url,
                  title=excluded.title,
                  artist=excluded.artist,
                  album=excluded.album,
                  duration_seconds=excluded.duration_seconds,
                  art_url=excluded.art_url,
                  updated_at=excluded.updated_at
            ''', (provider, track_id, stream_url, title, artist, album,
                  duration_seconds, art_url, time.time()))
            conn.commit()

    def update_stream_url(self, provider: str, track_id: str, stream_url: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE tracks SET stream_url=?, updated_at=? "
                "WHERE provider=? AND track_id=?",
                (stream_url, time.time(), provider, track_id),
            )
            conn.commit()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_track_store.py -v 2>&1 | tail -15
```

Expected: the new tests pass; existing tests may fail because their signatures use `video_id` instead of `(provider, track_id)`. Update the existing tests in the same edit to use the new API (e.g. `store.get_track(provider="yt", track_id="abc12345_-9")` everywhere).

- [ ] **Step 5: Update existing test signatures**

```bash
cd ~/Sync/Programs/xmpd
# manually inspect tests/test_track_store.py and update all calls.
# Pattern: store.add_track("vid", ...) -> store.add_track("yt", "vid", ...)
# Pattern: store.get_track("vid") -> store.get_track("yt", "vid")
```

Apply by hand or with targeted sed. Re-run tests until all pass.

```bash
pytest tests/test_track_store.py -v 2>&1 | tail -15
```

- [ ] **Step 6: Commit**

```bash
git add xmpd/track_store.py tests/test_track_store.py
git commit -m "track_store: compound (provider, track_id) key with v1 migration"
```

### Task B19: Update stream_proxy to route /proxy/<provider>/<id>

**Files:**
- Modify: `xmpd/stream_proxy.py`
- Test: `tests/test_stream_proxy.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_stream_proxy.py`:

```python
import asyncio
from unittest.mock import MagicMock, AsyncMock
import pytest


@pytest.fixture
def store_with_yt(tmp_path):
    from xmpd.track_store import TrackStore
    db = tmp_path / "tm.db"
    store = TrackStore(str(db))
    store.add_track("yt", "abc12345_-9", "http://example/a", "So What", "Miles Davis")
    return store


@pytest.mark.asyncio
async def test_proxy_route_recognizes_yt_provider(store_with_yt, aiohttp_client):
    from xmpd.stream_proxy import StreamRedirectProxy
    proxy = StreamRedirectProxy(store_with_yt, host="localhost", port=0)
    client = await aiohttp_client(proxy.app)
    resp = await client.get("/proxy/yt/abc12345_-9", allow_redirects=False)
    assert resp.status == 307
    assert "example/a" in resp.headers.get("Location", "")


@pytest.mark.asyncio
async def test_proxy_rejects_unknown_provider(store_with_yt, aiohttp_client):
    from xmpd.stream_proxy import StreamRedirectProxy
    proxy = StreamRedirectProxy(store_with_yt, host="localhost", port=0)
    client = await aiohttp_client(proxy.app)
    resp = await client.get("/proxy/spotify/anything", allow_redirects=False)
    assert resp.status == 404


@pytest.mark.asyncio
async def test_proxy_rejects_bad_yt_id_format(store_with_yt, aiohttp_client):
    from xmpd.stream_proxy import StreamRedirectProxy
    proxy = StreamRedirectProxy(store_with_yt, host="localhost", port=0)
    client = await aiohttp_client(proxy.app)
    resp = await client.get("/proxy/yt/notavalidid", allow_redirects=False)
    assert resp.status == 400
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_stream_proxy.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Update route shape in stream_proxy.py**

Modify `StreamRedirectProxy`:
- Route: `self.app.router.add_get("/proxy/{provider}/{track_id}", self._handle_proxy_request)`
- In `_handle_proxy_request`, extract `provider` from `request.match_info`. Validate against a known set (`{"yt", "tidal"}`); 404 on unknown.
- Per-provider regex validation. Define module-level constants:
  ```python
  PROVIDER_TRACK_ID_PATTERNS = {
      "yt": re.compile(r"^[A-Za-z0-9_-]{11}$"),
      "tidal": re.compile(r"^\d{1,20}$"),
  }
  ```
- Lookup with `self.track_store.get_track(provider=provider, track_id=track_id)`.

Apply incrementally; the rest of the method (refresh logic, redirect) stays the same.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_stream_proxy.py -v 2>&1 | tail -15
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add xmpd/stream_proxy.py tests/test_stream_proxy.py
git commit -m "stream_proxy: route /proxy/<provider>/<track_id> with per-provider validation"
```

### Task B20: Provider-aware sync engine

**Files:**
- Modify: `xmpd/sync_engine.py`
- Test: `tests/test_sync_engine.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_sync_engine.py`:

```python
def test_sync_engine_iterates_over_enabled_providers():
    from xmpd.sync_engine import SyncEngine
    yt = MagicMock()
    yt.name = "yt"
    yt.is_enabled.return_value = True
    yt.is_authenticated.return_value = True
    yt.list_playlists.return_value = []
    yt.get_favorites.return_value = []

    tidal = MagicMock()
    tidal.name = "tidal"
    tidal.is_enabled.return_value = True
    tidal.is_authenticated.return_value = True
    tidal.list_playlists.return_value = []
    tidal.get_favorites.return_value = []

    engine = SyncEngine(
        registry={"yt": yt, "tidal": tidal},
        config={"playlist_prefix": {"yt": "YT: ", "tidal": "TD: "}},
        mpd_client=MagicMock(),
        track_store=MagicMock(),
    )
    result = engine.sync_all()
    yt.list_playlists.assert_called_once()
    tidal.list_playlists.assert_called_once()
    assert result.success is True
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_sync_engine.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Refactor SyncEngine to take a registry**

Modify `xmpd/sync_engine.py` so `SyncEngine.__init__` accepts `registry: dict[str, Provider]` instead of a single YTMusicClient. The main `sync_all()` (or `sync()`) method iterates over `registry.values()` and runs the per-provider playlist sync inside a try/except so one provider's failure doesn't break others.

Concretely:

```python
class SyncEngine:
    def __init__(
        self,
        registry: "dict[str, Provider]",
        config: dict,
        mpd_client,
        track_store,
    ) -> None:
        self.registry = registry
        self.config = config
        self.mpd_client = mpd_client
        self.track_store = track_store

    def sync_all(self) -> SyncResult:
        errors: list[str] = []
        playlists_synced = 0
        playlists_failed = 0
        tracks_added = 0

        for provider in self.registry.values():
            if not provider.is_authenticated():
                logger.warning(f"{provider.name} not authenticated; skipping sync")
                continue
            try:
                p_synced, p_failed, p_tracks = self._sync_provider(provider)
                playlists_synced += p_synced
                playlists_failed += p_failed
                tracks_added += p_tracks
            except Exception as e:
                errors.append(f"{provider.name}: {_truncate_error(e)}")
                logger.exception(f"Sync failed for provider {provider.name}")

        return SyncResult(
            success=not errors,
            playlists_synced=playlists_synced,
            playlists_failed=playlists_failed,
            tracks_added=tracks_added,
            tracks_failed=0,
            duration_seconds=0.0,
            errors=errors,
        )

    def _sync_provider(self, provider) -> tuple[int, int, int]:
        prefix = self.config.get("playlist_prefix", {}).get(provider.name, f"{provider.name.upper()}: ")
        playlists = provider.list_playlists()
        synced = 0
        failed = 0
        tracks_added = 0
        for pl in playlists:
            try:
                tracks = provider.get_playlist_tracks(pl.playlist_id)
                self._write_playlist(provider, pl, tracks, prefix)
                synced += 1
                tracks_added += len(tracks)
            except Exception:
                failed += 1
                logger.exception(f"Playlist sync failed: {provider.name}:{pl.playlist_id}")
        return synced, failed, tracks_added

    def _write_playlist(self, provider, pl, tracks, prefix):
        # delegates to existing m3u/xspf writer with provider info
        ...
```

(Adjust to fit existing SyncEngine internals.)

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_sync_engine.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/sync_engine.py tests/test_sync_engine.py
git commit -m "sync_engine: iterate over enabled providers via registry"
```

### Task B21: Provider-aware proxy URL builder

**Files:**
- Modify: `xmpd/mpd_client.py`
- Modify: `xmpd/xspf_generator.py`
- Test: `tests/test_mpd_client.py`, `tests/test_xspf_generator.py`

- [ ] **Step 1: Add helper function and write tests**

Create a helper in `xmpd/stream_proxy.py` (since the proxy owns the URL shape):

```python
def build_proxy_url(provider: str, track_id: str, *, host: str = "localhost", port: int = 8080) -> str:
    """Build a proxy URL for an MPD playlist entry."""
    return f"http://{host}:{port}/proxy/{provider}/{track_id}"
```

Add a test in `tests/test_stream_proxy.py`:

```python
def test_build_proxy_url():
    from xmpd.stream_proxy import build_proxy_url
    url = build_proxy_url("yt", "abc12345_-9", host="localhost", port=8080)
    assert url == "http://localhost:8080/proxy/yt/abc12345_-9"
    url2 = build_proxy_url("tidal", "12345", host="localhost", port=9000)
    assert url2 == "http://localhost:9000/proxy/tidal/12345"
```

- [ ] **Step 2: Run test, expect pass after adding helper**

```bash
pytest tests/test_stream_proxy.py::test_build_proxy_url -v
```

- [ ] **Step 3: Replace inline URL construction in mpd_client.py and xspf_generator.py**

Search for the existing string `f"http://{proxy_config['host']}:{proxy_config['port']}/proxy/{track.video_id}"` and similar patterns. Replace with `build_proxy_url(track.provider, track.track_id, host=proxy_config['host'], port=proxy_config['port'])`.

```bash
grep -n 'proxy.*/proxy/' xmpd/mpd_client.py xmpd/xspf_generator.py
```

Update each match by hand, since context matters.

- [ ] **Step 4: Run all tests**

```bash
pytest -q 2>&1 | tail -10
```

Expected: same pass count as baseline; mpd_client / xspf tests now use the new URL pattern.

- [ ] **Step 5: Commit**

```bash
git add xmpd/stream_proxy.py xmpd/mpd_client.py xmpd/xspf_generator.py tests/
git commit -m "stream_proxy: add build_proxy_url helper; switch mpd_client and xspf_generator to it"
```

### Task B22: Provider-aware history reporter

**Files:**
- Modify: `xmpd/history_reporter.py`
- Test: `tests/test_history_*.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_history_integration.py` (or create a new file):

```python
def test_history_reporter_dispatches_to_correct_provider(monkeypatch):
    from xmpd.history_reporter import HistoryReporter
    yt = MagicMock(name="yt_provider")
    yt.name = "yt"
    tidal = MagicMock(name="tidal_provider")
    tidal.name = "tidal"
    registry = {"yt": yt, "tidal": tidal}

    # Imagine the reporter has a method that takes the current proxy URL
    # and dispatches to the matching provider.
    reporter = HistoryReporter(
        registry=registry,
        config={"min_play_seconds": 30},
        mpd_client=MagicMock(),
    )
    reporter._report_play_for_url("http://localhost:8080/proxy/yt/abc12345_-9", 60)
    yt.report_play.assert_called_once_with("abc12345_-9", 60)
    tidal.report_play.assert_not_called()

    reporter._report_play_for_url("http://localhost:8080/proxy/tidal/12345", 90)
    tidal.report_play.assert_called_once_with("12345", 90)
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_history_integration.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement provider dispatch**

In `xmpd/history_reporter.py`, add:

```python
import re

PROXY_URL_PATTERN = re.compile(r"/proxy/(?P<provider>\w+)/(?P<track_id>[^/?#]+)")


class HistoryReporter:
    def __init__(self, registry: "dict[str, Provider]", config: dict, mpd_client) -> None:
        self.registry = registry
        self.config = config
        self.mpd_client = mpd_client

    def _report_play_for_url(self, url: str, duration_seconds: int) -> None:
        m = PROXY_URL_PATTERN.search(url)
        if not m:
            return
        provider_name = m.group("provider")
        track_id = m.group("track_id")
        provider = self.registry.get(provider_name)
        if provider is None:
            return
        if duration_seconds < self.config.get("min_play_seconds", 30):
            return
        provider.report_play(track_id, duration_seconds)
```

Adapt to the existing HistoryReporter loop structure.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_history_integration.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/history_reporter.py tests/test_history_integration.py
git commit -m "history_reporter: dispatch report_play to provider matching the proxy URL"
```

### Task B23: Provider-aware rating module and CLI

**Files:**
- Modify: `xmpd/rating.py`
- Modify: `bin/xmpctl`
- Test: `tests/test_rating.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_rating.py`:

```python
def test_like_dispatches_via_current_track_provider(monkeypatch):
    from xmpd.rating import RatingService
    yt = MagicMock(); yt.name = "yt"
    tidal = MagicMock(); tidal.name = "tidal"
    registry = {"yt": yt, "tidal": tidal}
    mpd = MagicMock()
    mpd.current_track_url.return_value = "http://localhost:8080/proxy/tidal/12345"
    svc = RatingService(registry=registry, mpd_client=mpd)
    svc.like_current()
    tidal.like.assert_called_once_with("12345")
    yt.like.assert_not_called()
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_rating.py::test_like_dispatches_via_current_track_provider -v
```

- [ ] **Step 3: Implement RatingService dispatch**

In `xmpd/rating.py`, refactor existing rating code into a `RatingService` class that:
1. Takes `registry` and `mpd_client`.
2. `_resolve_provider_and_id()` reads MPD current track, parses the proxy URL, returns `(provider, track_id)`.
3. `like_current()`, `dislike_current()`, `unlike_current()` each call the right method on the resolved provider.

```python
import re

PROXY_URL_PATTERN = re.compile(r"/proxy/(?P<provider>\w+)/(?P<track_id>[^/?#]+)")


class RatingService:
    def __init__(self, registry, mpd_client) -> None:
        self.registry = registry
        self.mpd_client = mpd_client

    def _resolve(self) -> tuple[str, str] | None:
        url = self.mpd_client.current_track_url() or ""
        m = PROXY_URL_PATTERN.search(url)
        if not m:
            return None
        return m.group("provider"), m.group("track_id")

    def like_current(self) -> None:
        resolved = self._resolve()
        if not resolved:
            return
        provider_name, track_id = resolved
        provider = self.registry.get(provider_name)
        if provider:
            provider.like(track_id)

    def dislike_current(self) -> None:
        resolved = self._resolve()
        if not resolved:
            return
        provider_name, track_id = resolved
        provider = self.registry.get(provider_name)
        if provider:
            provider.dislike(track_id)

    def unlike_current(self) -> None:
        resolved = self._resolve()
        if not resolved:
            return
        provider_name, track_id = resolved
        provider = self.registry.get(provider_name)
        if provider:
            provider.unlike(track_id)
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_rating.py::test_like_dispatches_via_current_track_provider -v
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/rating.py tests/test_rating.py
git commit -m "rating: RatingService dispatches like/dislike/unlike via current track's provider"
```

### Task B24: Update daemon for provider registry construction

**Files:**
- Modify: `xmpd/daemon.py`

- [ ] **Step 1: Update daemon initialization**

Modify `XMPDaemon.__init__()` (or whatever the class is named after the rename) to:

1. Read config; build provider registry via `xmpd.providers.build_registry(config)`.
2. For each provider, log its `is_enabled()` and `is_authenticated()` state.
3. Construct SyncEngine, RatingService, HistoryReporter with the registry.
4. Construct StreamRedirectProxy with the track store; the proxy will validate provider names against its hardcoded set, or accept the registry to validate dynamically.

Concrete edits depend on the existing daemon.py shape; preserve all current threading and lifecycle behavior. The change is: where `YTMusicClient` was instantiated directly, use `registry["yt"]`. Where new components need a registry, pass it.

- [ ] **Step 2: Verify daemon still starts**

```bash
cd ~/Sync/Programs/xmpd
source .venv/bin/activate
mkdir -p ~/.config/xmpd-test
cat > ~/.config/xmpd-test/config.yaml <<'EOF'
yt:
  enabled: true
  auto_auth:
    enabled: false
  stream_cache_hours: 5
mpd_socket_path: ~/.config/mpd/socket
playlist_format: m3u
sync_interval_minutes: 30
proxy_enabled: false  # don't bind in smoke test
log_level: INFO
log_file: /tmp/xmpd-smoke.log
EOF
XMPD_CONFIG=~/.config/xmpd-test/config.yaml timeout 10 python -m xmpd 2>&1 | tail -20
```

Expected: daemon starts, logs the registry construction (one provider: yt), exits via timeout. No tracebacks.

- [ ] **Step 3: Run all tests**

```bash
pytest -q 2>&1 | tail -10
```

Expected: same pass count.

- [ ] **Step 4: Commit**

```bash
rm -rf ~/.config/xmpd-test
git add xmpd/daemon.py
git commit -m "daemon: build provider registry from config; pass to all components"
```

### Task B25: Update xmpctl auth subcommand structure

**Files:**
- Modify: `bin/xmpctl`

- [ ] **Step 1: Inspect current auth subcommand**

```bash
grep -nA 20 "def cmd_auth\|def auth\|--auto" bin/xmpctl | head -40
```

- [ ] **Step 2: Refactor to `xmpctl auth <provider>` shape**

Replace the existing `xmpctl auth --auto` argparse subparser with a positional `provider` argument:

```python
auth_parser = subparsers.add_parser("auth", help="Authenticate a provider")
auth_parser.add_argument("provider", choices=["yt", "tidal"], help="Provider to authenticate")
```

Then in the dispatch:

```python
if args.command == "auth":
    if args.provider == "yt":
        from xmpd.auth.ytmusic_cookie import run_auto_auth
        run_auto_auth(config["yt"]["auto_auth"])
    elif args.provider == "tidal":
        # Stage C will add this. For now, raise NotImplementedError.
        raise NotImplementedError("Tidal auth lands in Stage C (Task C5)")
```

- [ ] **Step 3: Verify with --help**

```bash
./bin/xmpctl auth --help
```

Expected: shows the new shape with `provider` positional.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_xmpctl.py -v 2>&1 | tail -10
```

Expected: test_xmpctl tests still pass; if they referenced `--auto`, update them.

- [ ] **Step 5: Commit**

```bash
git add bin/xmpctl tests/test_xmpctl.py
git commit -m "xmpctl: switch auth to 'xmpctl auth <provider>' subcommand shape"
```

### Task B26: Stage B verification + summary

**Files:**
- Verify: full suite, daemon start

- [ ] **Step 1: Run full pytest**

```bash
cd ~/Sync/Programs/xmpd
source .venv/bin/activate
pytest -q 2>&1 | tail -15
```

Expected: all tests pass.

- [ ] **Step 2: Smoke-test daemon**

```bash
mkdir -p ~/.config/xmpd-test
cat > ~/.config/xmpd-test/config.yaml <<'EOF'
yt:
  enabled: true
  auto_auth:
    enabled: false
  stream_cache_hours: 5
mpd_socket_path: ~/.config/mpd/socket
playlist_format: m3u
sync_interval_minutes: 30
proxy_enabled: false
log_level: INFO
log_file: /tmp/xmpd-smoke.log
EOF
XMPD_CONFIG=~/.config/xmpd-test/config.yaml timeout 10 python -m xmpd 2>&1 | tail -20
rm -rf ~/.config/xmpd-test
```

Expected: clean startup, no tracebacks.

- [ ] **Step 3: Push Stage B work to origin**

```bash
git push origin main
```

Stage B complete: provider abstraction extracted, all existing YT functionality flowing through the new Protocol with no behavior change.

---

## Stage C — Tidal provider

Outcome of stage C: Tidal works alongside YT. `xmpctl auth tidal` succeeds, `tidal.enabled: true` in config makes the daemon sync Tidal playlists, search/radio/like/dislike/history all work for Tidal tracks.

### Task C1: Add tidalapi dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add tidalapi to dependencies**

Edit `pyproject.toml`'s `[project]` `dependencies` list (or wherever runtime deps live). Add:

```toml
"tidalapi>=0.7.0,<1.0.0",
```

The version pin is approximate; the implementing AI checks `pip index versions tidalapi` for the latest stable as of execution time, pins compatible-release-clause-style.

- [ ] **Step 2: Install**

```bash
cd ~/Sync/Programs/xmpd
source .venv/bin/activate
pip install -e ".[dev]"
python -c "import tidalapi; print(tidalapi.__version__)"
```

Expected: prints the installed version.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add tidalapi for Tidal provider integration"
```

### Task C2: Implement tidal_oauth.py with clipboard helper

**Files:**
- Create: `xmpd/auth/tidal_oauth.py`
- Test: `tests/test_tidal_oauth.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_tidal_oauth.py`:

```python
"""Tests for Tidal OAuth flow and clipboard helper."""

from unittest.mock import MagicMock, patch
from xmpd.auth.tidal_oauth import (
    copy_to_clipboard,
    load_session_from_disk,
    save_session_to_disk,
)


def test_copy_to_clipboard_uses_wl_copy_when_available(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr("shutil.which", lambda c: "/usr/bin/wl-copy" if c == "wl-copy" else None)
    monkeypatch.setattr("subprocess.run", fake_run)

    ok = copy_to_clipboard("https://link.tidal.com/ABCDE")
    assert ok is True
    assert any("wl-copy" in c[0] for c in calls)


def test_copy_to_clipboard_falls_back_to_xclip(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        result = MagicMock()
        result.returncode = 0
        return result

    def fake_which(c):
        if c == "wl-copy":
            return None
        if c == "xclip":
            return "/usr/bin/xclip"
        return None

    monkeypatch.setattr("shutil.which", fake_which)
    monkeypatch.setattr("subprocess.run", fake_run)

    ok = copy_to_clipboard("https://link.tidal.com/ABCDE")
    assert ok is True
    assert any("xclip" in c[0] for c in calls)


def test_copy_to_clipboard_returns_false_when_no_tool(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda c: None)
    ok = copy_to_clipboard("anything")
    assert ok is False


def test_save_and_load_session_round_trip(tmp_path):
    path = tmp_path / "tidal_session.json"
    save_session_to_disk(
        path,
        token_type="Bearer",
        access_token="atk",
        refresh_token="rtk",
        expiry_time="2026-12-31T00:00:00",
    )
    data = load_session_from_disk(path)
    assert data["access_token"] == "atk"
    assert data["refresh_token"] == "rtk"
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_tidal_oauth.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement xmpd/auth/tidal_oauth.py**

```python
"""Tidal OAuth device flow + clipboard helper.

Daemon-mode behavior: never block on input. If no token exists, log a
warning and skip Tidal sync. The interactive setup runs only via
`xmpctl auth tidal`.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

import tidalapi

logger = logging.getLogger(__name__)

DEFAULT_SESSION_PATH = Path("~/.config/xmpd/tidal_session.json").expanduser()


class TidalAuthRequired(Exception):
    """Raised when no valid Tidal session exists."""


def copy_to_clipboard(text: str) -> bool:
    """Copy `text` to the system clipboard. Returns True on success.

    Tries Wayland (`wl-copy`) first, falls back to X11 (`xclip`). Returns
    False if neither is installed.
    """
    if shutil.which("wl-copy"):
        try:
            subprocess.run(["wl-copy"], input=text.encode(), check=True)
            return True
        except subprocess.CalledProcessError:
            return False
    if shutil.which("xclip"):
        try:
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
            return True
        except subprocess.CalledProcessError:
            return False
    return False


def save_session_to_disk(
    path: Path,
    *,
    token_type: str,
    access_token: str,
    refresh_token: str,
    expiry_time: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "token_type": token_type,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expiry_time": expiry_time,
    }))


def load_session_from_disk(path: Path = DEFAULT_SESSION_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise TidalAuthRequired(f"No Tidal session file at {path}")
    return json.loads(path.read_text())


def session_for_daemon(path: Path = DEFAULT_SESSION_PATH) -> tidalapi.Session:
    """Load a session for non-interactive use; raises TidalAuthRequired if missing."""
    data = load_session_from_disk(path)
    session = tidalapi.Session()
    session.load_oauth_session(
        data["token_type"],
        data["access_token"],
        data["refresh_token"],
        data["expiry_time"],
    )
    if not session.check_login():
        raise TidalAuthRequired("Tidal session exists but is invalid; re-run `xmpctl auth tidal`.")
    return session


def run_interactive_login(path: Path = DEFAULT_SESSION_PATH) -> None:
    """Run the OAuth device flow, copying the auth URL to clipboard.

    Called by `xmpctl auth tidal`. Blocks until login completes or times out.
    """
    session = tidalapi.Session()
    login, future = session.login_oauth()

    auth_url = f"https://{login.verification_uri_complete}"
    print(f"Open this URL in your browser to authorize xmpd:")
    print(f"  {auth_url}")
    if copy_to_clipboard(auth_url):
        print("(URL copied to clipboard.)")
    else:
        print("(Install wl-copy or xclip for automatic clipboard support.)")
    print()
    print("Waiting for authorization...")

    future.result()  # blocks until login or timeout

    save_session_to_disk(
        path,
        token_type=session.token_type,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expiry_time=session.expiry_time.isoformat(),
    )
    print(f"Tidal session saved to {path}.")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_tidal_oauth.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/auth/tidal_oauth.py tests/test_tidal_oauth.py
git commit -m "auth: tidal OAuth device flow with clipboard helper"
```

### Task C3: Scaffold TidalProvider

**Files:**
- Create: `xmpd/providers/tidal.py`
- Test: `tests/test_providers_tidal.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_providers_tidal.py`:

```python
"""Tests for TidalProvider — wraps tidalapi.Session."""

from unittest.mock import MagicMock, patch

from xmpd.providers.base import Provider
from xmpd.providers.tidal import TidalProvider


def test_tidal_provider_satisfies_protocol():
    config = {"enabled": True, "quality_ceiling": "HI_RES_LOSSLESS"}
    p = TidalProvider(config)
    assert isinstance(p, Provider)
    assert p.name == "tidal"


def test_tidal_provider_is_enabled():
    p = TidalProvider({"enabled": True})
    assert p.is_enabled() is True
    p2 = TidalProvider({"enabled": False})
    assert p2.is_enabled() is False


def test_tidal_provider_is_authenticated_false_when_no_session_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "xmpd.providers.tidal.DEFAULT_SESSION_PATH",
        tmp_path / "nonexistent.json",
    )
    p = TidalProvider({"enabled": True})
    assert p.is_authenticated() is False
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_providers_tidal.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement scaffold**

Create `xmpd/providers/tidal.py`:

```python
"""TidalProvider — wraps tidalapi.Session to satisfy the Provider Protocol."""

from __future__ import annotations

import logging
from typing import Any

import tidalapi

from xmpd.auth.tidal_oauth import (
    DEFAULT_SESSION_PATH,
    TidalAuthRequired,
    session_for_daemon,
)
from xmpd.providers.base import Playlist, Provider, Track, TrackMetadata

logger = logging.getLogger(__name__)


_QUALITY_LEVELS = {
    "LOW": tidalapi.Quality.low_320k,           # AAC 96 kbps (note: confusing name)
    "HIGH": tidalapi.Quality.high_320k,         # AAC 320 kbps
    "LOSSLESS": tidalapi.Quality.high_lossless, # FLAC 16/44.1
    "HI_RES_LOSSLESS": tidalapi.Quality.hi_res_lossless,
}


class TidalProvider:
    name = "tidal"

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._session: tidalapi.Session | None = None
        self._favorites_cache: set[str] | None = None  # for fast get_like_state

    def is_enabled(self) -> bool:
        return bool(self._config.get("enabled", False))

    def is_authenticated(self) -> bool:
        return DEFAULT_SESSION_PATH.is_file()

    def _ensure_session(self) -> tidalapi.Session:
        if self._session is None:
            self._session = session_for_daemon()
        return self._session
```

Verify the actual `tidalapi.Quality` enum names match what's in the installed version. If they differ (the lib renames its enum periodically), update the mapping.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_providers_tidal.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/tidal.py tests/test_providers_tidal.py
git commit -m "providers: scaffold TidalProvider satisfying Protocol"
```

### Task C4: Implement TidalProvider.list_playlists

**Files:**
- Modify: `xmpd/providers/tidal.py`
- Test: `tests/test_providers_tidal.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_providers_tidal.py`:

```python
def test_list_playlists_includes_own_and_favorited():
    p = TidalProvider({"enabled": True, "sync_favorited_playlists": True})
    fake_session = MagicMock()
    own = MagicMock()
    own.id = "p-own"; own.name = "My Mix"; own.num_tracks = 25
    favorited = MagicMock()
    favorited.id = "p-fav"; favorited.name = "Tidal Rising"; favorited.num_tracks = 50
    fake_session.user.playlists.return_value = [own]
    fake_session.user.favorites.playlists.return_value = [favorited]
    fake_session.user.favorites.tracks.return_value = [MagicMock(), MagicMock()]
    p._session = fake_session
    pls = p.list_playlists()
    names = sorted(pl.name for pl in pls)
    assert "My Mix" in names
    assert "Tidal Rising" in names
    assert "Favorites" in names  # synthesized favorites pseudo-playlist
    favs = next(pl for pl in pls if pl.is_favorites)
    assert favs.track_count == 2


def test_list_playlists_skips_favorited_when_disabled():
    p = TidalProvider({"enabled": True, "sync_favorited_playlists": False})
    fake_session = MagicMock()
    own = MagicMock()
    own.id = "p-own"; own.name = "My Mix"; own.num_tracks = 25
    fake_session.user.playlists.return_value = [own]
    fake_session.user.favorites.tracks.return_value = []
    p._session = fake_session
    pls = p.list_playlists()
    names = sorted(pl.name for pl in pls)
    assert "Tidal Rising" not in names  # favorited playlists not pulled
    assert "My Mix" in names
    assert "Favorites" in names
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_providers_tidal.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement list_playlists**

Add to TidalProvider:

```python
def list_playlists(self) -> list[Playlist]:
    session = self._ensure_session()
    out: list[Playlist] = []

    # Own playlists (always)
    for pl in session.user.playlists():
        out.append(Playlist(
            provider="tidal",
            playlist_id=str(pl.id),
            name=pl.name,
            track_count=pl.num_tracks,
            is_owned=True,
            is_favorites=False,
        ))

    # Favorited (saved) playlists
    if self._config.get("sync_favorited_playlists", True):
        for pl in session.user.favorites.playlists():
            out.append(Playlist(
                provider="tidal",
                playlist_id=str(pl.id),
                name=pl.name,
                track_count=pl.num_tracks,
                is_owned=False,
                is_favorites=False,
            ))

    # Favorites pseudo-playlist (always)
    fav_tracks = session.user.favorites.tracks()
    out.append(Playlist(
        provider="tidal",
        playlist_id="__favorites__",
        name="Favorites",
        track_count=len(fav_tracks),
        is_owned=True,
        is_favorites=True,
    ))

    return out
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_providers_tidal.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/tidal.py tests/test_providers_tidal.py
git commit -m "providers: TidalProvider.list_playlists includes own + favorited + favorites pseudo"
```

### Task C5: Implement TidalProvider.get_playlist_tracks and get_favorites

**Files:**
- Modify: `xmpd/providers/tidal.py`
- Test: `tests/test_providers_tidal.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def _make_tidal_track(id_, title, artist_name, album_name, duration_seconds, art_url):
    t = MagicMock()
    t.id = id_
    t.name = title
    t.artist.name = artist_name
    t.album.name = album_name
    t.album.image.return_value = art_url
    t.duration = duration_seconds
    return t


def test_get_playlist_tracks_returns_tracks():
    p = TidalProvider({"enabled": True})
    fake_session = MagicMock()
    fake_pl = MagicMock()
    fake_pl.tracks.return_value = [
        _make_tidal_track(12345, "So What", "Miles Davis", "Kind of Blue", 562, "https://art")
    ]
    fake_session.playlist.return_value = fake_pl
    p._session = fake_session
    tracks = p.get_playlist_tracks("12345")
    assert len(tracks) == 1
    assert tracks[0].provider == "tidal"
    assert tracks[0].track_id == "12345"
    assert tracks[0].metadata.title == "So What"
    assert tracks[0].metadata.album == "Kind of Blue"


def test_get_favorites_returns_favorite_tracks():
    p = TidalProvider({"enabled": True})
    fake_session = MagicMock()
    fake_session.user.favorites.tracks.return_value = [
        _make_tidal_track(99, "Freddie Freeloader", "Miles Davis", "Kind of Blue", 573, "https://art2")
    ]
    p._session = fake_session
    tracks = p.get_favorites()
    assert len(tracks) == 1
    assert tracks[0].track_id == "99"
    assert tracks[0].liked is True  # favorites are inherently liked
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_providers_tidal.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement**

Add to TidalProvider:

```python
@staticmethod
def _to_track(t, *, liked: bool | None = None) -> Track:
    md = TrackMetadata(
        title=t.name,
        artist=getattr(t.artist, "name", None) if t.artist else None,
        album=getattr(t.album, "name", None) if t.album else None,
        duration_seconds=getattr(t, "duration", None),
        art_url=t.album.image(640) if t.album else None,
    )
    return Track(provider="tidal", track_id=str(t.id), metadata=md, liked=liked)


def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
    session = self._ensure_session()
    if playlist_id == "__favorites__":
        return self.get_favorites()
    pl = session.playlist(playlist_id)
    return [self._to_track(t) for t in pl.tracks()]


def get_favorites(self) -> list[Track]:
    session = self._ensure_session()
    favs = session.user.favorites.tracks()
    self._favorites_cache = {str(t.id) for t in favs}
    return [self._to_track(t, liked=True) for t in favs]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_providers_tidal.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/tidal.py tests/test_providers_tidal.py
git commit -m "providers: TidalProvider.get_playlist_tracks and get_favorites with caching"
```

### Task C6: Implement TidalProvider.resolve_stream with quality_ceiling

**Files:**
- Modify: `xmpd/providers/tidal.py`
- Test: `tests/test_providers_tidal.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_resolve_stream_uses_quality_ceiling():
    p = TidalProvider({"enabled": True, "quality_ceiling": "LOSSLESS"})
    fake_session = MagicMock()
    fake_track = MagicMock()
    fake_track.audio_quality = "HI_RES_LOSSLESS"  # available higher
    fake_track.get_url.return_value = "https://stream.example/track"
    fake_session.track.return_value = fake_track
    p._session = fake_session

    url = p.resolve_stream("12345")
    assert url.startswith("https://")
    # The provider should have requested LOSSLESS (the ceiling), not HI_RES.
    fake_track.get_url.assert_called_once()
    args, kwargs = fake_track.get_url.call_args
    quality_arg = kwargs.get("quality") or (args[0] if args else None)
    # Allow either kwarg or positional; just check the right one was used:
    assert quality_arg == tidalapi.Quality.high_lossless or quality_arg == "LOSSLESS"


def test_resolve_stream_falls_back_when_track_only_has_lower_quality():
    p = TidalProvider({"enabled": True, "quality_ceiling": "HI_RES_LOSSLESS"})
    fake_session = MagicMock()
    fake_track = MagicMock()
    fake_track.audio_quality = "HIGH"  # only HIGH available
    fake_track.get_url.return_value = "https://stream.example/track"
    fake_session.track.return_value = fake_track
    p._session = fake_session

    url = p.resolve_stream("12345")
    assert url
    fake_track.get_url.assert_called_once()
    # Should request HIGH, not HI_RES_LOSSLESS
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_providers_tidal.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement**

Add to TidalProvider:

```python
_QUALITY_ORDER = ["LOW", "HIGH", "LOSSLESS", "HI_RES_LOSSLESS"]


def _resolve_quality(self, available: str) -> "tidalapi.Quality":
    """Pick min(ceiling, available)."""
    ceiling = self._config.get("quality_ceiling", "HI_RES_LOSSLESS")
    if ceiling not in self._QUALITY_ORDER:
        ceiling = "HI_RES_LOSSLESS"
    available_idx = self._QUALITY_ORDER.index(available) if available in self._QUALITY_ORDER else 0
    ceiling_idx = self._QUALITY_ORDER.index(ceiling)
    chosen = self._QUALITY_ORDER[min(available_idx, ceiling_idx)]
    return _QUALITY_LEVELS[chosen]


def resolve_stream(self, track_id: str) -> str:
    session = self._ensure_session()
    track = session.track(track_id)
    quality = self._resolve_quality(getattr(track, "audio_quality", "LOSSLESS"))
    return track.get_url(quality=quality)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_providers_tidal.py -v 2>&1 | tail -10
```

If `tidalapi.Quality` enum values don't accept the keyword `quality=` (some versions take positional only), adjust the call. Tests should pass either way once the call shape matches the lib.

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/tidal.py tests/test_providers_tidal.py
git commit -m "providers: TidalProvider.resolve_stream picks min(ceiling, available)"
```

### Task C7: Implement TidalProvider.get_track_metadata

**Files:**
- Modify: `xmpd/providers/tidal.py`
- Test: `tests/test_providers_tidal.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_get_track_metadata_returns_track_metadata():
    p = TidalProvider({"enabled": True})
    fake_session = MagicMock()
    fake_track = _make_tidal_track(12345, "So What", "Miles Davis", "Kind of Blue", 562, "https://art")
    fake_session.track.return_value = fake_track
    p._session = fake_session
    md = p.get_track_metadata("12345")
    assert md.title == "So What"
    assert md.artist == "Miles Davis"
    assert md.duration_seconds == 562
    assert md.art_url == "https://art"
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_providers_tidal.py::test_get_track_metadata_returns_track_metadata -v
```

- [ ] **Step 3: Implement**

Add to TidalProvider:

```python
def get_track_metadata(self, track_id: str) -> TrackMetadata:
    session = self._ensure_session()
    t = session.track(track_id)
    return self._to_track(t).metadata
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_providers_tidal.py::test_get_track_metadata_returns_track_metadata -v
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/tidal.py tests/test_providers_tidal.py
git commit -m "providers: TidalProvider.get_track_metadata reuses _to_track conversion"
```

### Task C8: Implement TidalProvider.search and get_radio

**Files:**
- Modify: `xmpd/providers/tidal.py`
- Test: `tests/test_providers_tidal.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
def test_search_returns_tracks():
    p = TidalProvider({"enabled": True})
    fake_session = MagicMock()
    fake_session.search.return_value = {
        "tracks": [_make_tidal_track(1, "Track A", "Artist", "Album", 200, "https://art")]
    }
    p._session = fake_session
    results = p.search("query", limit=5)
    assert len(results) == 1
    assert results[0].track_id == "1"


def test_get_radio_returns_radio_tracks():
    p = TidalProvider({"enabled": True})
    fake_session = MagicMock()
    fake_track = MagicMock()
    fake_track.get_track_radio.return_value = [
        _make_tidal_track(2, "Radio A", "Artist", "Album", 180, "https://art")
    ]
    fake_session.track.return_value = fake_track
    p._session = fake_session
    radio = p.get_radio("12345", limit=10)
    assert len(radio) == 1
    assert radio[0].track_id == "2"
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_providers_tidal.py -v 2>&1 | tail -15
```

- [ ] **Step 3: Implement**

Add to TidalProvider:

```python
def search(self, query: str, limit: int = 25) -> list[Track]:
    session = self._ensure_session()
    results = session.search(query, models=[tidalapi.media.Track])
    raw_tracks = results.get("tracks", []) if isinstance(results, dict) else getattr(results, "tracks", [])
    return [self._to_track(t) for t in raw_tracks[:limit]]


def get_radio(self, seed_track_id: str, limit: int = 25) -> list[Track]:
    session = self._ensure_session()
    track = session.track(seed_track_id)
    radio_tracks = track.get_track_radio()
    return [self._to_track(t) for t in radio_tracks[:limit]]
```

If `tidalapi.search` returns a different shape in the installed version, adjust the parsing.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_providers_tidal.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/tidal.py tests/test_providers_tidal.py
git commit -m "providers: TidalProvider.search and get_radio"
```

### Task C9: Implement TidalProvider.like / dislike / unlike / get_like_state

**Files:**
- Modify: `xmpd/providers/tidal.py`
- Test: `tests/test_providers_tidal.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
def test_like_calls_favorites_add_track():
    p = TidalProvider({"enabled": True})
    fake_session = MagicMock()
    p._session = fake_session
    p.like("12345")
    fake_session.user.favorites.add_track.assert_called_once_with(12345)


def test_unlike_calls_favorites_remove_track():
    p = TidalProvider({"enabled": True})
    fake_session = MagicMock()
    p._session = fake_session
    p.unlike("12345")
    fake_session.user.favorites.remove_track.assert_called_once_with(12345)


def test_dislike_aliases_unlike():
    p = TidalProvider({"enabled": True})
    fake_session = MagicMock()
    p._session = fake_session
    p.dislike("12345")
    fake_session.user.favorites.remove_track.assert_called_once_with(12345)


def test_get_like_state_uses_cached_favorites_set():
    p = TidalProvider({"enabled": True})
    fake_session = MagicMock()
    fake_session.user.favorites.tracks.return_value = [
        _make_tidal_track(12345, "x", "y", "z", 1, "u")
    ]
    p._session = fake_session
    # Populating cache via get_favorites
    p.get_favorites()
    assert p.get_like_state("12345") is True
    assert p.get_like_state("99999") is False
```

- [ ] **Step 2: Run tests, expect failure**

```bash
pytest tests/test_providers_tidal.py -v 2>&1 | tail -15
```

- [ ] **Step 3: Implement**

Add to TidalProvider:

```python
def like(self, track_id: str) -> None:
    session = self._ensure_session()
    session.user.favorites.add_track(int(track_id))
    if self._favorites_cache is not None:
        self._favorites_cache.add(track_id)


def dislike(self, track_id: str) -> None:
    """Tidal has no dislike API; map to unlike per design decision."""
    self.unlike(track_id)


def unlike(self, track_id: str) -> None:
    session = self._ensure_session()
    session.user.favorites.remove_track(int(track_id))
    if self._favorites_cache is not None:
        self._favorites_cache.discard(track_id)


def get_like_state(self, track_id: str) -> bool:
    if self._favorites_cache is None:
        # Populate cache on first call.
        self.get_favorites()
    assert self._favorites_cache is not None
    return track_id in self._favorites_cache
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_providers_tidal.py -v 2>&1 | tail -15
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/tidal.py tests/test_providers_tidal.py
git commit -m "providers: TidalProvider rating methods (like/dislike/unlike/get_like_state)"
```

### Task C10: Implement TidalProvider.report_play

**Files:**
- Modify: `xmpd/providers/tidal.py`
- Test: `tests/test_providers_tidal.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_report_play_is_best_effort_and_swallows_exceptions(caplog):
    p = TidalProvider({"enabled": True})
    fake_session = MagicMock()
    fake_session.user.add_to_history.side_effect = Exception("Tidal blew up")
    p._session = fake_session
    # Must NOT raise:
    p.report_play("12345", duration_seconds=120)
    # Should log a warning:
    assert any("12345" in r.message and "Tidal" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_providers_tidal.py::test_report_play_is_best_effort_and_swallows_exceptions -v
```

- [ ] **Step 3: Implement**

Add to TidalProvider:

```python
def report_play(self, track_id: str, duration_seconds: int) -> None:
    """Report a play to Tidal's history. Best-effort; logs on failure."""
    session = self._ensure_session()
    try:
        # API name varies between tidalapi versions; check the installed lib.
        # Common candidates: session.user.add_to_history(track_id),
        # session.user.history.append(track_id), session.put(...).
        if hasattr(session.user, "add_to_history"):
            session.user.add_to_history(int(track_id))
        else:
            logger.debug(f"Tidal history reporting not available in installed tidalapi; skipped {track_id}")
    except Exception as e:
        logger.warning(f"Tidal history report failed for {track_id} ({duration_seconds}s): {e}")
```

If the exact tidalapi API differs, adapt the implementation while keeping the contract: never raise; log on failure.

- [ ] **Step 4: Run test**

```bash
pytest tests/test_providers_tidal.py::test_report_play_is_best_effort_and_swallows_exceptions -v
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/providers/tidal.py tests/test_providers_tidal.py
git commit -m "providers: TidalProvider.report_play (best-effort, never raises)"
```

### Task C11: Wire `xmpctl auth tidal` into the CLI

**Files:**
- Modify: `bin/xmpctl`
- Test: `tests/test_xmpctl.py`

- [ ] **Step 1: Update the auth dispatch**

Find the previously-stubbed `xmpctl auth tidal` branch (Task B25 left it as `NotImplementedError`). Replace with:

```python
if args.command == "auth":
    if args.provider == "yt":
        from xmpd.auth.ytmusic_cookie import run_auto_auth
        run_auto_auth(config["yt"]["auto_auth"])
    elif args.provider == "tidal":
        from xmpd.auth.tidal_oauth import run_interactive_login
        run_interactive_login()
```

- [ ] **Step 2: Test --help**

```bash
./bin/xmpctl auth --help
./bin/xmpctl auth tidal --help 2>&1 | head -10
```

Expected: both succeed; `tidal` is shown as one of the choices.

- [ ] **Step 3: Run xmpctl tests**

```bash
pytest tests/test_xmpctl.py -v 2>&1 | tail -10
```

- [ ] **Step 4: Manual test (interactive — user runs)**

Document in commit message that the implementing AI should NOT run the interactive auth as part of automated tests. The user runs it manually after Stage C is complete.

- [ ] **Step 5: Commit**

```bash
git add bin/xmpctl
git commit -m "xmpctl: wire 'xmpctl auth tidal' to interactive OAuth flow"
```

### Task C12: Per-provider stream_cache_hours in stream_proxy

**Files:**
- Modify: `xmpd/stream_proxy.py`
- Test: `tests/test_stream_proxy.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_stream_proxy.py`:

```python
def test_per_provider_stream_cache_hours_used(monkeypatch):
    from xmpd.stream_proxy import _is_url_expired_for_provider
    config = {"yt": {"stream_cache_hours": 5}, "tidal": {"stream_cache_hours": 1}}
    now = 1_700_000_000
    yt_age_4h_ago = now - 4 * 3600
    tidal_age_4h_ago = now - 4 * 3600
    monkeypatch.setattr("time.time", lambda: now)
    assert _is_url_expired_for_provider(yt_age_4h_ago, "yt", config) is False  # 5h cap
    assert _is_url_expired_for_provider(tidal_age_4h_ago, "tidal", config) is True  # 1h cap
```

- [ ] **Step 2: Run test, expect failure**

```bash
pytest tests/test_stream_proxy.py::test_per_provider_stream_cache_hours_used -v
```

- [ ] **Step 3: Implement helper and update proxy logic**

Add to `xmpd/stream_proxy.py`:

```python
import time as _time


def _is_url_expired_for_provider(updated_at: float, provider: str, config: dict) -> bool:
    cap = config.get(provider, {}).get(
        "stream_cache_hours",
        config.get("stream_cache_hours", 5),
    )
    age_hours = (_time.time() - updated_at) / 3600
    return age_hours > cap
```

Replace the existing `_is_url_expired` calls inside `_handle_proxy_request` with `_is_url_expired_for_provider(track["updated_at"], provider, self.config)`. The proxy needs the full config for this; pass it through StreamRedirectProxy's constructor.

- [ ] **Step 4: Run test**

```bash
pytest tests/test_stream_proxy.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add xmpd/stream_proxy.py tests/test_stream_proxy.py
git commit -m "stream_proxy: per-provider stream_cache_hours"
```

### Task C13: Update example config.yaml with full Tidal section

**Files:**
- Modify: `examples/config.yaml`

- [ ] **Step 1: Read current state**

```bash
cd ~/Sync/Programs/xmpd
cat examples/config.yaml
```

- [ ] **Step 2: Replace with the full layout from the spec**

Write `examples/config.yaml`:

```yaml
# xmpd configuration.
#
# Located at ~/.config/xmpd/config.yaml. Created with these defaults
# on first run.

# Per-provider configuration.
yt:
  enabled: true                   # YouTube Music sync on by default
  stream_cache_hours: 5           # YT stream URLs expire ~6h
  auto_auth:
    enabled: true                 # Refresh browser.json from Firefox cookies
    browser: firefox-dev          # "firefox" or "firefox-dev"
    container: null               # Multi-Account-Containers name, or null
    profile: null                 # null = auto-detect
    refresh_interval_hours: 12

tidal:
  enabled: false                  # Opt-in. Run `xmpctl auth tidal` first.
  stream_cache_hours: 1           # Tidal URLs expire faster than YT.
  quality_ceiling: HI_RES_LOSSLESS  # LOW | HIGH | LOSSLESS | HI_RES_LOSSLESS
  sync_favorited_playlists: true  # Pull both your own and saved-from-others playlists.

# Shared settings (apply across providers).
mpd_socket_path: ~/.config/mpd/socket
mpd_music_directory: ~/Music
playlist_format: xspf             # m3u or xspf
sync_interval_minutes: 30
enable_auto_sync: true
stream_cache_hours: 5             # Default for any provider that doesn't set its own.

playlist_prefix:
  yt: "YT: "
  tidal: "TD: "

radio_playlist_limit: 25

history_reporting:
  enabled: false
  min_play_seconds: 30

like_indicator:
  enabled: true
  tag: "+1"
  alignment: right

# Local stream proxy.
proxy_enabled: true
proxy_host: localhost
proxy_port: 8080
proxy_track_mapping_db: ~/.config/xmpd/track_mapping.db

# Logging.
log_level: INFO
log_file: ~/.config/xmpd/xmpd.log
```

- [ ] **Step 3: Verify YAML parses**

```bash
python -c "import yaml; print(yaml.safe_load(open('examples/config.yaml')).keys())"
```

Expected: prints `dict_keys([...])` with `'yt'`, `'tidal'`, etc. No syntax errors.

- [ ] **Step 4: Commit**

```bash
git add examples/config.yaml
git commit -m "examples: full multi-source config.yaml with Tidal section"
```

### Task C14: Stage C verification

**Files:**
- Verify: full suite, daemon start with both providers configured

- [ ] **Step 1: Run full pytest**

```bash
cd ~/Sync/Programs/xmpd
source .venv/bin/activate
pytest -q 2>&1 | tail -15
```

Expected: all tests pass.

- [ ] **Step 2: Smoke-test daemon with Tidal disabled**

```bash
mkdir -p ~/.config/xmpd-test
cp examples/config.yaml ~/.config/xmpd-test/config.yaml
sed -i 's|~/.config/xmpd/|~/.config/xmpd-test/|g' ~/.config/xmpd-test/config.yaml
sed -i 's|proxy_enabled: true|proxy_enabled: false|' ~/.config/xmpd-test/config.yaml
sed -i 's|enabled: true   *# YouTube Music|enabled: false  # YouTube Music disabled for smoke test|' ~/.config/xmpd-test/config.yaml || true
XMPD_CONFIG=~/.config/xmpd-test/config.yaml timeout 8 python -m xmpd 2>&1 | tail -20
```

Expected: daemon starts, logs that no providers are enabled (or just yt), no tracebacks.

- [ ] **Step 3: Push Stage C work**

```bash
rm -rf ~/.config/xmpd-test
git push origin main
```

Stage C complete: TidalProvider implemented end-to-end. Code path is exercised by tests with mocked tidalapi; live integration (against the user's actual Tidal account) follows in the post-rollout user-run smoke test.

---

## Stage D — AirPlay bridge: Tidal album art

Outcome of stage D: when a Tidal-served track plays, the AirPlay receiver shows the correct album art (Tidal's art_url, fetched and cached). When a YT track plays, existing thumbnail behavior preserved.

### Task D1: Update URL parsing for new proxy URL pattern

**Files:**
- Modify: `extras/airplay-bridge/mpd_owntone_metadata.py`
- Test: manual smoke test (no automated tests in this module per existing convention)

- [ ] **Step 1: Inspect current URL parser**

```bash
grep -nA 10 "youtube\|11-char\|video_id\|/proxy/" extras/airplay-bridge/mpd_owntone_metadata.py | head -40
```

- [ ] **Step 2: Update the URL parsing helper**

The existing code keys off `/proxy/<11-char-video-id>`. Update to recognize `/proxy/<provider>/<track_id>`. Add a helper:

```python
import re

PROXY_URL_PATTERN = re.compile(r"/proxy/(?P<provider>\w+)/(?P<track_id>[^/?#]+)")


def parse_proxy_url(url: str | None) -> tuple[str, str] | None:
    """Return (provider, track_id) if `url` is an xmpd proxy URL, else None."""
    if not url:
        return None
    m = PROXY_URL_PATTERN.search(url)
    if not m:
        return None
    return m.group("provider"), m.group("track_id")
```

Replace the existing pattern `_YT_PROXY_RE = re.compile(r"/proxy/([A-Za-z0-9_-]{11})")` with calls to `parse_proxy_url`.

- [ ] **Step 3: Smoke test**

Restart the bridge service, play a YT track, check the AirPlay receiver still shows YT thumbnail. Then verify (after Stage E install migration) by also playing a Tidal track.

For now, just lint and dry-run:

```bash
python -c "import ast; ast.parse(open('extras/airplay-bridge/mpd_owntone_metadata.py').read())"
```

- [ ] **Step 4: Commit**

```bash
git add extras/airplay-bridge/mpd_owntone_metadata.py
git commit -m "airplay-bridge: parse new /proxy/<provider>/<track_id> URL pattern"
```

### Task D2: Add Tidal art-fetcher path

**Files:**
- Modify: `extras/airplay-bridge/mpd_owntone_metadata.py`

- [ ] **Step 1: Read the existing resolver chain**

```bash
grep -nA 20 "_classify_album\|fetch_album_art\|youtube\|hqdefault" extras/airplay-bridge/mpd_owntone_metadata.py | head -60
```

- [ ] **Step 2: Add a Tidal-source art fetcher**

Add a new function that reads `art_url` from the xmpd track-store row:

```python
import sqlite3

DEFAULT_TRACK_DB = Path("~/.config/xmpd/track_mapping.db").expanduser()


def fetch_tidal_album_art(track_id: str, db_path: Path = DEFAULT_TRACK_DB) -> bytes | None:
    """Fetch album art for a Tidal track by reading art_url from the xmpd track store."""
    if not db_path.is_file():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT art_url FROM tracks WHERE provider=? AND track_id=?",
            ("tidal", track_id),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["art_url"]:
        return None
    return _download_with_cache(row["art_url"])  # use the existing online-art cache helper
```

(Use whatever the existing online-art download/cache function is named. The point is: Tidal art is cheap, accurate, and rate-limit-free; prefer it over the iTunes/MusicBrainz fallback chain.)

- [ ] **Step 3: Wire it into the dispatch**

In the function that handles a track change, after parsing the URL via `parse_proxy_url`:

```python
parsed = parse_proxy_url(current_url)
if parsed:
    provider, track_id = parsed
    if provider == "yt":
        art = fetch_youtube_thumbnail(track_id)  # existing function
    elif provider == "tidal":
        art = fetch_tidal_album_art(track_id)
    else:
        art = None
else:
    art = run_local_art_chain()  # existing iTunes/MusicBrainz chain for local files
```

- [ ] **Step 4: Smoke test**

```bash
python -c "import ast; ast.parse(open('extras/airplay-bridge/mpd_owntone_metadata.py').read())"
```

- [ ] **Step 5: Commit**

```bash
git add extras/airplay-bridge/mpd_owntone_metadata.py
git commit -m "airplay-bridge: fetch Tidal album art via track_store.art_url"
```

### Task D3: Update _classify_album to return three categories

**Files:**
- Modify: `extras/airplay-bridge/mpd_owntone_metadata.py`

- [ ] **Step 1: Inspect current classifier**

```bash
grep -nA 15 "_classify_album" extras/airplay-bridge/mpd_owntone_metadata.py
```

- [ ] **Step 2: Update the function**

Replace the body so it returns `"xmpd-yt"` for YT proxy URLs, `"xmpd-tidal"` for Tidal proxy URLs, and the MPD-reported album for everything else:

```python
def _classify_album(current_url: str | None, mpd_album: str | None) -> str:
    parsed = parse_proxy_url(current_url)
    if parsed:
        provider, _ = parsed
        return f"xmpd-{provider}"
    return mpd_album or ""
```

(Plan 1 already changed `return "ytmpd"` to `return "xmpd-yt"`; this task generalizes via the parser.)

- [ ] **Step 3: Audit consumers**

```bash
grep -n "xmpd-yt\|xmpd-tidal\|_classify_album" extras/airplay-bridge/mpd_owntone_metadata.py
```

Verify any callers that branch on the returned string handle both `xmpd-yt` and `xmpd-tidal` correctly.

- [ ] **Step 4: Smoke test**

```bash
python -c "import ast; ast.parse(open('extras/airplay-bridge/mpd_owntone_metadata.py').read())"
```

- [ ] **Step 5: Commit**

```bash
git add extras/airplay-bridge/mpd_owntone_metadata.py
git commit -m "airplay-bridge: _classify_album returns xmpd-yt / xmpd-tidal"
```

### Task D4: Stage D verification

- [ ] **Step 1: Lint**

```bash
python -c "import ast; ast.parse(open('extras/airplay-bridge/mpd_owntone_metadata.py').read())"
ruff check extras/airplay-bridge/mpd_owntone_metadata.py 2>&1 | tail -10
```

- [ ] **Step 2: Push Stage D**

```bash
git push origin main
```

Manual verification deferred until Stage E ships and the user can install + auth Tidal.

---

## Stage E — Install / migration / docs

Outcome of stage E: a fresh user can clone xmpd, run `install.sh`, configure Tidal, and reach a working state. Existing ytmpd users have their config and DB migrated transparently.

### Task E1: Update install.sh for config migration and YAML rewrite

**Files:**
- Modify: `install.sh`
- Add: a small Python helper script (inline in install.sh or as a separate file)

- [ ] **Step 1: Inspect existing install.sh**

```bash
cat install.sh
```

- [ ] **Step 2: Add config-dir migration step**

In `install.sh`, before the systemd unit installation, add:

```bash
# --- Migrate config dir from old ytmpd location, if applicable ---
if [ ! -d "$HOME/.config/xmpd" ] && [ -d "$HOME/.config/ytmpd" ]; then
    echo "Found old ~/.config/ytmpd/. Copying to ~/.config/xmpd/..."
    cp -r "$HOME/.config/ytmpd" "$HOME/.config/xmpd"
    if [ -f "$HOME/.config/xmpd/ytmpd.log" ]; then
        mv "$HOME/.config/xmpd/ytmpd.log" "$HOME/.config/xmpd/xmpd.log"
    fi
    echo "Config dir copied. (Old ~/.config/ytmpd/ left in place; delete manually when confident.)"
fi
```

- [ ] **Step 3: Add YAML shape migration**

After the config-dir copy, run a one-shot Python helper to rewrite the YAML shape:

```bash
# --- Migrate config.yaml shape (top-level auto_auth -> yt.auto_auth) ---
if [ -f "$HOME/.config/xmpd/config.yaml" ]; then
    python3 - <<'PYEOF'
from pathlib import Path
try:
    from ruamel.yaml import YAML
except ImportError:
    import yaml as plain_yaml
    YAML = None

cfg_path = Path("~/.config/xmpd/config.yaml").expanduser()
if YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    cfg = yaml.load(cfg_path)
else:
    cfg = plain_yaml.safe_load(cfg_path.read_text())

if cfg is None:
    cfg = {}

migrated = False

# Move top-level auto_auth -> yt.auto_auth
if "auto_auth" in cfg and "yt" not in cfg:
    cfg.setdefault("yt", {})
    cfg["yt"]["enabled"] = True
    cfg["yt"]["auto_auth"] = cfg.pop("auto_auth")
    migrated = True
elif "auto_auth" in cfg and "yt" in cfg:
    if "auto_auth" not in cfg["yt"]:
        cfg["yt"]["auto_auth"] = cfg.pop("auto_auth")
        migrated = True

# Add a stub tidal section if missing
if "tidal" not in cfg:
    cfg["tidal"] = {
        "enabled": False,
        "stream_cache_hours": 1,
        "quality_ceiling": "HI_RES_LOSSLESS",
        "sync_favorited_playlists": True,
    }
    migrated = True

if migrated:
    if YAML:
        yaml.dump(cfg, cfg_path)
    else:
        import yaml as plain_yaml
        cfg_path.write_text(plain_yaml.safe_dump(cfg, sort_keys=False))
    print("Migrated config.yaml shape (auto_auth -> yt.auto_auth, added tidal stub).")
else:
    print("config.yaml already has new shape; no migration needed.")
PYEOF
fi
```

- [ ] **Step 4: Add ytmpd.service replacement**

```bash
# --- Replace old ytmpd.service if present ---
if [ -f "$HOME/.config/systemd/user/ytmpd.service" ]; then
    echo "Disabling and removing old ytmpd.service..."
    systemctl --user disable ytmpd 2>/dev/null
    rm -f "$HOME/.config/systemd/user/ytmpd.service"
fi
```

- [ ] **Step 5: Add ruamel.yaml to install dependencies if not already**

If install.sh runs `pip install -e ".[dev]"` or similar, ensure `ruamel.yaml` is included via pyproject.toml deps. Otherwise the migration falls back to PyYAML which loses comments.

Add to `pyproject.toml`:

```toml
"ruamel.yaml>=0.17",
```

- [ ] **Step 6: Test install.sh on a fake-old environment**

```bash
# Set up a fake old environment
rm -rf /tmp/fake-old-config
mkdir -p /tmp/fake-old-config/ytmpd
cat > /tmp/fake-old-config/ytmpd/config.yaml <<'EOF'
mpd_socket_path: ~/.config/mpd/socket
sync_interval_minutes: 30
auto_auth:
  enabled: true
  browser: firefox-dev
playlist_format: m3u
EOF
echo "test log" > /tmp/fake-old-config/ytmpd/ytmpd.log

# Run a copy of install.sh's migration logic against this fake env
HOME=/tmp/fake-old-config bash -c 'set -e; \
    [ ! -d "$HOME/.config/xmpd" ] && [ -d "$HOME/.config/ytmpd" ] && cp -r "$HOME/.config/ytmpd" "$HOME/.config/xmpd"; \
    [ -f "$HOME/.config/xmpd/ytmpd.log" ] && mv "$HOME/.config/xmpd/ytmpd.log" "$HOME/.config/xmpd/xmpd.log"; \
    ls -la $HOME/.config/xmpd/'

# Verify
ls /tmp/fake-old-config/.config/xmpd/
cat /tmp/fake-old-config/.config/xmpd/config.yaml
```

Expected: `xmpd.log` exists, `config.yaml` exists, no `ytmpd.log`.

- [ ] **Step 7: Commit**

```bash
git add install.sh pyproject.toml
git commit -m "install: migrate ~/.config/ytmpd to ~/.config/xmpd, rewrite config.yaml shape, replace systemd unit"
```

### Task E2: Update uninstall.sh

**Files:**
- Modify: `uninstall.sh`

- [ ] **Step 1: Inspect**

```bash
cat uninstall.sh
```

- [ ] **Step 2: Update**

Make `uninstall.sh` operate on `xmpd.service`, `xmpctl`, etc. Preserve `~/.config/xmpd/` data by default unless `--purge`:

```bash
sed -i \
  -e 's/\bytmpd\b/xmpd/g' \
  -e 's/\bytmpctl\b/xmpctl/g' \
  -e 's/ytmpd-status/xmpd-status/g' \
  uninstall.sh
```

(After Plan 1 these may already be done; re-run for safety.)

- [ ] **Step 3: Commit**

```bash
git add uninstall.sh
git commit -m "uninstall: align with xmpd identifiers"
```

### Task E3: Rewrite README.md for multi-source story

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read current README**

```bash
head -50 README.md
```

- [ ] **Step 2: Rewrite the lead paragraph and feature list**

Replace the top sections of README.md so it describes xmpd as a multi-source music daemon. Preserve the technical sections (i3 integration, configuration, troubleshooting) but update them for new identifiers and add Tidal-specific notes.

Key changes:
- Title: `# xmpd — Multi-source music daemon (YouTube Music + Tidal → MPD)`
- Lead paragraph: explain the multi-source design, link to spec
- Quick start: `xmpctl auth yt` and `xmpctl auth tidal`
- New section: "Tidal" — auth flow, quality, parity gaps documented in spec
- Update all command examples to `xmpctl ...`
- Update all `~/.config/ytmpd/` references to `~/.config/xmpd/`

The full rewrite is too long to inline here. Reference the spec at `docs/superpowers/specs/2026-04-26-xmpd-tidal-design.md` for the canonical user-facing description.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "README: rewrite for multi-source xmpd"
```

### Task E4: Rewrite docs/MIGRATION.md

**Files:**
- Modify: `docs/MIGRATION.md`

- [ ] **Step 1: Read current state**

```bash
cat docs/MIGRATION.md
```

- [ ] **Step 2: Replace with rename + multi-source migration content**

```markdown
# Migration: ytmpd to xmpd

If you previously ran `ytmpd` on this machine, the new `xmpd` install
script migrates your config and DB transparently. This document
describes what happens and how to run it manually if you need to.

## Automatic migration via install.sh

Run from the new repo:

```bash
cd ~/Sync/Programs/xmpd
./install.sh
```

`install.sh` does:

1. If `~/.config/xmpd/` doesn't exist and `~/.config/ytmpd/` does, copies
   the latter to the former (preserving config, browser.json, track DB).
2. Renames `ytmpd.log` to `xmpd.log` inside the new dir.
3. Rewrites `config.yaml` shape: nests top-level `auto_auth:` under a
   new `yt:` section, adds a `tidal:` stub with default values.
4. Disables and removes the old `ytmpd.service`, installs `xmpd.service`,
   reloads systemd.

The original `~/.config/ytmpd/` is left in place. After confirming xmpd
works, delete it manually with `rm -rf ~/.config/ytmpd`.

## Manual migration

If install.sh isn't suitable (e.g., custom config locations), do the
equivalent steps manually:

```bash
systemctl --user stop ytmpd 2>/dev/null
cp -r ~/.config/ytmpd ~/.config/xmpd
mv ~/.config/xmpd/ytmpd.log ~/.config/xmpd/xmpd.log

# Edit ~/.config/xmpd/config.yaml to nest auto_auth under yt:
# Before:
#   auto_auth:
#     enabled: true
# After:
#   yt:
#     enabled: true
#     auto_auth:
#       enabled: true
#   tidal:
#     enabled: false
#     stream_cache_hours: 1
#     quality_ceiling: HI_RES_LOSSLESS
#     sync_favorited_playlists: true

systemctl --user disable ytmpd 2>/dev/null
rm -f ~/.config/systemd/user/ytmpd.service
# install xmpd.service from the repo:
cp xmpd.service ~/.config/systemd/user/
systemctl --user daemon-reload

# Update i3 keybindings:
sed -i 's/\bytmpctl\b/xmpctl/g; s/ytmpd-status/xmpd-status/g' ~/.i3/config
i3-msg reload

systemctl --user enable --now xmpd
```

## Track database

The SQLite track DB at `~/.config/xmpd/track_mapping.db` migrates on
first xmpd-daemon startup:

- Adds `provider TEXT NOT NULL DEFAULT 'yt'` column.
- Adds nullable `album`, `duration_seconds`, `art_url` columns.
- Compound `(provider, track_id)` unique index for future Tidal rows.
- Existing rows tagged `provider='yt'` retroactively.

PRAGMA `user_version` tracks schema state, so the migration runs
exactly once.

## Setting up Tidal

After migration:

```bash
xmpctl auth tidal
# (paste URL into browser, log in)
# Then in ~/.config/xmpd/config.yaml, set tidal.enabled: true
systemctl --user restart xmpd
```
```

- [ ] **Step 3: Commit**

```bash
git add docs/MIGRATION.md
git commit -m "docs: rewrite MIGRATION.md for ytmpd-to-xmpd migration"
```

### Task E5: Add CHANGELOG entry for Tidal addition

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update the existing "Unreleased" entry**

Plan 1 added an "Unreleased" entry for the rename. Now extend it (or replace `## Unreleased` content) with the multi-source additions:

```markdown
## Unreleased

### Added

- Tidal as a second source provider alongside YouTube Music. Sync,
  search, radio, like/dislike, history reporting, and like-indicator
  all work for Tidal tracks.
- `xmpctl auth tidal` interactive OAuth flow with clipboard helper.
- `xmpctl auth yt` (replaces previous `xmpctl auth --auto`).
- `--provider {yt,tidal,all}` flag on `xmpctl search`.
- `tidal.quality_ceiling` config: highest quality requested per track,
  `HI_RES_LOSSLESS` by default.
- `tidal.sync_favorited_playlists` config: pulls own + favorited
  playlists by default.
- AirPlay bridge fetches Tidal album art for Tidal-served tracks.

### Changed

- Project renamed from `ytmpd` to `xmpd`. The Python package, CLI
  binaries (`xmpctl`, `xmpd-status`, `xmpd-status-preview`), systemd
  unit (`xmpd.service`), and default config dir (`~/.config/xmpd/`) all
  follow the new name.
- Track-store schema gains a `provider` column. Existing data tagged
  `provider='yt'` retroactively. Compound `(provider, track_id)` key.
- Stream proxy URL pattern: `/proxy/<provider>/<track_id>`. Internal
  rename of `icy_proxy.py` to `stream_proxy.py` and the misleading
  `ICYProxyServer` to `StreamRedirectProxy` (no behavior change; the
  module never injected ICY metadata).
- Config `auto_auth:` moved under `yt:` section. `install.sh` migrates
  automatically.

### Deprecated / Removed

- `ytmpctl` CLI name dropped (no compatibility alias). Use `xmpctl`.
- `ytmpd.service` replaced by `xmpd.service`. `install.sh` handles the
  swap.
- `docs/ICY_PROXY.md` removed; `docs/STREAM_PROXY.md` describes the
  current behavior accurately.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "CHANGELOG: document multi-source xmpd release"
```

### Task E6: Stage E verification + push

- [ ] **Step 1: Run full pytest one final time**

```bash
cd ~/Sync/Programs/xmpd
source .venv/bin/activate
pytest -q 2>&1 | tail -10
```

Expected: all tests pass.

- [ ] **Step 2: Run mypy and ruff**

```bash
mypy xmpd/ 2>&1 | tail -5
ruff check xmpd/ 2>&1 | tail -5
```

Expected: no errors. Fix any new issues introduced by the multi-source work.

- [ ] **Step 3: Push everything**

```bash
git push origin main
```

- [ ] **Step 4: User-machine smoke test (operator runs, not the implementing AI)**

The user runs:

```bash
# In ~/Sync/Programs/xmpd
./install.sh                   # migrates config, swaps service unit
sed -i 's/\bytmpctl\b/xmpctl/g; s/ytmpd-status/xmpd-status/g' ~/.i3/config
i3-msg reload
systemctl --user status xmpd

# Verify YT still works
xmpctl status
xmpctl sync
mpc lsplaylists | head -5

# Set up Tidal
xmpctl auth tidal
# (paste URL into browser, log in)
# Edit ~/.config/xmpd/config.yaml: set tidal.enabled: true
systemctl --user restart xmpd
xmpctl sync
mpc lsplaylists | grep '^TD:'

# Play a Tidal track and verify AirPlay album art
mpc load "TD: Favorites"
mpc play
# (check Denon/kitchen receiver for art)
```

If all of these succeed, plan 2 is complete.

---

## Acceptance criteria (whole plan)

- All Stage A–E commits are on `origin/main` of `tuncenator/xmpd`.
- `pytest` passes.
- Daemon starts cleanly with both providers configured (or just one — both modes tested in Stage C verification).
- `xmpctl auth tidal` runs the OAuth flow with clipboard support and saves a working token.
- Tidal playlists sync into MPD as `TD: ...`. Tidal tracks play. Search, radio, like/dislike, history all work.
- Existing YouTube Music functionality is preserved end-to-end.
- AirPlay receivers display Tidal album art for Tidal-served tracks.
- `~/.config/ytmpd/` migrated by `install.sh` to `~/.config/xmpd/`; user's existing data preserved.
- Old `ytmpd.service` disabled and replaced by `xmpd.service`.
- README, MIGRATION.md, CHANGELOG.md describe the new multi-source state accurately.

After acceptance, the user can delete `~/Sync/Programs/ytmpd/` (the local fallback clone) and `~/.config/ytmpd/` (the original config dir) at their leisure. The next spec — out of scope — is the cross-provider liked-tracks sync layer, which builds on the `Track.liked_signature` hook reserved here.
