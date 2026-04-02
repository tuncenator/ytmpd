"""Unit tests for HistoryReporter."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from ytmpd.history_reporter import HistoryReporter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_reporter(min_play_seconds: int = 30) -> HistoryReporter:
    """Build a HistoryReporter with mocked dependencies."""
    return HistoryReporter(
        mpd_socket_path="/tmp/mpd.sock",
        ytmusic=MagicMock(),
        track_store=MagicMock(),
        proxy_config={"host": "localhost", "port": 8080, "enabled": True},
        min_play_seconds=min_play_seconds,
    )


def _set_mpd_state(
    reporter: HistoryReporter,
    state: str = "play",
    file_url: str | None = "http://localhost:8080/proxy/dQw4w9WgXcQ",
) -> None:
    """Configure the mock MPD to return given state and song."""
    mpd = MagicMock()
    mpd.status.return_value = {"state": state}
    song: dict[str, str] = {}
    if file_url:
        song["file"] = file_url
    mpd.currentsong.return_value = song
    reporter._mpd = mpd


# ---------------------------------------------------------------------------
# Video ID extraction
# ---------------------------------------------------------------------------


class TestExtractVideoId:
    def test_valid_proxy_url(self) -> None:
        r = _make_reporter()
        assert r._extract_video_id("http://localhost:8080/proxy/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_valid_proxy_url_with_hyphens(self) -> None:
        r = _make_reporter()
        assert r._extract_video_id("http://localhost:8080/proxy/a-b_c123456") == "a-b_c123456"

    def test_invalid_url_no_proxy(self) -> None:
        r = _make_reporter()
        assert r._extract_video_id("http://example.com/song.mp3") is None

    def test_empty_string(self) -> None:
        r = _make_reporter()
        assert r._extract_video_id("") is None

    def test_wrong_length_video_id(self) -> None:
        r = _make_reporter()
        assert r._extract_video_id("http://localhost:8080/proxy/short") is None

    def test_non_proxy_path(self) -> None:
        r = _make_reporter()
        assert r._extract_video_id("http://localhost:8080/stream/dQw4w9WgXcQ") is None


# ---------------------------------------------------------------------------
# State transitions and reporting
# ---------------------------------------------------------------------------


class TestHandlePlayerEvent:
    """Tests for the _handle_player_event state machine."""

    def _setup_playing(
        self,
        reporter: HistoryReporter,
        url: str = "http://localhost:8080/proxy/dQw4w9WgXcQ",
        elapsed: float = 60.0,
    ) -> None:
        """Set reporter state as if a track has been playing for *elapsed* seconds."""
        reporter._current_track_url = url
        reporter._current_track_start = time.monotonic() - elapsed
        reporter._accumulated_play = 0.0
        reporter._pause_start = None
        reporter._last_state = "play"

    # -- play -> play (different track), duration met --

    def test_track_change_reports_previous(self) -> None:
        r = _make_reporter(min_play_seconds=30)
        self._setup_playing(r, elapsed=60)
        _set_mpd_state(r, "play", "http://localhost:8080/proxy/AAAAAAAAAAA")

        r._handle_player_event()

        r._ytmusic.get_song.assert_called_once_with("dQw4w9WgXcQ")
        r._ytmusic.report_history.assert_called_once()

    # -- play -> play (different track), duration NOT met --

    def test_track_change_skips_if_short(self) -> None:
        r = _make_reporter(min_play_seconds=30)
        self._setup_playing(r, elapsed=5)
        _set_mpd_state(r, "play", "http://localhost:8080/proxy/AAAAAAAAAAA")

        r._handle_player_event()

        r._ytmusic.get_song.assert_not_called()

    # -- play -> stop, duration met --

    def test_stop_reports_previous(self) -> None:
        r = _make_reporter(min_play_seconds=30)
        self._setup_playing(r, elapsed=45)
        _set_mpd_state(r, "stop", None)

        r._handle_player_event()

        r._ytmusic.get_song.assert_called_once_with("dQw4w9WgXcQ")

    # -- play -> pause (same track) --

    def test_pause_does_not_report(self) -> None:
        r = _make_reporter(min_play_seconds=30)
        url = "http://localhost:8080/proxy/dQw4w9WgXcQ"
        self._setup_playing(r, url=url, elapsed=60)
        _set_mpd_state(r, "pause", url)

        r._handle_player_event()

        r._ytmusic.get_song.assert_not_called()
        assert r._pause_start is not None

    # -- pause -> play (same track = resume) --

    def test_resume_does_not_report(self) -> None:
        r = _make_reporter(min_play_seconds=30)
        url = "http://localhost:8080/proxy/dQw4w9WgXcQ"
        r._current_track_url = url
        r._current_track_start = time.monotonic() - 20
        r._accumulated_play = 0.0
        r._pause_start = time.monotonic() - 5
        r._last_state = "pause"
        _set_mpd_state(r, "play", url)

        r._handle_player_event()

        r._ytmusic.get_song.assert_not_called()
        assert r._pause_start is None

    # -- pause -> play (different track), duration met --

    def test_pause_then_different_track_reports(self) -> None:
        r = _make_reporter(min_play_seconds=10)
        url_old = "http://localhost:8080/proxy/dQw4w9WgXcQ"
        r._current_track_url = url_old
        r._current_track_start = time.monotonic() - 25
        r._accumulated_play = 0.0
        r._pause_start = time.monotonic() - 5  # paused for 5s
        r._last_state = "pause"
        _set_mpd_state(r, "play", "http://localhost:8080/proxy/BBBBBBBBBBB")

        r._handle_player_event()

        # Should report old track (20s play - pause excluded via _compute_elapsed)
        r._ytmusic.get_song.assert_called_once_with("dQw4w9WgXcQ")

    # -- stop -> play --

    def test_stop_to_play_starts_tracking(self) -> None:
        r = _make_reporter()
        r._last_state = "stop"
        r._current_track_url = None
        r._current_track_start = None
        _set_mpd_state(r, "play", "http://localhost:8080/proxy/CCCCCCCCCCC")

        r._handle_player_event()

        assert r._current_track_url == "http://localhost:8080/proxy/CCCCCCCCCCC"
        assert r._current_track_start is not None


# ---------------------------------------------------------------------------
# Pause time exclusion
# ---------------------------------------------------------------------------


class TestPauseExclusion:
    def test_pause_time_not_counted(self) -> None:
        r = _make_reporter(min_play_seconds=30)
        url = "http://localhost:8080/proxy/dQw4w9WgXcQ"

        # Simulate: played 20s, paused, resumed, played 15s more => 35s total play
        r._current_track_url = url
        r._accumulated_play = 20.0
        r._current_track_start = time.monotonic() - 15  # 15s since resume
        r._pause_start = None
        r._last_state = "play"

        elapsed = r._compute_elapsed()
        assert elapsed == pytest.approx(35.0, abs=1.0)

    def test_elapsed_while_paused(self) -> None:
        r = _make_reporter()
        r._current_track_start = time.monotonic() - 50
        r._accumulated_play = 0.0
        r._pause_start = time.monotonic() - 10  # paused 10s ago

        elapsed = r._compute_elapsed()
        # Should be ~40s (50s total - 10s paused)
        assert elapsed == pytest.approx(40.0, abs=1.0)


# ---------------------------------------------------------------------------
# Non-proxy URL
# ---------------------------------------------------------------------------


class TestNonProxyUrl:
    def test_non_proxy_url_not_reported(self) -> None:
        r = _make_reporter(min_play_seconds=5)
        r._current_track_url = "http://example.com/song.mp3"
        r._current_track_start = time.monotonic() - 60
        r._accumulated_play = 0.0
        r._pause_start = None
        r._last_state = "play"
        _set_mpd_state(r, "stop", None)

        r._handle_player_event()

        r._ytmusic.get_song.assert_not_called()


# ---------------------------------------------------------------------------
# Error recovery
# ---------------------------------------------------------------------------


class TestErrorRecovery:
    def test_ytmusic_failure_does_not_crash(self) -> None:
        r = _make_reporter(min_play_seconds=5)
        r._current_track_url = "http://localhost:8080/proxy/dQw4w9WgXcQ"
        r._current_track_start = time.monotonic() - 60
        r._accumulated_play = 0.0
        r._pause_start = None
        r._last_state = "play"
        r._ytmusic.get_song.side_effect = Exception("API down")
        _set_mpd_state(r, "stop", None)

        # Should not raise
        r._handle_player_event()

    def test_mpd_reconnects_on_connection_loss(self) -> None:
        r = _make_reporter()
        shutdown = threading.Event()

        call_count = 0

        def fake_connect() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Connection refused")
            # Second call succeeds -- set up a mock MPD
            mpd = MagicMock()
            mpd.status.return_value = {"state": "stop"}
            mpd.currentsong.return_value = {}
            mpd.idle.side_effect = lambda *a: shutdown.set()
            r._mpd = mpd

        # Stop after two connect attempts
        def wait_side_effect(timeout: float = 0) -> bool:
            return call_count >= 2

        shutdown.wait = wait_side_effect  # type: ignore[assignment]
        shutdown.is_set = lambda: call_count >= 2  # type: ignore[assignment]

        with patch.object(r, "_connect", side_effect=fake_connect):
            r.run(shutdown)

        assert call_count == 2


# ---------------------------------------------------------------------------
# Clean shutdown
# ---------------------------------------------------------------------------


class TestShutdown:
    def test_run_exits_on_shutdown_event(self) -> None:
        r = _make_reporter()
        shutdown = threading.Event()

        mpd = MagicMock()
        mpd.status.return_value = {"state": "stop"}
        mpd.currentsong.return_value = {}

        def idle_blocks(*args: object) -> list[str]:
            shutdown.set()
            return ["player"]

        mpd.idle.side_effect = idle_blocks

        with patch.object(r, "_connect", side_effect=lambda: setattr(r, "_mpd", mpd)):
            r.run(shutdown)

        assert shutdown.is_set()
