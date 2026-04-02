"""Integration tests for HistoryReporter wiring in the daemon."""

import threading
import time
from unittest.mock import MagicMock, patch

from ytmpd.daemon import YTMPDaemon
from ytmpd.history_reporter import HistoryReporter


def _base_config() -> dict:
    """Return a config dict with history_reporting and proxy enabled."""
    return {
        "mpd_socket_path": "/tmp/mpd.sock",
        "mpd_playlist_directory": "/tmp/playlists",
        "stream_cache_hours": 5,
        "playlist_prefix": "YT: ",
        "sync_interval_minutes": 30,
        "enable_auto_sync": True,
        "proxy_enabled": True,
        "proxy_host": "localhost",
        "proxy_port": 8080,
        "proxy_track_mapping_db": "/tmp/track_mapping.db",
        "auto_auth": {"enabled": False},
        "history_reporting": {
            "enabled": True,
            "min_play_seconds": 45,
        },
    }


def _disabled_config() -> dict:
    cfg = _base_config()
    cfg["history_reporting"]["enabled"] = False
    return cfg


# Shared decorator stack for mocking daemon dependencies
_daemon_patches = [
    "ytmpd.daemon.YTMusicClient",
    "ytmpd.daemon.MPDClient",
    "ytmpd.daemon.StreamResolver",
    "ytmpd.daemon.SyncEngine",
    "ytmpd.daemon.load_config",
    "ytmpd.daemon.get_config_dir",
]


def _make_daemon(tmp_path, config_dict):
    """Create a YTMPDaemon with full mock stack and given config."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "browser.json").touch()

    with (
        patch("ytmpd.daemon.get_config_dir", return_value=config_dir),
        patch("ytmpd.daemon.load_config", return_value=config_dict),
        patch("ytmpd.daemon.YTMusicClient"),
        patch("ytmpd.daemon.MPDClient"),
        patch("ytmpd.daemon.StreamResolver"),
        patch("ytmpd.daemon.SyncEngine"),
        patch("ytmpd.daemon.ICYProxyServer"),
        patch("ytmpd.daemon.TrackStore"),
        patch("ytmpd.daemon.HistoryReporter") as mock_hr_cls,
    ):
        daemon = YTMPDaemon()
        return daemon, mock_hr_cls


class TestDaemonCreatesHistoryReporter:
    """Verify daemon creates/skips HistoryReporter based on config."""

    def test_creates_reporter_when_enabled(self, tmp_path) -> None:
        daemon, mock_hr_cls = _make_daemon(tmp_path, _base_config())
        assert daemon._history_reporter is not None
        mock_hr_cls.assert_called_once()

    def test_skips_reporter_when_disabled(self, tmp_path) -> None:
        daemon, mock_hr_cls = _make_daemon(tmp_path, _disabled_config())
        assert daemon._history_reporter is None
        mock_hr_cls.assert_not_called()

    def test_passes_correct_config(self, tmp_path) -> None:
        daemon, mock_hr_cls = _make_daemon(tmp_path, _base_config())
        call_kwargs = mock_hr_cls.call_args.kwargs
        assert call_kwargs["mpd_socket_path"] == "/tmp/mpd.sock"
        assert call_kwargs["min_play_seconds"] == 45

    def test_skips_reporter_when_proxy_disabled(self, tmp_path) -> None:
        cfg = _base_config()
        cfg["proxy_enabled"] = False
        daemon, mock_hr_cls = _make_daemon(tmp_path, cfg)
        # Without proxy (and therefore no TrackStore), reporter should not be created
        assert daemon._history_reporter is None


class TestDaemonHistoryThread:
    """Verify daemon spawns and stops the history thread."""

    def test_spawns_thread_on_run(self, tmp_path) -> None:
        daemon, _ = _make_daemon(tmp_path, _base_config())
        # Make run() non-blocking: reporter.run() returns immediately
        daemon._history_reporter.run = MagicMock()
        daemon._running = True

        # Manually call _history_loop to verify it calls run with the shutdown event
        daemon._history_loop()
        daemon._history_reporter.run.assert_called_once_with(daemon._history_shutdown)

    def test_thread_starts_in_run(self, tmp_path) -> None:
        daemon, _ = _make_daemon(tmp_path, _base_config())
        daemon._history_reporter.run = MagicMock()

        # Mock out the rest of run() to prevent it from actually running
        with (
            patch.object(daemon.mpd_client, "connect"),
            patch.object(daemon, "_perform_sync"),
        ):
            daemon._running = True

            # Start daemon in a thread so we can stop it
            def start_and_stop():
                # Give run() a moment to spawn threads, then stop
                time.sleep(0.2)
                daemon._running = False

            stopper = threading.Thread(target=start_and_stop, daemon=True)
            stopper.start()
            daemon.run()
            stopper.join(timeout=2)

        assert daemon._history_thread is not None

    def test_stop_signals_shutdown(self, tmp_path) -> None:
        daemon, _ = _make_daemon(tmp_path, _base_config())
        daemon._running = True

        # Create a real thread that blocks on the shutdown event
        def fake_run(shutdown_event):
            shutdown_event.wait()

        daemon._history_reporter.run = MagicMock(side_effect=fake_run)
        daemon._history_thread = threading.Thread(
            target=daemon._history_loop, name="history-reporter", daemon=True
        )
        daemon._history_thread.start()

        # Verify thread is alive
        assert daemon._history_thread.is_alive()

        # stop() should signal and join
        daemon.stop()
        assert daemon._history_shutdown.is_set()
        assert not daemon._history_thread.is_alive()


class TestEndToEndMock:
    """Simulate track change and verify report_history is called."""

    def test_track_change_triggers_report(self) -> None:
        """Full path: HistoryReporter detects track change -> calls report_history."""
        ytmusic = MagicMock()
        ytmusic.get_song.return_value = {"videoId": "dQw4w9WgXc0"}
        ytmusic.report_history.return_value = True

        track_store = MagicMock()

        reporter = HistoryReporter(
            mpd_socket_path="/tmp/mpd.sock",
            ytmusic=ytmusic,
            track_store=track_store,
            proxy_config={"host": "localhost", "port": 8080, "enabled": True},
            min_play_seconds=5,
        )

        # Simulate: was playing a track long enough, then stopped
        reporter._current_track_url = "http://localhost:8080/proxy/dQw4w9WgXc0"
        reporter._current_track_start = time.monotonic() - 60
        reporter._accumulated_play = 0.0
        reporter._pause_start = None
        reporter._last_state = "play"

        # Simulate _report_track directly
        reporter._report_track("http://localhost:8080/proxy/dQw4w9WgXc0")

        ytmusic.get_song.assert_called_once_with("dQw4w9WgXc0")
        ytmusic.report_history.assert_called_once()
