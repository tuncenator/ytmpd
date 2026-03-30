"""Firefox cookie extraction for YouTube Music authentication.

Extracts cookies from Firefox's SQLite database and generates browser.json
files compatible with ytmusicapi browser authentication.
"""

import hashlib
import json
import logging
import shutil
import sqlite3
import tempfile
import time
from configparser import ConfigParser
from pathlib import Path

from ytmpd.exceptions import CookieExtractionError

logger = logging.getLogger(__name__)

# Firefox install IDs used to find the default profile in profiles.ini
_INSTALL_IDS = {
    "firefox": "Install4F96D1932A9F858E",
    "firefox-dev": "Install46F492E0ACFF84D4",
}

# Minimum required cookies for ytmusicapi browser auth
_REQUIRED_COOKIES = {"SID", "HSID", "SSID"}
_SAPISID_COOKIES = {"SAPISID", "__Secure-3PAPISID"}

_ORIGIN = "https://music.youtube.com"


class FirefoxCookieExtractor:
    """Extracts YouTube Music cookies from a Firefox profile."""

    def __init__(
        self,
        browser: str = "firefox",
        profile: str | None = None,
        container: str | None = None,
    ) -> None:
        if browser not in _INSTALL_IDS:
            raise CookieExtractionError(
                f"Unsupported browser: {browser!r}. Must be 'firefox' or 'firefox-dev'."
            )
        self.browser = browser
        self.profile = profile
        self.container = container
        self._firefox_dir = Path.home() / ".mozilla" / "firefox"

    def find_profile_dir(self) -> Path:
        """Find the Firefox profile directory.

        If self.profile is set, uses it directly. Otherwise reads profiles.ini
        to find the default profile for the configured browser type.

        Returns:
            Full path to the Firefox profile directory.

        Raises:
            CookieExtractionError: If profile cannot be found.
        """
        if self.profile:
            profile_path = self._firefox_dir / self.profile
            if not profile_path.is_dir():
                raise CookieExtractionError(f"Firefox profile directory not found: {profile_path}")
            return profile_path

        profiles_ini = self._firefox_dir / "profiles.ini"
        if not profiles_ini.exists():
            raise CookieExtractionError(f"Firefox profiles.ini not found: {profiles_ini}")

        parser = ConfigParser()
        parser.read(profiles_ini)

        install_id = _INSTALL_IDS[self.browser]
        if install_id not in parser:
            raise CookieExtractionError(
                f"No {self.browser} installation found in profiles.ini "
                f"(looking for section [{install_id}])"
            )

        default_profile = parser[install_id].get("Default")
        if not default_profile:
            raise CookieExtractionError(
                f"No default profile set for {self.browser} in profiles.ini"
            )

        profile_path = self._firefox_dir / default_profile
        if not profile_path.is_dir():
            raise CookieExtractionError(f"Firefox profile directory not found: {profile_path}")
        return profile_path

    def _resolve_container_filter(self, profile_dir: Path) -> str:
        """Resolve the container name to an originAttributes filter value.

        Args:
            profile_dir: Path to the Firefox profile directory.

        Returns:
            Empty string for no container, or '^userContextId=N' for a named container.

        Raises:
            CookieExtractionError: If the container name is not found.
        """
        if self.container is None:
            return ""

        containers_file = profile_dir / "containers.json"
        if not containers_file.exists():
            raise CookieExtractionError(
                f"containers.json not found in profile: {profile_dir}. "
                "Firefox Multi-Account Containers may not be installed."
            )

        try:
            data = json.loads(containers_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            raise CookieExtractionError(f"Failed to read containers.json: {e}") from e

        for identity in data.get("identities", []):
            if identity.get("name") == self.container:
                user_context_id = identity["userContextId"]
                return f"^userContextId={user_context_id}"

        available = [i["name"] for i in data.get("identities", []) if i.get("name")]
        raise CookieExtractionError(
            f"Container {self.container!r} not found. Available containers: {available}"
        )

    def extract_cookies(self, domain: str = ".youtube.com") -> list[dict]:
        """Extract cookies for a domain from the Firefox cookie database.

        Copies the SQLite database to a temp directory to avoid locking
        issues with a running Firefox instance.

        Args:
            domain: Domain to filter cookies for.

        Returns:
            List of cookie dicts with keys: name, value, host, expiry, isSecure.

        Raises:
            CookieExtractionError: If extraction fails.
        """
        profile_dir = self.find_profile_dir()
        cookies_db = profile_dir / "cookies.sqlite"

        if not cookies_db.exists():
            raise CookieExtractionError(f"cookies.sqlite not found in profile: {profile_dir}")

        origin_filter = self._resolve_container_filter(profile_dir)

        tmpdir = tempfile.mkdtemp(prefix="ytmpd_cookies_")
        try:
            tmp_db = Path(tmpdir) / "cookies.sqlite"
            shutil.copy2(cookies_db, tmp_db)
            for suffix in ("-wal", "-shm"):
                wal_file = profile_dir / f"cookies.sqlite{suffix}"
                if wal_file.exists():
                    shutil.copy2(wal_file, Path(tmpdir) / f"cookies.sqlite{suffix}")

            try:
                conn = sqlite3.connect(f"file:{tmp_db}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
            except sqlite3.Error as e:
                raise CookieExtractionError(f"Failed to open cookie database: {e}") from e

            try:
                cursor = conn.execute(
                    "SELECT name, value, host, expiry, isSecure "
                    "FROM moz_cookies "
                    "WHERE host LIKE ? AND originAttributes = ?",
                    (f"%{domain}", origin_filter),
                )
                cookies = [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                raise CookieExtractionError(f"Failed to query cookie database: {e}") from e
            finally:
                conn.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

        logger.info(
            "Extracted %d cookies for domain %s (container=%s)",
            len(cookies),
            domain,
            self.container,
        )
        return cookies

    def validate_cookies(self, cookies: list[dict]) -> bool:
        """Validate that required cookies are present and not expired.

        Args:
            cookies: List of cookie dicts from extract_cookies().

        Returns:
            True if all required cookies are present and valid.
        """
        cookie_names = {c["name"] for c in cookies}
        now = int(time.time())

        missing_required = _REQUIRED_COOKIES - cookie_names
        if missing_required:
            logger.warning("Missing required cookies: %s", missing_required)
            return False

        has_sapisid = bool(_SAPISID_COOKIES & cookie_names)
        if not has_sapisid:
            logger.warning("Missing SAPISID cookie (need at least one of %s)", _SAPISID_COOKIES)
            return False

        for cookie in cookies:
            if cookie["expiry"] > 0 and cookie["expiry"] < now:
                logger.warning(
                    "Cookie %s is expired (expiry=%d, now=%d)",
                    cookie["name"],
                    cookie["expiry"],
                    now,
                )

        # Check that critical cookies are not expired
        for cookie in cookies:
            if cookie["name"] in (_REQUIRED_COOKIES | _SAPISID_COOKIES):
                if 0 < cookie["expiry"] < now:
                    logger.warning("Critical cookie %s is expired", cookie["name"])
                    return False

        return True

    def build_browser_json(self, output_path: Path) -> Path:
        """Extract cookies and write a browser.json file for ytmusicapi.

        Args:
            output_path: Where to write the browser.json file.

        Returns:
            The output path.

        Raises:
            CookieExtractionError: If extraction or validation fails.
        """
        cookies = self.extract_cookies()

        if not self.validate_cookies(cookies):
            raise CookieExtractionError(
                "Cookie validation failed: required cookies missing or expired"
            )

        cookie_string = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

        # Find SAPISID for authorization header
        sapisid = None
        for c in cookies:
            if c["name"] == "__Secure-3PAPISID":
                sapisid = c["value"]
                break
        if sapisid is None:
            for c in cookies:
                if c["name"] == "SAPISID":
                    sapisid = c["value"]
                    break

        if sapisid is None:
            raise CookieExtractionError(
                "Cannot compute SAPISIDHASH: no SAPISID or __Secure-3PAPISID cookie"
            )

        # Compute SAPISIDHASH (for auth type detection only; ytmusicapi recomputes per-request)
        ts = str(int(time.time()))
        sha1 = hashlib.sha1(f"{ts} {sapisid} {_ORIGIN}".encode()).hexdigest()
        authorization = f"SAPISIDHASH {ts}_{sha1}"

        headers = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate",
            "authorization": authorization,
            "content-encoding": "gzip",
            "content-type": "application/json",
            "cookie": cookie_string,
            "origin": _ORIGIN,
            "user-agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0"
            ),
            "x-goog-authuser": "0",
            "x-origin": _ORIGIN,
        }

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(headers, indent=4) + "\n")

        logger.info("Wrote browser.json to %s", output_path)
        return output_path
