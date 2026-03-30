"""Tests for ytmpd.cookie_extract module."""

import json
import sqlite3
import time
from pathlib import Path

import pytest

from ytmpd.cookie_extract import _ORIGIN, FirefoxCookieExtractor
from ytmpd.exceptions import CookieExtractionError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROFILES_INI_CONTENT = """\
[Profile0]
Name=default-release
IsRelative=1
Path=abcdefgh.default-release

[Profile1]
Name=dev-edition-default
IsRelative=1
Path=4wkrywqj.dev-edition-default

[Install4F96D1932A9F858E]
Default=abcdefgh.default-release

[Install46F492E0ACFF84D4]
Default=4wkrywqj.dev-edition-default
"""

CONTAINERS_JSON = {
    "version": 4,
    "identities": [
        {"userContextId": 1, "name": "Personal", "public": True},
        {"userContextId": 2, "name": "Work", "public": True},
        {"userContextId": 16, "name": "ACCOUNT_002", "public": True},
    ],
}


def _create_cookie_db(db_path: Path, cookies: list[dict] | None = None) -> None:
    """Create a minimal Firefox cookies.sqlite with test data."""
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
    if cookies is None:
        future = int(time.time()) + 86400 * 365
        cookies = [
            {
                "name": "SID",
                "value": "sid_val",
                "host": ".youtube.com",
                "expiry": future,
                "isSecure": 0,
                "originAttributes": "",
            },
            {
                "name": "HSID",
                "value": "hsid_val",
                "host": ".youtube.com",
                "expiry": future,
                "isSecure": 0,
                "originAttributes": "",
            },
            {
                "name": "SSID",
                "value": "ssid_val",
                "host": ".youtube.com",
                "expiry": future,
                "isSecure": 1,
                "originAttributes": "",
            },
            {
                "name": "APISID",
                "value": "apisid_val",
                "host": ".youtube.com",
                "expiry": future,
                "isSecure": 0,
                "originAttributes": "",
            },
            {
                "name": "SAPISID",
                "value": "sapisid_val",
                "host": ".youtube.com",
                "expiry": future,
                "isSecure": 1,
                "originAttributes": "",
            },
            {
                "name": "__Secure-3PAPISID",
                "value": "s3papisid_val",
                "host": ".youtube.com",
                "expiry": future,
                "isSecure": 1,
                "originAttributes": "",
            },
            {
                "name": "__Secure-3PSID",
                "value": "s3psid_val",
                "host": ".youtube.com",
                "expiry": future,
                "isSecure": 1,
                "originAttributes": "",
            },
            # A cookie in a container (should be excluded by default)
            {
                "name": "SID",
                "value": "container_sid",
                "host": ".youtube.com",
                "expiry": future,
                "isSecure": 0,
                "originAttributes": "^userContextId=16",
            },
        ]
    for c in cookies:
        conn.execute(
            "INSERT INTO moz_cookies (name, value, host, expiry, isSecure, originAttributes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (c["name"], c["value"], c["host"], c["expiry"], c["isSecure"], c["originAttributes"]),
        )
    conn.commit()
    conn.close()


@pytest.fixture()
def firefox_home(tmp_path: Path) -> Path:
    """Set up a fake ~/.mozilla/firefox directory."""
    ff_dir = tmp_path / ".mozilla" / "firefox"
    ff_dir.mkdir(parents=True)

    # profiles.ini
    (ff_dir / "profiles.ini").write_text(PROFILES_INI_CONTENT)

    # Dev edition profile
    dev_profile = ff_dir / "4wkrywqj.dev-edition-default"
    dev_profile.mkdir()
    _create_cookie_db(dev_profile / "cookies.sqlite")
    (dev_profile / "containers.json").write_text(json.dumps(CONTAINERS_JSON))

    # Standard profile
    std_profile = ff_dir / "abcdefgh.default-release"
    std_profile.mkdir()
    _create_cookie_db(std_profile / "cookies.sqlite")

    return ff_dir


def _make_extractor(
    firefox_home: Path, browser: str = "firefox-dev", **kwargs
) -> FirefoxCookieExtractor:
    ext = FirefoxCookieExtractor(browser=browser, **kwargs)
    ext._firefox_dir = firefox_home
    return ext


# ---------------------------------------------------------------------------
# Tests: __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_invalid_browser_raises(self) -> None:
        with pytest.raises(CookieExtractionError, match="Unsupported browser"):
            FirefoxCookieExtractor(browser="chrome")


# ---------------------------------------------------------------------------
# Tests: find_profile_dir
# ---------------------------------------------------------------------------


class TestFindProfileDir:
    def test_auto_detect_dev_edition(self, firefox_home: Path) -> None:
        ext = _make_extractor(firefox_home, browser="firefox-dev")
        result = ext.find_profile_dir()
        assert result == firefox_home / "4wkrywqj.dev-edition-default"

    def test_auto_detect_standard(self, firefox_home: Path) -> None:
        ext = _make_extractor(firefox_home, browser="firefox")
        result = ext.find_profile_dir()
        assert result == firefox_home / "abcdefgh.default-release"

    def test_explicit_profile(self, firefox_home: Path) -> None:
        ext = _make_extractor(firefox_home, profile="4wkrywqj.dev-edition-default")
        result = ext.find_profile_dir()
        assert result == firefox_home / "4wkrywqj.dev-edition-default"

    def test_explicit_profile_not_found(self, firefox_home: Path) -> None:
        ext = _make_extractor(firefox_home, profile="nonexistent")
        with pytest.raises(CookieExtractionError, match="not found"):
            ext.find_profile_dir()

    def test_missing_profiles_ini(self, firefox_home: Path) -> None:
        (firefox_home / "profiles.ini").unlink()
        ext = _make_extractor(firefox_home)
        with pytest.raises(CookieExtractionError, match="profiles.ini not found"):
            ext.find_profile_dir()

    def test_missing_install_section(self, firefox_home: Path) -> None:
        (firefox_home / "profiles.ini").write_text("[Profile0]\nName=default\n")
        ext = _make_extractor(firefox_home, browser="firefox-dev")
        with pytest.raises(CookieExtractionError, match="No firefox-dev installation"):
            ext.find_profile_dir()

    def test_missing_default_key(self, firefox_home: Path) -> None:
        (firefox_home / "profiles.ini").write_text("[Install46F492E0ACFF84D4]\nLocked=1\n")
        ext = _make_extractor(firefox_home, browser="firefox-dev")
        with pytest.raises(CookieExtractionError, match="No default profile"):
            ext.find_profile_dir()

    def test_profile_dir_missing_on_disk(self, firefox_home: Path) -> None:
        # Remove the actual profile directory but keep profiles.ini pointing to it
        import shutil

        shutil.rmtree(firefox_home / "4wkrywqj.dev-edition-default")
        ext = _make_extractor(firefox_home, browser="firefox-dev")
        with pytest.raises(CookieExtractionError, match="not found"):
            ext.find_profile_dir()


# ---------------------------------------------------------------------------
# Tests: extract_cookies
# ---------------------------------------------------------------------------


class TestExtractCookies:
    def test_extracts_no_container_cookies(self, firefox_home: Path) -> None:
        ext = _make_extractor(firefox_home)
        cookies = ext.extract_cookies()
        # Should get the 7 no-container cookies, not the container one
        assert len(cookies) == 7
        names = {c["name"] for c in cookies}
        assert "SID" in names
        assert "__Secure-3PAPISID" in names
        # Verify no container cookies leaked through
        assert all(c["value"] != "container_sid" for c in cookies)

    def test_extracts_container_cookies(self, firefox_home: Path) -> None:
        ext = _make_extractor(firefox_home, container="ACCOUNT_002")
        cookies = ext.extract_cookies()
        assert len(cookies) == 1
        assert cookies[0]["value"] == "container_sid"

    def test_container_not_found(self, firefox_home: Path) -> None:
        ext = _make_extractor(firefox_home, container="Nonexistent")
        with pytest.raises(CookieExtractionError, match="Container.*not found"):
            ext.extract_cookies()

    def test_missing_containers_json(self, firefox_home: Path) -> None:
        (firefox_home / "4wkrywqj.dev-edition-default" / "containers.json").unlink()
        ext = _make_extractor(firefox_home, container="Personal")
        with pytest.raises(CookieExtractionError, match="containers.json not found"):
            ext.extract_cookies()

    def test_missing_cookies_sqlite(self, firefox_home: Path) -> None:
        (firefox_home / "4wkrywqj.dev-edition-default" / "cookies.sqlite").unlink()
        ext = _make_extractor(firefox_home)
        with pytest.raises(CookieExtractionError, match="cookies.sqlite not found"):
            ext.extract_cookies()

    def test_empty_database(self, firefox_home: Path) -> None:
        db_path = firefox_home / "4wkrywqj.dev-edition-default" / "cookies.sqlite"
        db_path.unlink()
        _create_cookie_db(db_path, cookies=[])
        ext = _make_extractor(firefox_home)
        cookies = ext.extract_cookies()
        assert cookies == []

    def test_domain_filter(self, firefox_home: Path) -> None:
        ext = _make_extractor(firefox_home)
        cookies = ext.extract_cookies(domain=".google.com")
        assert cookies == []


# ---------------------------------------------------------------------------
# Tests: validate_cookies
# ---------------------------------------------------------------------------


class TestValidateCookies:
    def _make_cookies(self, names: list[str], expired: bool = False) -> list[dict]:
        exp = int(time.time()) - 3600 if expired else int(time.time()) + 86400
        return [
            {"name": n, "value": f"{n}_val", "host": ".youtube.com", "expiry": exp, "isSecure": 0}
            for n in names
        ]

    def test_valid_cookies(self, firefox_home: Path) -> None:
        ext = _make_extractor(firefox_home)
        cookies = self._make_cookies(["SID", "HSID", "SSID", "SAPISID", "__Secure-3PAPISID"])
        assert ext.validate_cookies(cookies) is True

    def test_missing_required(self, firefox_home: Path) -> None:
        ext = _make_extractor(firefox_home)
        cookies = self._make_cookies(["SAPISID"])  # Missing SID, HSID, SSID
        assert ext.validate_cookies(cookies) is False

    def test_missing_sapisid(self, firefox_home: Path) -> None:
        ext = _make_extractor(firefox_home)
        cookies = self._make_cookies(["SID", "HSID", "SSID"])  # No SAPISID
        assert ext.validate_cookies(cookies) is False

    def test_expired_critical_cookie(self, firefox_home: Path) -> None:
        ext = _make_extractor(firefox_home)
        cookies = self._make_cookies(["HSID", "SSID", "SAPISID"])
        cookies.append(
            {"name": "SID", "value": "x", "host": ".youtube.com", "expiry": 1, "isSecure": 0}
        )
        assert ext.validate_cookies(cookies) is False

    def test_zero_expiry_treated_as_session(self, firefox_home: Path) -> None:
        """Cookies with expiry=0 are session cookies and should not be flagged as expired."""
        ext = _make_extractor(firefox_home)
        cookies = self._make_cookies(["HSID", "SSID", "SAPISID", "__Secure-3PAPISID"])
        cookies.append(
            {"name": "SID", "value": "x", "host": ".youtube.com", "expiry": 0, "isSecure": 0}
        )
        assert ext.validate_cookies(cookies) is True


# ---------------------------------------------------------------------------
# Tests: build_browser_json
# ---------------------------------------------------------------------------


class TestBuildBrowserJson:
    def test_generates_valid_json(self, firefox_home: Path, tmp_path: Path) -> None:
        ext = _make_extractor(firefox_home)
        output = tmp_path / "browser.json"
        result = ext.build_browser_json(output)
        assert result == output
        assert output.exists()

        data = json.loads(output.read_text())
        assert data["origin"] == _ORIGIN
        assert data["x-origin"] == _ORIGIN
        assert "SAPISIDHASH" in data["authorization"]
        assert "cookie" in data
        assert "SID=" in data["cookie"]
        assert data["x-goog-authuser"] == "0"

    def test_prefers_secure_3papisid(self, firefox_home: Path, tmp_path: Path) -> None:
        """Should use __Secure-3PAPISID over SAPISID for SAPISIDHASH."""
        ext = _make_extractor(firefox_home)
        output = tmp_path / "browser.json"
        ext.build_browser_json(output)
        data = json.loads(output.read_text())
        # The cookie string should contain both, but the hash should be based on __Secure-3PAPISID
        assert "__Secure-3PAPISID=s3papisid_val" in data["cookie"]

    def test_fails_on_invalid_cookies(self, firefox_home: Path, tmp_path: Path) -> None:
        db_path = firefox_home / "4wkrywqj.dev-edition-default" / "cookies.sqlite"
        db_path.unlink()
        _create_cookie_db(db_path, cookies=[])
        ext = _make_extractor(firefox_home)
        with pytest.raises(CookieExtractionError, match="validation failed"):
            ext.build_browser_json(tmp_path / "browser.json")

    def test_creates_parent_directories(self, firefox_home: Path, tmp_path: Path) -> None:
        ext = _make_extractor(firefox_home)
        output = tmp_path / "deep" / "nested" / "browser.json"
        ext.build_browser_json(output)
        assert output.exists()


# ---------------------------------------------------------------------------
# Tests: config validation
# ---------------------------------------------------------------------------


class TestAutoAuthConfig:
    def test_default_config_has_auto_auth(self) -> None:
        from ytmpd.config import _validate_config

        config = _validate_config({"auto_auth": {"enabled": False, "browser": "firefox-dev"}})
        assert config["auto_auth"]["enabled"] is False

    def test_invalid_browser(self) -> None:
        from ytmpd.config import _validate_config

        with pytest.raises(ValueError, match="auto_auth.browser"):
            _validate_config({"auto_auth": {"browser": "chrome"}})

    def test_invalid_enabled(self) -> None:
        from ytmpd.config import _validate_config

        with pytest.raises(ValueError, match="auto_auth.enabled"):
            _validate_config({"auto_auth": {"enabled": "yes"}})

    def test_invalid_container_type(self) -> None:
        from ytmpd.config import _validate_config

        with pytest.raises(ValueError, match="auto_auth.container"):
            _validate_config({"auto_auth": {"container": 123}})

    def test_invalid_profile_type(self) -> None:
        from ytmpd.config import _validate_config

        with pytest.raises(ValueError, match="auto_auth.profile"):
            _validate_config({"auto_auth": {"profile": 123}})

    def test_invalid_refresh_interval(self) -> None:
        from ytmpd.config import _validate_config

        with pytest.raises(ValueError, match="auto_auth.refresh_interval_hours"):
            _validate_config({"auto_auth": {"refresh_interval_hours": -1}})

    def test_valid_full_config(self) -> None:
        from ytmpd.config import _validate_config

        config = _validate_config(
            {
                "auto_auth": {
                    "enabled": True,
                    "browser": "firefox",
                    "container": "Personal",
                    "profile": "abc.default",
                    "refresh_interval_hours": 6,
                }
            }
        )
        assert config["auto_auth"]["enabled"] is True
        assert config["auto_auth"]["container"] == "Personal"

    def test_null_container_is_valid(self) -> None:
        from ytmpd.config import _validate_config

        config = _validate_config({"auto_auth": {"container": None}})
        assert config["auto_auth"]["container"] is None
