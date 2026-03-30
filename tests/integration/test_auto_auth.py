"""Integration tests for auto-auth: full cookie extraction pipeline and edge cases."""

import json
import sqlite3
import time
from pathlib import Path

import pytest

from ytmpd.cookie_extract import FirefoxCookieExtractor
from ytmpd.exceptions import CookieExtractionError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PROFILES_INI_TEMPLATE = """\
[Profile0]
Name=default-release
IsRelative=1
Path={std_profile}

[Profile1]
Name=dev-edition-default
IsRelative=1
Path={dev_profile}

[Install4F96D1932A9F858E]
Default={std_profile}

[Install46F492E0ACFF84D4]
Default={dev_profile}
"""

CONTAINERS_JSON = {
    "version": 4,
    "identities": [
        {"userContextId": 1, "name": "Personal", "public": True},
        {"userContextId": 2, "name": "Work", "public": True},
    ],
}

# Realistic set of YouTube Music cookies
_COOKIE_NAMES = [
    "SID",
    "HSID",
    "SSID",
    "APISID",
    "SAPISID",
    "__Secure-1PAPISID",
    "__Secure-3PAPISID",
    "__Secure-1PSID",
    "__Secure-3PSID",
    "__Secure-1PSIDCC",
    "__Secure-3PSIDCC",
    "__Secure-1PSIDTS",
    "__Secure-3PSIDTS",
    "LOGIN_INFO",
    "SIDCC",
    "PREF",
    "VISITOR_PRIVACY_METADATA",
    "VISITOR_INFO1_LIVE",
]


def _create_cookie_db(
    db_path: Path,
    cookie_names: list[str] | None = None,
    expired: bool = False,
    origin_attributes: str = "",
    extra_cookies: list[dict] | None = None,
) -> None:
    """Create a Firefox cookies.sqlite with test data."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE moz_cookies ("
        "  id INTEGER PRIMARY KEY,"
        "  name TEXT NOT NULL,"
        "  value TEXT NOT NULL,"
        "  host TEXT NOT NULL,"
        "  expiry INTEGER NOT NULL,"
        "  isSecure INTEGER NOT NULL,"
        "  originAttributes TEXT NOT NULL DEFAULT ''"
        ")"
    )
    if cookie_names is None:
        cookie_names = _COOKIE_NAMES

    expiry = int(time.time()) - 3600 if expired else int(time.time()) + 86400 * 365

    for name in cookie_names:
        is_secure = 1 if name.startswith("__Secure") else 0
        conn.execute(
            "INSERT INTO moz_cookies (name, value, host, expiry, isSecure, originAttributes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, f"{name}_test_value", ".youtube.com", expiry, is_secure, origin_attributes),
        )

    if extra_cookies:
        for c in extra_cookies:
            conn.execute(
                "INSERT INTO moz_cookies (name, value, host, expiry, isSecure, originAttributes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    c["name"],
                    c["value"],
                    c.get("host", ".youtube.com"),
                    c.get("expiry", expiry),
                    c.get("isSecure", 0),
                    c.get("originAttributes", ""),
                ),
            )

    conn.commit()
    conn.close()


def _setup_firefox_dir(
    tmp_path: Path,
    dev_profile_name: str = "abc123.dev-edition-default",
    std_profile_name: str = "def456.default-release",
    create_dev_cookies: bool = True,
    create_std_cookies: bool = True,
    dev_cookie_names: list[str] | None = None,
    dev_expired: bool = False,
    containers: dict | None = None,
    dev_extra_cookies: list[dict] | None = None,
) -> Path:
    """Set up a fake ~/.mozilla/firefox directory structure.

    Returns the firefox directory path.
    """
    ff_dir = tmp_path / ".mozilla" / "firefox"
    ff_dir.mkdir(parents=True)

    (ff_dir / "profiles.ini").write_text(
        PROFILES_INI_TEMPLATE.format(
            std_profile=std_profile_name,
            dev_profile=dev_profile_name,
        )
    )

    dev_profile = ff_dir / dev_profile_name
    dev_profile.mkdir()
    if create_dev_cookies:
        _create_cookie_db(
            dev_profile / "cookies.sqlite",
            cookie_names=dev_cookie_names,
            expired=dev_expired,
            extra_cookies=dev_extra_cookies,
        )

    if containers is not None:
        (dev_profile / "containers.json").write_text(json.dumps(containers))

    std_profile = ff_dir / std_profile_name
    std_profile.mkdir()
    if create_std_cookies:
        _create_cookie_db(std_profile / "cookies.sqlite")

    return ff_dir


def _make_extractor(ff_dir: Path, **kwargs) -> FirefoxCookieExtractor:
    """Create an extractor pointing at a fake firefox dir."""
    ext = FirefoxCookieExtractor(**kwargs)
    ext._firefox_dir = ff_dir
    return ext


# ---------------------------------------------------------------------------
# Integration: Full extraction pipeline
# ---------------------------------------------------------------------------


class TestFullExtractionPipeline:
    """End-to-end tests: profile detection -> cookie extraction -> browser.json."""

    def test_full_pipeline_produces_valid_browser_json(self, tmp_path: Path) -> None:
        ff_dir = _setup_firefox_dir(tmp_path, containers=CONTAINERS_JSON)
        ext = _make_extractor(ff_dir, browser="firefox-dev")

        output = tmp_path / "output" / "browser.json"
        result = ext.build_browser_json(output)

        assert result == output
        assert output.exists()

        data = json.loads(output.read_text())

        # Verify structure
        assert "authorization" in data
        assert data["authorization"].startswith("SAPISIDHASH ")
        assert "cookie" in data
        assert data["origin"] == "https://music.youtube.com"
        assert data["x-origin"] == "https://music.youtube.com"
        assert data["x-goog-authuser"] == "0"

        # Verify all cookies are present
        cookie_str = data["cookie"]
        for name in _COOKIE_NAMES:
            assert f"{name}=" in cookie_str, f"Missing cookie: {name}"

    def test_pipeline_with_standard_firefox(self, tmp_path: Path) -> None:
        ff_dir = _setup_firefox_dir(tmp_path)
        ext = _make_extractor(ff_dir, browser="firefox")

        output = tmp_path / "browser.json"
        ext.build_browser_json(output)

        data = json.loads(output.read_text())
        assert "SAPISIDHASH" in data["authorization"]

    def test_pipeline_with_container(self, tmp_path: Path) -> None:
        ff_dir = _setup_firefox_dir(
            tmp_path,
            containers=CONTAINERS_JSON,
            dev_extra_cookies=[
                {
                    "name": name,
                    "value": f"{name}_container",
                    "host": ".youtube.com",
                    "expiry": int(time.time()) + 86400 * 365,
                    "isSecure": 1 if name.startswith("__Secure") else 0,
                    "originAttributes": "^userContextId=1",
                }
                for name in _COOKIE_NAMES
            ],
        )
        ext = _make_extractor(ff_dir, browser="firefox-dev", container="Personal")

        output = tmp_path / "browser.json"
        ext.build_browser_json(output)

        data = json.loads(output.read_text())
        assert "SID=SID_container" in data["cookie"]

    def test_pipeline_with_explicit_profile(self, tmp_path: Path) -> None:
        profile_name = "abc123.dev-edition-default"
        ff_dir = _setup_firefox_dir(tmp_path, dev_profile_name=profile_name)
        ext = _make_extractor(ff_dir, browser="firefox-dev", profile=profile_name)

        output = tmp_path / "browser.json"
        ext.build_browser_json(output)

        assert output.exists()
        data = json.loads(output.read_text())
        assert "SAPISIDHASH" in data["authorization"]

    def test_pipeline_multiple_profiles_selects_correct(self, tmp_path: Path) -> None:
        """With multiple profiles, the correct default is selected per browser type."""
        ff_dir = _setup_firefox_dir(tmp_path)

        # Standard Firefox extractor should use std profile
        ext_std = _make_extractor(ff_dir, browser="firefox")
        profile_std = ext_std.find_profile_dir()
        assert "default-release" in profile_std.name

        # Dev edition extractor should use dev profile
        ext_dev = _make_extractor(ff_dir, browser="firefox-dev")
        profile_dev = ext_dev.find_profile_dir()
        assert "dev-edition-default" in profile_dev.name


# ---------------------------------------------------------------------------
# Edge cases: Firefox not installed / missing components
# ---------------------------------------------------------------------------


class TestFirefoxNotInstalled:
    def test_no_firefox_directory(self, tmp_path: Path) -> None:
        ext = FirefoxCookieExtractor(browser="firefox-dev")
        ext._firefox_dir = tmp_path / "nonexistent"

        with pytest.raises(CookieExtractionError, match="profiles.ini not found"):
            ext.extract_cookies()

    def test_firefox_dir_exists_but_empty(self, tmp_path: Path) -> None:
        ff_dir = tmp_path / ".mozilla" / "firefox"
        ff_dir.mkdir(parents=True)

        ext = _make_extractor(ff_dir, browser="firefox-dev")
        with pytest.raises(CookieExtractionError, match="profiles.ini not found"):
            ext.extract_cookies()


# ---------------------------------------------------------------------------
# Edge cases: cookies.sqlite problems
# ---------------------------------------------------------------------------


class TestCookieDatabaseEdgeCases:
    def test_cookies_sqlite_missing(self, tmp_path: Path) -> None:
        ff_dir = _setup_firefox_dir(tmp_path, create_dev_cookies=False)
        ext = _make_extractor(ff_dir, browser="firefox-dev")

        with pytest.raises(CookieExtractionError, match="cookies.sqlite not found"):
            ext.extract_cookies()

    def test_corrupt_database(self, tmp_path: Path) -> None:
        ff_dir = _setup_firefox_dir(tmp_path, create_dev_cookies=False)
        profile_dir = ff_dir / "abc123.dev-edition-default"
        # Write garbage instead of a valid SQLite file
        (profile_dir / "cookies.sqlite").write_bytes(b"this is not a sqlite database")

        ext = _make_extractor(ff_dir, browser="firefox-dev")
        with pytest.raises(CookieExtractionError, match="corrupt|unreadable|Failed"):
            ext.extract_cookies()

    def test_database_no_youtube_cookies(self, tmp_path: Path) -> None:
        ff_dir = _setup_firefox_dir(tmp_path, create_dev_cookies=False)
        profile_dir = ff_dir / "abc123.dev-edition-default"
        # Create valid DB but with no YouTube cookies
        conn = sqlite3.connect(profile_dir / "cookies.sqlite")
        conn.execute(
            "CREATE TABLE moz_cookies ("
            "  id INTEGER PRIMARY KEY, name TEXT, value TEXT, host TEXT,"
            "  expiry INTEGER, isSecure INTEGER, originAttributes TEXT DEFAULT '')"
        )
        conn.execute(
            "INSERT INTO moz_cookies (name, value, host, expiry, isSecure, originAttributes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("session", "abc", ".example.com", int(time.time()) + 86400, 0, ""),
        )
        conn.commit()
        conn.close()

        ext = _make_extractor(ff_dir, browser="firefox-dev")
        cookies = ext.extract_cookies()
        assert cookies == []

    def test_all_cookies_expired(self, tmp_path: Path) -> None:
        ff_dir = _setup_firefox_dir(tmp_path, dev_expired=True)
        ext = _make_extractor(ff_dir, browser="firefox-dev")

        # extract_cookies returns them; validation fails
        cookies = ext.extract_cookies()
        assert len(cookies) > 0
        assert ext.validate_cookies(cookies) is False

    def test_wal_file_missing_still_works(self, tmp_path: Path) -> None:
        ff_dir = _setup_firefox_dir(tmp_path)
        profile_dir = ff_dir / "abc123.dev-edition-default"

        # Ensure no WAL/SHM files exist
        for suffix in ("-wal", "-shm"):
            wal = profile_dir / f"cookies.sqlite{suffix}"
            if wal.exists():
                wal.unlink()

        ext = _make_extractor(ff_dir, browser="firefox-dev")
        cookies = ext.extract_cookies()
        assert len(cookies) > 0

    def test_database_locked_retry(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        ff_dir = _setup_firefox_dir(tmp_path)
        ext = _make_extractor(ff_dir, browser="firefox-dev")

        original_query = ext._query_cookies_with_retry
        call_count = 0

        def mock_query(conn, domain, origin_filter, max_retries=3, retry_delay=1.0):
            nonlocal call_count
            call_count += 1
            # Use very short retry delay in tests
            return original_query(conn, domain, origin_filter, max_retries, retry_delay=0.01)

        monkeypatch.setattr(ext, "_query_cookies_with_retry", mock_query)
        cookies = ext.extract_cookies()
        assert len(cookies) > 0

    def test_database_locked_retry_exhaustion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ff_dir = _setup_firefox_dir(tmp_path)
        ext = _make_extractor(ff_dir, browser="firefox-dev")

        def always_locked(conn, domain, origin_filter, max_retries=3, retry_delay=1.0):
            raise CookieExtractionError(
                "Cookie database locked after 3 attempts: database is locked"
            )

        monkeypatch.setattr(ext, "_query_cookies_with_retry", always_locked)
        with pytest.raises(CookieExtractionError, match="locked"):
            ext.extract_cookies()


# ---------------------------------------------------------------------------
# Edge cases: Container problems
# ---------------------------------------------------------------------------


class TestContainerEdgeCases:
    def test_container_specified_but_no_containers_json(self, tmp_path: Path) -> None:
        ff_dir = _setup_firefox_dir(tmp_path, containers=None)
        ext = _make_extractor(ff_dir, browser="firefox-dev", container="Personal")

        with pytest.raises(CookieExtractionError, match="containers.json not found"):
            ext.extract_cookies()

    def test_container_not_in_containers_json(self, tmp_path: Path) -> None:
        ff_dir = _setup_firefox_dir(tmp_path, containers=CONTAINERS_JSON)
        ext = _make_extractor(ff_dir, browser="firefox-dev", container="Nonexistent")

        with pytest.raises(CookieExtractionError, match="not found.*Available"):
            ext.extract_cookies()

    def test_container_found_filters_correctly(self, tmp_path: Path) -> None:
        future = int(time.time()) + 86400 * 365
        ff_dir = _setup_firefox_dir(
            tmp_path,
            containers=CONTAINERS_JSON,
            dev_extra_cookies=[
                {
                    "name": name,
                    "value": f"{name}_personal",
                    "originAttributes": "^userContextId=1",
                    "expiry": future,
                    "isSecure": 1 if name.startswith("__Secure") else 0,
                }
                for name in _COOKIE_NAMES
            ],
        )
        ext = _make_extractor(ff_dir, browser="firefox-dev", container="Personal")
        cookies = ext.extract_cookies()

        # Should only get container cookies, not default ones
        assert all("_personal" in c["value"] for c in cookies)

    def test_corrupt_containers_json(self, tmp_path: Path) -> None:
        ff_dir = _setup_firefox_dir(tmp_path, containers=None)
        profile_dir = ff_dir / "abc123.dev-edition-default"
        (profile_dir / "containers.json").write_text("not valid json {{{")

        ext = _make_extractor(ff_dir, browser="firefox-dev", container="Personal")
        with pytest.raises(CookieExtractionError, match="Failed to read containers.json"):
            ext.extract_cookies()


# ---------------------------------------------------------------------------
# Edge cases: Profile problems
# ---------------------------------------------------------------------------


class TestProfileEdgeCases:
    def test_explicit_profile_not_a_directory(self, tmp_path: Path) -> None:
        ff_dir = tmp_path / ".mozilla" / "firefox"
        ff_dir.mkdir(parents=True)
        # Create a file where a directory is expected
        (ff_dir / "fake-profile").write_text("not a directory")

        ext = _make_extractor(ff_dir, browser="firefox-dev", profile="fake-profile")
        with pytest.raises(CookieExtractionError, match="not found"):
            ext.find_profile_dir()

    def test_profiles_ini_points_to_missing_profile(self, tmp_path: Path) -> None:
        ff_dir = tmp_path / ".mozilla" / "firefox"
        ff_dir.mkdir(parents=True)
        (ff_dir / "profiles.ini").write_text("[Install46F492E0ACFF84D4]\nDefault=ghost-profile\n")

        ext = _make_extractor(ff_dir, browser="firefox-dev")
        with pytest.raises(CookieExtractionError, match="not found"):
            ext.find_profile_dir()


# ---------------------------------------------------------------------------
# Edge case: Validation details
# ---------------------------------------------------------------------------


class TestValidationEdgeCases:
    def test_only_sapisid_no_secure3papisid(self, tmp_path: Path) -> None:
        """Should work with just SAPISID when __Secure-3PAPISID is missing."""
        names = ["SID", "HSID", "SSID", "SAPISID"]
        ff_dir = _setup_firefox_dir(tmp_path, dev_cookie_names=names)
        ext = _make_extractor(ff_dir, browser="firefox-dev")

        output = tmp_path / "browser.json"
        ext.build_browser_json(output)
        data = json.loads(output.read_text())
        assert "SAPISIDHASH" in data["authorization"]

    def test_only_secure3papisid_no_sapisid(self, tmp_path: Path) -> None:
        """Should work with just __Secure-3PAPISID when SAPISID is missing."""
        names = ["SID", "HSID", "SSID", "__Secure-3PAPISID"]
        ff_dir = _setup_firefox_dir(tmp_path, dev_cookie_names=names)
        ext = _make_extractor(ff_dir, browser="firefox-dev")

        output = tmp_path / "browser.json"
        ext.build_browser_json(output)
        data = json.loads(output.read_text())
        assert "SAPISIDHASH" in data["authorization"]

    def test_no_sapisid_at_all_raises(self, tmp_path: Path) -> None:
        """Should fail if neither SAPISID nor __Secure-3PAPISID present."""
        names = ["SID", "HSID", "SSID"]
        ff_dir = _setup_firefox_dir(tmp_path, dev_cookie_names=names)
        ext = _make_extractor(ff_dir, browser="firefox-dev")

        with pytest.raises(CookieExtractionError, match="validation failed"):
            ext.build_browser_json(tmp_path / "browser.json")

    def test_session_cookies_accepted(self, tmp_path: Path) -> None:
        """Cookies with expiry=0 (session cookies) should pass validation."""
        ff_dir = _setup_firefox_dir(tmp_path, create_dev_cookies=False)
        profile_dir = ff_dir / "abc123.dev-edition-default"

        conn = sqlite3.connect(profile_dir / "cookies.sqlite")
        conn.execute(
            "CREATE TABLE moz_cookies ("
            "  id INTEGER PRIMARY KEY, name TEXT, value TEXT, host TEXT,"
            "  expiry INTEGER, isSecure INTEGER, originAttributes TEXT DEFAULT '')"
        )
        for name in ["SID", "HSID", "SSID", "SAPISID", "__Secure-3PAPISID"]:
            conn.execute(
                "INSERT INTO moz_cookies (name, value, host, expiry, isSecure, originAttributes) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (name, f"{name}_val", ".youtube.com", 0, 0, ""),
            )
        conn.commit()
        conn.close()

        ext = _make_extractor(ff_dir, browser="firefox-dev")
        cookies = ext.extract_cookies()
        assert ext.validate_cookies(cookies) is True


# ---------------------------------------------------------------------------
# Daemon status with auto-auth enabled
# ---------------------------------------------------------------------------


class TestDaemonStatusAutoAuth:
    """Test that daemon status includes auto-auth fields."""

    def test_status_includes_auto_auth_fields_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify the daemon's status response shape includes auto-auth info."""
        # This is a structural test - we mock the daemon to check field presence
        from unittest.mock import MagicMock, patch

        mock_config = {
            "socket_path": "/tmp/test_socket",
            "state_file": "/tmp/test_state.json",
            "log_level": "INFO",
            "log_file": "/tmp/test.log",
            "mpd_socket_path": "/tmp/mpd_socket",
            "mpd_playlist_directory": "/tmp/mpd_playlists",
            "sync_interval_minutes": 30,
            "enable_auto_sync": False,
            "playlist_prefix": "YT: ",
            "stream_cache_hours": 5,
            "proxy_enabled": False,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
            "radio_playlist_limit": 25,
            "playlist_format": "m3u",
            "mpd_music_directory": "/tmp/music",
            "auto_auth": {
                "enabled": True,
                "browser": "firefox-dev",
                "container": None,
                "profile": None,
                "refresh_interval_hours": 12,
            },
        }

        with (
            patch("ytmpd.daemon.load_config", return_value=mock_config),
            patch("ytmpd.daemon.YTMusicClient") as mock_yt,
            patch("ytmpd.daemon.SyncEngine"),
            patch("ytmpd.daemon.MPDClient"),
            patch("ytmpd.daemon.StreamResolver"),
            patch("ytmpd.daemon.TrackStore"),
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.mkdir"),
        ):
            mock_yt_instance = MagicMock()
            mock_yt_instance.is_authenticated.return_value = (True, "")
            mock_yt.return_value = mock_yt_instance

            from ytmpd.daemon import YTMPDaemon

            daemon = YTMPDaemon()
            status = daemon._cmd_status()

            assert "auto_auth_enabled" in status
            assert status["auto_auth_enabled"] is True
            assert "auto_refresh_failures" in status
            assert "last_auto_refresh" in status
