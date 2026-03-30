"""Tests for auto-auth daemon integration (Phase 2)."""

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from ytmpd.exceptions import CookieExtractionError

# ---------------------------------------------------------------------------
# YTMusicClient.refresh_auth tests
# ---------------------------------------------------------------------------


class TestRefreshAuth:
    """Tests for YTMusicClient.refresh_auth()."""

    @patch("ytmpd.ytmusic.YTMusic")
    def test_refresh_auth_success(self, mock_ytmusic_cls, tmp_path):
        """refresh_auth reinitializes the client and resets cache."""
        from ytmpd.ytmusic import YTMusicClient

        auth_file = tmp_path / "browser.json"
        auth_file.write_text("{}")

        client = YTMusicClient(auth_file=auth_file)
        # Simulate an old cached auth check
        client._auth_cache_time = time.time()
        client._auth_cache_valid = False

        result = client.refresh_auth()

        assert result is True
        assert client._auth_cache_time == 0.0
        # _init_client was called again (YTMusic instantiated twice: init + refresh)
        assert mock_ytmusic_cls.call_count == 2

    @patch("ytmpd.ytmusic.YTMusic")
    def test_refresh_auth_with_new_path(self, mock_ytmusic_cls, tmp_path):
        """refresh_auth updates auth_file when a new path is provided."""
        from ytmpd.ytmusic import YTMusicClient

        old_auth = tmp_path / "old.json"
        old_auth.write_text("{}")
        new_auth = tmp_path / "new.json"
        new_auth.write_text("{}")

        client = YTMusicClient(auth_file=old_auth)
        result = client.refresh_auth(auth_file=new_auth)

        assert result is True
        assert client.auth_file == new_auth

    @patch("ytmpd.ytmusic.YTMusic")
    def test_refresh_auth_failure(self, mock_ytmusic_cls, tmp_path):
        """refresh_auth returns False when _init_client raises."""
        from ytmpd.ytmusic import YTMusicClient

        auth_file = tmp_path / "browser.json"
        auth_file.write_text("{}")

        client = YTMusicClient(auth_file=auth_file)

        # Make _init_client fail on second call
        mock_ytmusic_cls.side_effect = Exception("bad credentials")

        result = client.refresh_auth()
        assert result is False


# ---------------------------------------------------------------------------
# Daemon auto-auth integration tests
# ---------------------------------------------------------------------------


def _make_daemon(tmp_path, auto_auth_enabled=False, extra_config=None):
    """Create a mocked YTMPDaemon for testing.

    Returns the daemon and the mocks dict.
    """
    from ytmpd.daemon import YTMPDaemon

    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "browser.json").touch()

    config = {
        "mpd_socket_path": "/tmp/mpd.sock",
        "stream_cache_hours": 5,
        "playlist_prefix": "YT: ",
        "sync_interval_minutes": 30,
        "enable_auto_sync": True,
        "proxy_enabled": False,
        "auto_auth": {
            "enabled": auto_auth_enabled,
            "browser": "firefox-dev",
            "profile": None,
            "container": None,
            "refresh_interval_hours": 12,
        },
    }
    if extra_config:
        config.update(extra_config)

    with (
        patch("ytmpd.daemon.get_config_dir", return_value=config_dir),
        patch("ytmpd.daemon.load_config", return_value=config),
        patch("ytmpd.daemon.YTMusicClient") as mock_ytmusic,
        patch("ytmpd.daemon.MPDClient"),
        patch("ytmpd.daemon.StreamResolver"),
        patch("ytmpd.daemon.SyncEngine"),
    ):
        mock_ytmusic_instance = mock_ytmusic.return_value
        mock_ytmusic_instance.is_authenticated.return_value = (True, "")
        mock_ytmusic_instance.refresh_auth.return_value = True

        daemon = YTMPDaemon()

    return daemon


class TestDaemonAutoAuthInit:
    """Tests for daemon auto-auth initialization."""

    def test_auto_auth_disabled_by_default(self, tmp_path):
        """When auto_auth.enabled is False, auto-auth thread is not created."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=False)
        assert daemon._auto_auth_enabled is False
        assert daemon._auto_auth_thread is None

    def test_auto_auth_enabled(self, tmp_path):
        """When auto_auth.enabled is True, auto-auth state is initialized."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=True)
        assert daemon._auto_auth_enabled is True
        assert daemon._last_reactive_refresh == 0.0

    def test_auto_auth_state_defaults(self, tmp_path):
        """State includes auto-auth fields with defaults."""
        daemon = _make_daemon(tmp_path)
        assert daemon.state.get("last_auto_refresh") is None
        assert daemon.state.get("auto_refresh_failures") == 0


def _patch_auto_refresh(daemon, tmp_path, mock_extractor_cls):
    """Set up mocks for _attempt_auto_refresh to work with tmp_path.

    The method calls get_config_dir() and does a tmp file rename,
    so we need to mock get_config_dir and make build_browser_json
    create the expected temp file.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)

    def _create_tmp_file(output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("{}")
        return output_path

    mock_extractor_cls.return_value.build_browser_json.side_effect = _create_tmp_file
    return patch("ytmpd.daemon.get_config_dir", return_value=config_dir)


class TestAttemptAutoRefresh:
    """Tests for _attempt_auto_refresh()."""

    @patch("ytmpd.daemon.FirefoxCookieExtractor")
    def test_successful_refresh(self, mock_extractor_cls, tmp_path):
        """Successful extraction + client refresh returns True."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=True)
        daemon.ytmusic_client.refresh_auth.return_value = True

        ctx = _patch_auto_refresh(daemon, tmp_path, mock_extractor_cls)
        with ctx:
            result = daemon._attempt_auto_refresh()

        assert result is True
        assert daemon.state["auto_refresh_failures"] == 0
        assert daemon.state["last_auto_refresh"] is not None
        mock_extractor_cls.return_value.build_browser_json.assert_called_once()
        daemon.ytmusic_client.refresh_auth.assert_called_once()

    @patch("ytmpd.daemon.FirefoxCookieExtractor")
    def test_extraction_failure(self, mock_extractor_cls, tmp_path):
        """CookieExtractionError returns False and increments failure count."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=True)

        mock_extractor = mock_extractor_cls.return_value
        mock_extractor.build_browser_json.side_effect = CookieExtractionError("no cookies")

        with patch("ytmpd.daemon.get_config_dir", return_value=tmp_path / "config"):
            result = daemon._attempt_auto_refresh()

        assert result is False
        assert daemon.state["auto_refresh_failures"] == 1

    @patch("ytmpd.daemon.FirefoxCookieExtractor")
    def test_client_refresh_failure(self, mock_extractor_cls, tmp_path):
        """When client reinit fails, returns False and increments failures."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=True)
        daemon.ytmusic_client.refresh_auth.return_value = False

        ctx = _patch_auto_refresh(daemon, tmp_path, mock_extractor_cls)
        with ctx:
            result = daemon._attempt_auto_refresh()

        assert result is False
        assert daemon.state["auto_refresh_failures"] == 1

    @patch("ytmpd.daemon.FirefoxCookieExtractor")
    def test_failure_count_increments(self, mock_extractor_cls, tmp_path):
        """Repeated failures increment the counter."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=True)
        daemon.state["auto_refresh_failures"] = 3

        mock_extractor = mock_extractor_cls.return_value
        mock_extractor.build_browser_json.side_effect = CookieExtractionError("fail")

        with patch("ytmpd.daemon.get_config_dir", return_value=tmp_path / "config"):
            daemon._attempt_auto_refresh()
        assert daemon.state["auto_refresh_failures"] == 4

    @patch("ytmpd.daemon.FirefoxCookieExtractor")
    def test_success_resets_failure_count(self, mock_extractor_cls, tmp_path):
        """Successful refresh resets the failure counter to 0."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=True)
        daemon.state["auto_refresh_failures"] = 5
        daemon.ytmusic_client.refresh_auth.return_value = True

        ctx = _patch_auto_refresh(daemon, tmp_path, mock_extractor_cls)
        with ctx:
            result = daemon._attempt_auto_refresh()
        assert result is True
        assert daemon.state["auto_refresh_failures"] == 0


class TestAutoAuthLoop:
    """Tests for _auto_auth_loop() thread behavior."""

    @patch("ytmpd.daemon.FirefoxCookieExtractor")
    def test_loop_stops_on_shutdown(self, mock_extractor_cls, tmp_path):
        """Auto-auth loop exits when shutdown event is set."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=True)
        daemon._running = True

        # Set a very short interval so we don't wait long
        daemon.auto_auth_config["refresh_interval_hours"] = 0.0001  # ~0.36s

        # Start the loop in a thread
        thread = threading.Thread(target=daemon._auto_auth_loop, daemon=True)
        thread.start()

        # Signal shutdown after a brief moment
        time.sleep(0.1)
        daemon._running = False
        daemon._auto_auth_shutdown.set()

        thread.join(timeout=3)
        assert not thread.is_alive()

    @patch("ytmpd.daemon.FirefoxCookieExtractor")
    def test_loop_calls_refresh(self, mock_extractor_cls, tmp_path):
        """Auto-auth loop calls _attempt_auto_refresh on schedule."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=True)
        daemon._running = True

        mock_extractor = mock_extractor_cls.return_value
        mock_extractor.build_browser_json.return_value = Path("/tmp/browser.json")
        daemon.ytmusic_client.refresh_auth.return_value = True

        # Very short interval
        daemon.auto_auth_config["refresh_interval_hours"] = 0.00005  # ~0.18s

        thread = threading.Thread(target=daemon._auto_auth_loop, daemon=True)
        thread.start()

        # Wait for at least one refresh cycle
        time.sleep(0.5)

        daemon._running = False
        daemon._auto_auth_shutdown.set()
        thread.join(timeout=3)

        # Should have called build_browser_json at least once
        assert mock_extractor.build_browser_json.call_count >= 1


class TestReactiveRefresh:
    """Tests for reactive refresh in _perform_sync()."""

    @patch("ytmpd.daemon.FirefoxCookieExtractor")
    def test_reactive_refresh_on_auth_error(self, mock_extractor_cls, tmp_path):
        """Auth error during sync triggers reactive refresh."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=True)
        daemon._running = True

        # First sync raises auth error, retry succeeds
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.playlists_synced = 1
        mock_result.playlists_failed = 0
        mock_result.tracks_added = 5
        mock_result.tracks_failed = 0
        mock_result.duration_seconds = 1.0
        mock_result.errors = []

        daemon.sync_engine.sync_all_playlists.side_effect = [
            Exception("unauthorized access"),
            mock_result,
        ]

        daemon.ytmusic_client.refresh_auth.return_value = True

        ctx = _patch_auto_refresh(daemon, tmp_path, mock_extractor_cls)
        with ctx:
            daemon._perform_sync()

        # Should have attempted extraction
        mock_extractor_cls.return_value.build_browser_json.assert_called_once()
        # Sync should have been called twice (original + retry)
        assert daemon.sync_engine.sync_all_playlists.call_count == 2
        # State should reflect success from retry
        assert daemon.state["last_sync_result"]["success"] is True

    @patch("ytmpd.daemon.FirefoxCookieExtractor")
    def test_reactive_refresh_cooldown(self, mock_extractor_cls, tmp_path):
        """Reactive refresh respects the cooldown period."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=True)
        daemon._running = True

        # Set last reactive refresh to recent past (within cooldown)
        daemon._last_reactive_refresh = time.time()

        daemon.sync_engine.sync_all_playlists.side_effect = Exception("unauthorized")

        daemon._perform_sync()

        # Should NOT have attempted extraction due to cooldown
        mock_extractor_cls.assert_not_called()

    def test_reactive_refresh_skipped_when_disabled(self, tmp_path):
        """Reactive refresh does not trigger when auto_auth is disabled."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=False)
        daemon._running = True

        daemon.sync_engine.sync_all_playlists.side_effect = Exception("unauthorized")

        with patch("ytmpd.daemon.FirefoxCookieExtractor") as mock_cls:
            daemon._perform_sync()
            mock_cls.assert_not_called()

    @patch("ytmpd.daemon.FirefoxCookieExtractor")
    def test_no_reactive_refresh_on_non_auth_error(self, mock_extractor_cls, tmp_path):
        """Non-auth errors don't trigger reactive refresh."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=True)
        daemon._running = True

        daemon.sync_engine.sync_all_playlists.side_effect = Exception("network timeout")

        daemon._perform_sync()

        mock_extractor_cls.assert_not_called()


class TestCmdStatusAutoAuth:
    """Tests for auto-auth fields in _cmd_status()."""

    def test_status_includes_auto_auth_disabled(self, tmp_path):
        """Status response includes auto_auth_enabled=False when disabled."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=False)
        daemon.ytmusic_client.is_authenticated.return_value = (True, "")

        response = daemon._cmd_status()

        assert response["auto_auth_enabled"] is False
        assert response["last_auto_refresh"] is None
        assert response["auto_refresh_failures"] == 0

    def test_status_includes_auto_auth_enabled(self, tmp_path):
        """Status response includes auto-auth state when enabled."""
        daemon = _make_daemon(tmp_path, auto_auth_enabled=True)
        daemon.ytmusic_client.is_authenticated.return_value = (True, "")
        daemon.state["last_auto_refresh"] = "2026-03-30T12:00:00Z"
        daemon.state["auto_refresh_failures"] = 2

        response = daemon._cmd_status()

        assert response["auto_auth_enabled"] is True
        assert response["last_auto_refresh"] == "2026-03-30T12:00:00Z"
        assert response["auto_refresh_failures"] == 2


class TestStatePersistence:
    """Tests for auto-auth state persistence."""

    def test_state_persists_across_save_load(self, tmp_path):
        """Auto-auth state fields are saved and loaded correctly."""
        daemon = _make_daemon(tmp_path)
        daemon.state["last_auto_refresh"] = "2026-03-30T14:00:00Z"
        daemon.state["auto_refresh_failures"] = 3
        daemon._save_state()

        # Reload state
        new_state = daemon._load_state()
        assert new_state["last_auto_refresh"] == "2026-03-30T14:00:00Z"
        assert new_state["auto_refresh_failures"] == 3

    def test_old_state_file_gets_defaults(self, tmp_path):
        """Loading a state file without auto-auth keys adds defaults."""
        daemon = _make_daemon(tmp_path)

        # Simulate old state file without auto-auth keys
        import json

        with open(daemon.state_file, "w") as f:
            json.dump({"last_sync": None, "daemon_start_time": None}, f)

        state = daemon._load_state()
        assert state["last_auto_refresh"] is None
        assert state["auto_refresh_failures"] == 0
