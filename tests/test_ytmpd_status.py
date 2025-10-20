"""Tests for bin/ytmpd-status script.

Tests cover MPD connection, track classification, color selection,
and output formatting functionality.
"""

import importlib.machinery
import importlib.util
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import the script module
script_path = Path(__file__).parent.parent / "bin" / "ytmpd-status"
spec = importlib.util.spec_from_file_location("ytmpd_status", script_path,
                                              loader=importlib.machinery.SourceFileLoader("ytmpd_status", str(script_path)))
ytmpd_status = importlib.util.module_from_spec(spec)
sys.modules["ytmpd_status"] = ytmpd_status
spec.loader.exec_module(ytmpd_status)


class TestGetMPDClient:
    """Test MPD client connection."""

    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.MPDClient")
    def test_successful_connection(self, mock_mpd_class):
        """Test successful MPD connection."""
        mock_client = MagicMock()
        mock_mpd_class.return_value = mock_client

        client = ytmpd_status.get_mpd_client("localhost", 6601)

        assert client is not None
        mock_client.connect.assert_called_once_with("localhost", 6601)

    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.MPDClient")
    def test_connection_refused(self, mock_mpd_class):
        """Test connection failure when MPD is not running."""
        mock_client = MagicMock()
        mock_client.connect.side_effect = ConnectionRefusedError()
        mock_mpd_class.return_value = mock_client

        client = ytmpd_status.get_mpd_client("localhost", 6601)

        assert client is None

    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.MPDClient")
    def test_connection_os_error(self, mock_mpd_class):
        """Test connection failure with OS error."""
        mock_client = MagicMock()
        mock_client.connect.side_effect = OSError()
        mock_mpd_class.return_value = mock_client

        client = ytmpd_status.get_mpd_client("localhost", 6601)

        assert client is None


class TestGetTrackType:
    """Test track type classification."""

    def test_youtube_proxy_url(self):
        """Test YouTube track detection from proxy URL."""
        file_path = "http://localhost:6602/proxy/dQw4w9WgXcQ"
        track_type = ytmpd_status.get_track_type(file_path)
        assert track_type == "youtube"

    def test_local_file_no_database(self, tmp_path):
        """Test local file detection when database doesn't exist."""
        # Point to non-existent database
        with patch("ytmpd_status.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            file_path = "/music/song.mp3"
            track_type = ytmpd_status.get_track_type(file_path)
            assert track_type == "local"

    def test_youtube_from_database(self, tmp_path):
        """Test YouTube track detection from database."""
        # Create temporary database
        db_path = tmp_path / ".config" / "ytmpd"
        db_path.mkdir(parents=True)
        db_file = db_path / "track_mapping.db"

        # Create database with test data
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE tracks (
                file TEXT PRIMARY KEY,
                video_id TEXT,
                title TEXT,
                artist TEXT
            )
        """)
        cursor.execute(
            "INSERT INTO tracks (file, video_id, title, artist) VALUES (?, ?, ?, ?)",
            ("_youtube/test.xspf", "dQw4w9WgXcQ", "Test Song", "Test Artist")
        )
        conn.commit()
        conn.close()

        # Test detection
        with patch("ytmpd_status.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            track_type = ytmpd_status.get_track_type("_youtube/test.xspf")
            assert track_type == "youtube"

    def test_local_file_not_in_database(self, tmp_path):
        """Test local file detection when not in database."""
        # Create temporary database
        db_path = tmp_path / ".config" / "ytmpd"
        db_path.mkdir(parents=True)
        db_file = db_path / "track_mapping.db"

        # Create empty database
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE tracks (
                file TEXT PRIMARY KEY,
                video_id TEXT,
                title TEXT,
                artist TEXT
            )
        """)
        conn.commit()
        conn.close()

        # Test detection
        with patch("ytmpd_status.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            track_type = ytmpd_status.get_track_type("/music/local.mp3")
            assert track_type == "local"

    def test_unknown_http_url(self, tmp_path):
        """Test unknown HTTP URL when not in database."""
        db_path = tmp_path / ".config" / "ytmpd"
        db_path.mkdir(parents=True)
        db_file = db_path / "track_mapping.db"

        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE tracks (
                file TEXT PRIMARY KEY,
                video_id TEXT
            )
        """)
        conn.commit()
        conn.close()

        with patch("ytmpd_status.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            track_type = ytmpd_status.get_track_type("http://example.com/song.mp3")
            assert track_type == "unknown"

    def test_database_error_fallback(self, tmp_path):
        """Test fallback to heuristic when database query fails."""
        # Create database path but with bad permissions or corrupted
        db_path = tmp_path / ".config" / "ytmpd"
        db_path.mkdir(parents=True)

        with patch("ytmpd_status.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            # Create a file instead of a database to trigger error
            (db_path / "track_mapping.db").write_text("not a database")

            track_type = ytmpd_status.get_track_type("/music/song.mp3")
            assert track_type == "local"


class TestFormatTime:
    """Test time formatting."""

    def test_format_seconds(self):
        """Test formatting integer seconds."""
        assert ytmpd_status.format_time(0) == "0:00"
        assert ytmpd_status.format_time(45) == "0:45"
        assert ytmpd_status.format_time(60) == "1:00"
        assert ytmpd_status.format_time(185) == "3:05"
        assert ytmpd_status.format_time(3665) == "61:05"

    def test_format_string_seconds(self):
        """Test formatting string seconds."""
        assert ytmpd_status.format_time("0") == "0:00"
        assert ytmpd_status.format_time("123") == "2:03"
        assert ytmpd_status.format_time("3600") == "60:00"

    def test_format_float_seconds(self):
        """Test formatting float seconds."""
        assert ytmpd_status.format_time("123.5") == "2:03"
        assert ytmpd_status.format_time(123.9) == "2:03"

    def test_format_invalid_input(self):
        """Test handling of invalid input."""
        assert ytmpd_status.format_time("invalid") == "0:00"
        assert ytmpd_status.format_time(None) == "0:00"
        assert ytmpd_status.format_time("") == "0:00"


class TestTruncate:
    """Test text truncation."""

    def test_no_truncation_needed(self):
        """Test when text is shorter than max length."""
        text = "Short text"
        assert ytmpd_status.truncate(text, 50) == "Short text"

    def test_exact_length(self):
        """Test when text is exactly max length."""
        text = "Exactly ten"
        assert ytmpd_status.truncate(text, 11) == "Exactly ten"

    def test_truncation_with_ellipsis(self):
        """Test truncation with ellipsis."""
        text = "This is a very long text that needs truncation"
        result = ytmpd_status.truncate(text, 20)
        assert len(result) == 20
        assert result.endswith("...")
        assert result == "This is a very lo..."

    def test_truncation_edge_case(self):
        """Test truncation with very short max length."""
        text = "Hello World"
        result = ytmpd_status.truncate(text, 5)
        assert len(result) == 5
        assert result == "He..."


class TestColorSelection:
    """Test color selection for different states and track types."""

    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_youtube_playing_color(self, mock_track_type, mock_client, capsys):
        """Test color for playing YouTube track."""
        # Mock MPD client
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "60",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "http://localhost:6602/proxy/test",
            "time": "180",
        }

        mock_track_type.return_value = "youtube"

        # Run main
        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 3
        assert lines[2] == "#FF6B35"  # Orange for YouTube playing

    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_youtube_paused_color(self, mock_track_type, mock_client, capsys):
        """Test color for paused YouTube track."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "pause",
            "elapsed": "60",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "http://localhost:6602/proxy/test",
            "time": "180",
        }

        mock_track_type.return_value = "youtube"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert lines[2] == "#FFB84D"  # Light orange for YouTube paused

    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_local_playing_color(self, mock_track_type, mock_client, capsys):
        """Test color for playing local track."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "60",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "/music/song.mp3",
            "time": "180",
        }

        mock_track_type.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert lines[2] == "#00FF00"  # Green for local playing

    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_local_paused_color(self, mock_track_type, mock_client, capsys):
        """Test color for paused local track."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "pause",
            "elapsed": "60",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "/music/song.mp3",
            "time": "180",
        }

        mock_track_type.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert lines[2] == "#FFFF00"  # Yellow for local paused

    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_mpd_client")
    def test_mpd_not_running(self, mock_client, capsys):
        """Test output when MPD is not running."""
        mock_client.return_value = None

        with pytest.raises(SystemExit):
            ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 3
        assert "MPD stopped" in lines[0]
        assert lines[2] == "#808080"  # Gray

    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_mpd_client")
    def test_mpd_stopped(self, mock_client, capsys):
        """Test output when MPD is stopped."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {"state": "stop"}
        mock_mpd.currentsong.return_value = {}

        with pytest.raises(SystemExit):
            ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 3
        assert "Stopped" in lines[0]
        assert lines[2] == "#808080"  # Gray


class TestOutputFormatting:
    """Test output formatting for i3blocks."""

    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_basic_output_format(self, mock_track_type, mock_client, capsys):
        """Test basic output format."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "45",
            "duration": "180",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "/music/test.mp3",
        }

        mock_track_type.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        assert len(lines) == 3
        assert lines[0].startswith("▶")  # Playing icon
        assert "Test Artist - Test Song" in lines[0]
        # With progress bar, output is "[0:45 █░... 3:00]"
        assert "0:45" in lines[0]
        assert "3:00" in lines[0]
        assert "[" in lines[0] and "]" in lines[0]

    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_truncation_in_output(self, mock_track_type, mock_client, capsys, monkeypatch):
        """Test output truncation."""
        monkeypatch.setenv("YTMPD_STATUS_MAX_LENGTH", "30")

        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "45",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Very Long Song Title That Needs Truncation",
            "artist": "Very Long Artist Name",
            "file": "/music/test.mp3",
            "time": "180",
        }

        mock_track_type.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        assert len(lines[0]) <= 30
        assert "…" in lines[0]  # Check for proper ellipsis character

    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_pause_icon(self, mock_track_type, mock_client, capsys):
        """Test pause icon display."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "pause",
            "elapsed": "45",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "/music/test.mp3",
            "time": "180",
        }

        mock_track_type.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        assert lines[0].startswith("⏸")  # Pause icon


class TestCalculateProgress:
    """Test progress bar calculation."""

    def test_basic_progress(self):
        """Test basic progress calculation."""
        # 50% progress
        filled = ytmpd_status.calculate_progress(30.0, 60.0, 10)
        assert filled == 5

    def test_zero_duration(self):
        """Test handling of zero duration."""
        filled = ytmpd_status.calculate_progress(10.0, 0.0, 10)
        assert filled == 0

    def test_zero_elapsed(self):
        """Test handling of zero elapsed time."""
        filled = ytmpd_status.calculate_progress(0.0, 60.0, 10)
        assert filled == 0

    def test_elapsed_greater_than_duration(self):
        """Test when elapsed exceeds duration."""
        filled = ytmpd_status.calculate_progress(70.0, 60.0, 10)
        assert filled == 10

    def test_very_short_elapsed(self):
        """Test very short elapsed time (less than one bar unit)."""
        filled = ytmpd_status.calculate_progress(1.0, 100.0, 10)
        assert filled == 0  # 1% progress rounds down to 0

    def test_almost_complete(self):
        """Test progress just before completion."""
        filled = ytmpd_status.calculate_progress(59.0, 60.0, 10)
        assert filled == 9

    def test_exactly_complete(self):
        """Test progress at exactly 100%."""
        filled = ytmpd_status.calculate_progress(60.0, 60.0, 10)
        assert filled == 10

    def test_different_bar_lengths(self):
        """Test calculation with different bar lengths."""
        # Bar length of 5
        filled = ytmpd_status.calculate_progress(30.0, 60.0, 5)
        assert filled == 2  # 50% of 5 = 2.5, rounds to 2

        # Bar length of 20
        filled = ytmpd_status.calculate_progress(30.0, 60.0, 20)
        assert filled == 10  # 50% of 20 = 10

    def test_negative_values(self):
        """Test handling of negative values."""
        filled = ytmpd_status.calculate_progress(-10.0, 60.0, 10)
        assert filled == 0


class TestRenderProgressBar:
    """Test progress bar rendering."""

    def test_blocks_style_full(self):
        """Test blocks style with full bar."""
        bar = ytmpd_status.render_progress_bar(10, 10, "blocks")
        assert bar == "██████████"

    def test_blocks_style_empty(self):
        """Test blocks style with empty bar."""
        bar = ytmpd_status.render_progress_bar(0, 10, "blocks")
        assert bar == "░░░░░░░░░░"

    def test_blocks_style_half(self):
        """Test blocks style with half-filled bar."""
        bar = ytmpd_status.render_progress_bar(5, 10, "blocks")
        assert bar == "█████░░░░░"

    def test_smooth_style_full(self):
        """Test smooth style with full bar."""
        bar = ytmpd_status.render_progress_bar(10, 10, "smooth")
        assert bar == "▰▰▰▰▰▰▰▰▰▰"

    def test_smooth_style_empty(self):
        """Test smooth style with empty bar."""
        bar = ytmpd_status.render_progress_bar(0, 10, "smooth")
        assert bar == "▱▱▱▱▱▱▱▱▱▱"

    def test_smooth_style_partial(self):
        """Test smooth style with partial bar."""
        bar = ytmpd_status.render_progress_bar(3, 10, "smooth")
        assert bar == "▰▰▰▱▱▱▱▱▱▱"

    def test_simple_style_full(self):
        """Test simple style with full bar."""
        bar = ytmpd_status.render_progress_bar(10, 10, "simple")
        assert bar == "##########"

    def test_simple_style_empty(self):
        """Test simple style with empty bar."""
        bar = ytmpd_status.render_progress_bar(0, 10, "simple")
        assert bar == "----------"

    def test_simple_style_partial(self):
        """Test simple style with partial bar."""
        bar = ytmpd_status.render_progress_bar(7, 10, "simple")
        assert bar == "#######---"

    def test_unknown_style_defaults_to_blocks(self):
        """Test that unknown style defaults to blocks."""
        bar = ytmpd_status.render_progress_bar(5, 10, "unknown_style")
        assert bar == "█████░░░░░"

    def test_filled_exceeds_length(self):
        """Test when filled exceeds total length."""
        bar = ytmpd_status.render_progress_bar(15, 10, "blocks")
        assert bar == "██████████"

    def test_negative_filled(self):
        """Test with negative filled value."""
        bar = ytmpd_status.render_progress_bar(-5, 10, "blocks")
        assert bar == "░░░░░░░░░░"

    def test_different_bar_lengths(self):
        """Test rendering with different bar lengths."""
        # Bar length 5
        bar = ytmpd_status.render_progress_bar(2, 5, "blocks")
        assert bar == "██░░░"

        # Bar length 20
        bar = ytmpd_status.render_progress_bar(10, 20, "blocks")
        assert bar == "██████████░░░░░░░░░░"


class TestProgressBarIntegration:
    """Test progress bar integration with main output."""

    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_progress_bar_in_output_youtube(self, mock_track_type, mock_client, capsys):
        """Test progress bar appears in output for YouTube track."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "30.5",
            "duration": "60.0",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "http://localhost:6602/proxy/test123",
        }

        mock_track_type.return_value = "youtube"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        # Should contain smooth style bar (▰▱)
        assert "▰" in lines[0] or "▱" in lines[0]
        # Should have time before and after bar
        assert "0:30" in lines[0]
        assert "1:00" in lines[0]

    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_progress_bar_in_output_local(self, mock_track_type, mock_client, capsys):
        """Test progress bar appears in output for local track."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "45.0",
            "duration": "90.0",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Local Song",
            "artist": "Local Artist",
            "file": "/music/local.mp3",
        }

        mock_track_type.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        # Should contain blocks style bar (█░)
        assert "█" in lines[0] or "░" in lines[0]
        # Should have time before and after bar
        assert "0:45" in lines[0]
        assert "1:30" in lines[0]

    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_progress_bar_disabled(self, mock_track_type, mock_client, capsys, monkeypatch):
        """Test that progress bar can be disabled via environment variable."""
        monkeypatch.setenv("YTMPD_STATUS_SHOW_BAR", "false")

        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "30.0",
            "duration": "60.0",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "/music/test.mp3",
        }

        mock_track_type.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        # Should NOT contain bar characters
        assert "█" not in lines[0]
        assert "░" not in lines[0]
        assert "▰" not in lines[0]
        assert "▱" not in lines[0]

    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_custom_bar_length(self, mock_track_type, mock_client, capsys, monkeypatch):
        """Test custom bar length via environment variable."""
        monkeypatch.setenv("YTMPD_STATUS_BAR_LENGTH", "5")

        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "30.0",
            "duration": "60.0",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test",
            "artist": "Artist",
            "file": "/music/test.mp3",
        }

        mock_track_type.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        # Extract bar from output (should be 5 characters)
        # Bar should be between the two time stamps
        assert "█" in lines[0] or "░" in lines[0]

    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_forced_bar_style(self, mock_track_type, mock_client, capsys, monkeypatch):
        """Test forcing a specific bar style via environment variable."""
        monkeypatch.setenv("YTMPD_STATUS_BAR_STYLE", "simple")

        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "30.0",
            "duration": "60.0",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "http://localhost:6602/proxy/test123",
        }

        mock_track_type.return_value = "youtube"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        # Should use simple style (#-) instead of smooth (▰▱) for YouTube
        assert "#" in lines[0] or "-" in lines[0]
        assert "▰" not in lines[0]
        assert "▱" not in lines[0]

    @patch("ytmpd_status.get_mpd_client")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_track_type")
    def test_no_duration_no_bar(self, mock_track_type, mock_client, capsys):
        """Test that bar is not shown when duration is 0 or missing."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "30.0",
            "duration": "0",  # No duration
        }
        mock_mpd.currentsong.return_value = {
            "title": "Stream",
            "artist": "Live",
            "file": "http://stream.example.com/radio",
        }

        mock_track_type.return_value = "unknown"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")

        # Should NOT contain bar characters
        assert "█" not in lines[0]
        assert "░" not in lines[0]
        assert "▰" not in lines[0]
        assert "▱" not in lines[0]


class TestGetPlaylistContext:
    """Test playlist context retrieval."""

    def test_basic_playlist_context(self):
        """Test getting context from middle of playlist."""
        mock_client = MagicMock()
        mock_client.status.return_value = {
            "song": "4",  # 0-indexed position (5th song)
            "playlistlength": "10"
        }
        mock_client.currentsong.return_value = {"title": "Current"}

        # Mock next and prev track info
        mock_client.playlistinfo.side_effect = [
            [{"artist": "Next Artist", "title": "Next Title"}],  # Next track
            [{"artist": "Prev Artist", "title": "Prev Title"}],  # Prev track
        ]

        context = ytmpd_status.get_playlist_context(mock_client)

        assert context["current_pos"] == 5  # 1-indexed
        assert context["total"] == 10
        assert context["next"]["artist"] == "Next Artist"
        assert context["next"]["title"] == "Next Title"
        assert context["prev"]["artist"] == "Prev Artist"
        assert context["prev"]["title"] == "Prev Title"

    def test_first_track_in_playlist(self):
        """Test context when on first track."""
        mock_client = MagicMock()
        mock_client.status.return_value = {
            "song": "0",
            "playlistlength": "5"
        }
        mock_client.currentsong.return_value = {"title": "First"}
        mock_client.playlistinfo.return_value = [
            {"artist": "Next Artist", "title": "Next Title"}
        ]

        context = ytmpd_status.get_playlist_context(mock_client)

        assert context["current_pos"] == 1
        assert context["total"] == 5
        assert context["next"] is not None
        assert context["prev"] is None

    def test_last_track_in_playlist(self):
        """Test context when on last track."""
        mock_client = MagicMock()
        mock_client.status.return_value = {
            "song": "4",  # Last track (0-indexed)
            "playlistlength": "5"
        }
        mock_client.currentsong.return_value = {"title": "Last"}
        mock_client.playlistinfo.return_value = [
            {"artist": "Prev Artist", "title": "Prev Title"}
        ]

        context = ytmpd_status.get_playlist_context(mock_client)

        assert context["current_pos"] == 5
        assert context["total"] == 5
        assert context["next"] is None
        assert context["prev"] is not None

    def test_single_track_playlist(self):
        """Test context with only one track."""
        mock_client = MagicMock()
        mock_client.status.return_value = {
            "song": "0",
            "playlistlength": "1"
        }
        mock_client.currentsong.return_value = {"title": "Only"}

        context = ytmpd_status.get_playlist_context(mock_client)

        assert context["current_pos"] == 1
        assert context["total"] == 1
        assert context["next"] is None
        assert context["prev"] is None

    def test_no_song_playing(self):
        """Test context when no song is playing."""
        mock_client = MagicMock()
        mock_client.status.return_value = {
            "playlistlength": "5"
        }  # No "song" key
        mock_client.currentsong.return_value = {}

        context = ytmpd_status.get_playlist_context(mock_client)

        assert context["current_pos"] is None
        assert context["total"] is None
        assert context["next"] is None
        assert context["prev"] is None

    def test_exception_handling(self):
        """Test graceful handling of exceptions."""
        mock_client = MagicMock()
        mock_client.status.side_effect = Exception("Connection error")

        context = ytmpd_status.get_playlist_context(mock_client)

        assert context["current_pos"] is None
        assert context["total"] is None
        assert context["next"] is None
        assert context["prev"] is None


class TestGetSyncStatus:
    """Test sync status checking."""

    def test_local_file(self):
        """Test sync status for local file."""
        status = ytmpd_status.get_sync_status("/music/song.mp3")
        assert status == "local"

    def test_youtube_resolved(self, tmp_path):
        """Test sync status for resolved YouTube track."""
        # Create temporary database
        db_path = tmp_path / ".config" / "ytmpd"
        db_path.mkdir(parents=True)
        db_file = db_path / "track_mapping.db"

        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE tracks (
                video_id TEXT PRIMARY KEY,
                stream_url TEXT
            )
        """)
        cursor.execute(
            "INSERT INTO tracks (video_id, stream_url) VALUES (?, ?)",
            ("dQw4w9WgXcQ", "https://youtube.com/stream/url")
        )
        conn.commit()
        conn.close()

        with patch("ytmpd_status.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            status = ytmpd_status.get_sync_status("http://localhost:6602/proxy/dQw4w9WgXcQ")
            assert status == "resolved"

    def test_youtube_unresolved(self, tmp_path):
        """Test sync status for unresolved YouTube track."""
        # Create temporary database
        db_path = tmp_path / ".config" / "ytmpd"
        db_path.mkdir(parents=True)
        db_file = db_path / "track_mapping.db"

        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE tracks (
                video_id TEXT PRIMARY KEY,
                stream_url TEXT
            )
        """)
        cursor.execute(
            "INSERT INTO tracks (video_id, stream_url) VALUES (?, ?)",
            ("dQw4w9WgXcQ", None)  # NULL stream_url
        )
        conn.commit()
        conn.close()

        with patch("ytmpd_status.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            status = ytmpd_status.get_sync_status("http://localhost:6602/proxy/dQw4w9WgXcQ")
            assert status == "unresolved"

    def test_youtube_not_in_database(self, tmp_path):
        """Test sync status for YouTube track not in database."""
        # Create empty database
        db_path = tmp_path / ".config" / "ytmpd"
        db_path.mkdir(parents=True)
        db_file = db_path / "track_mapping.db"

        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE tracks (
                video_id TEXT PRIMARY KEY,
                stream_url TEXT
            )
        """)
        conn.commit()
        conn.close()

        with patch("ytmpd_status.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            status = ytmpd_status.get_sync_status("http://localhost:6602/proxy/dQw4w9WgXcQ")
            assert status == "unknown"

    def test_no_database(self, tmp_path):
        """Test sync status when database doesn't exist."""
        with patch("ytmpd_status.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            status = ytmpd_status.get_sync_status("http://localhost:6602/proxy/dQw4w9WgXcQ")
            assert status == "unknown"


class TestSmartTruncate:
    """Test smart truncation function."""

    def test_no_truncation_needed(self):
        """Test when text is already short enough."""
        text = "Short text"
        result = ytmpd_status.smart_truncate(text, 50)
        assert result == "Short text"

    def test_truncate_simple_text(self):
        """Test truncation of simple text without separator."""
        text = "This is a very long text that needs to be truncated"
        result = ytmpd_status.smart_truncate(text, 30)
        assert len(result) <= 30
        assert result.endswith("…")

    def test_preserve_artist_name(self):
        """Test that artist name is preserved when truncating."""
        text = "Artist Name - Very Long Song Title That Needs Truncation"
        result = ytmpd_status.smart_truncate(text, 40)
        assert "Artist Name" in result
        assert result.startswith("Artist Name")
        assert "…" in result

    def test_truncate_middle_of_long_title(self):
        """Test middle truncation for very long titles."""
        text = "Artist - This is an extremely long song title that should be truncated from the middle"
        result = ytmpd_status.smart_truncate(text, 50)
        assert len(result) <= 50
        assert "Artist" in result
        assert "…" in result
        # Should truncate from middle
        assert result.startswith("Artist - ")

    def test_truncate_short_title(self):
        """Test truncation of shorter title from end."""
        text = "Artist Name - Short Title Here"
        result = ytmpd_status.smart_truncate(text, 20)
        assert len(result) <= 20
        assert "Artist" in result
        assert "…" in result

    def test_very_long_artist_name(self):
        """Test truncation when artist name itself is too long."""
        text = "Very Long Artist Name That Exceeds Length - Song"
        result = ytmpd_status.smart_truncate(text, 30)
        assert len(result) <= 30
        assert result.endswith("…")

    def test_proper_ellipsis_character(self):
        """Test that proper ellipsis character (…) is used."""
        text = "A" * 100
        result = ytmpd_status.smart_truncate(text, 20)
        assert "…" in result
        assert "..." not in result  # Should not use three dots


class TestContextAwareMessaging:
    """Test context-aware messaging in output."""

    @patch("ytmpd_status.get_mpd_client")
    @patch("ytmpd_status.get_track_type")
    @patch("ytmpd_status.get_playlist_context")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_sync_status")
    def test_unresolved_youtube_track(self, mock_sync, mock_ctx, mock_track, mock_client, capsys):
        """Test 'Resolving...' message for unresolved YouTube track."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "30",
            "duration": "180",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "http://localhost:6602/proxy/test123",
        }
        mock_track.return_value = "youtube"
        mock_ctx.return_value = {"current_pos": None, "total": None, "next": None, "prev": None}
        mock_sync.return_value = "unresolved"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert "[Resolving...]" in lines[0]

    @patch("ytmpd_status.get_mpd_client")
    @patch("ytmpd_status.get_track_type")
    @patch("ytmpd_status.get_playlist_context")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_sync_status")
    def test_first_track_position(self, mock_sync, mock_ctx, mock_track, mock_client, capsys):
        """Test position display for first track."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "30",
            "duration": "180",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "/music/song.mp3",
        }
        mock_track.return_value = "local"
        mock_ctx.return_value = {"current_pos": 1, "total": 25, "next": {}, "prev": None}
        mock_sync.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert "[1/25]" in lines[0]

    @patch("ytmpd_status.get_mpd_client")
    @patch("ytmpd_status.get_track_type")
    @patch("ytmpd_status.get_playlist_context")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_sync_status")
    def test_last_track_position(self, mock_sync, mock_ctx, mock_track, mock_client, capsys):
        """Test position display for last track."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "30",
            "duration": "180",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "/music/song.mp3",
        }
        mock_track.return_value = "local"
        mock_ctx.return_value = {"current_pos": 25, "total": 25, "next": None, "prev": {}}
        mock_sync.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert "[25/25]" in lines[0]

    @patch("ytmpd_status.get_mpd_client")
    @patch("ytmpd_status.get_track_type")
    @patch("ytmpd_status.get_playlist_context")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_sync_status")
    def test_single_track_playlist(self, mock_sync, mock_ctx, mock_track, mock_client, capsys):
        """Test position display for single track playlist."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "30",
            "duration": "180",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "/music/song.mp3",
        }
        mock_track.return_value = "local"
        mock_ctx.return_value = {"current_pos": 1, "total": 1, "next": None, "prev": None}
        mock_sync.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert "[1/1]" in lines[0]


class TestCompactMode:
    """Test compact mode functionality."""

    @patch.dict("os.environ", {"YTMPD_STATUS_COMPACT": "true"})
    @patch("ytmpd_status.get_mpd_client")
    @patch("ytmpd_status.get_track_type")
    @patch("ytmpd_status.get_playlist_context")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_sync_status")
    def test_compact_mode_output(self, mock_sync, mock_ctx, mock_track, mock_client, capsys):
        """Test that compact mode produces minimal output."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "30",
            "duration": "180",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "/music/song.mp3",
        }
        mock_track.return_value = "local"
        mock_ctx.return_value = {"current_pos": None, "total": None, "next": None, "prev": None}
        mock_sync.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        output = lines[0]

        # Should have icon, artist, and title
        assert "▶" in output
        assert "Test Artist" in output
        assert "Test Song" in output

        # Should NOT have time or progress bar
        assert "[" not in output  # No brackets for time
        assert "0:30" not in output
        assert "3:00" not in output


class TestNextPrevDisplay:
    """Test next/previous track display."""

    @patch.dict("os.environ", {"YTMPD_STATUS_SHOW_NEXT": "true"})
    @patch("ytmpd_status.get_mpd_client")
    @patch("ytmpd_status.get_track_type")
    @patch("ytmpd_status.get_playlist_context")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_sync_status")
    def test_show_next_track(self, mock_sync, mock_ctx, mock_track, mock_client, capsys):
        """Test next track display when enabled."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "30",
            "duration": "180",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Current Song",
            "artist": "Current Artist",
            "file": "/music/song.mp3",
        }
        mock_track.return_value = "local"
        mock_ctx.return_value = {
            "current_pos": 5,
            "total": 10,
            "next": {"artist": "Next Artist", "title": "Next Song"},
            "prev": None
        }
        mock_sync.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        output = captured.out

        # Should have next track info
        assert "↓" in output
        assert "Next Artist" in output
        assert "Next Song" in output

    @patch.dict("os.environ", {"YTMPD_STATUS_SHOW_PREV": "true"})
    @patch("ytmpd_status.get_mpd_client")
    @patch("ytmpd_status.get_track_type")
    @patch("ytmpd_status.get_playlist_context")
    @patch("sys.argv", ["ytmpd-status"])
    @patch("ytmpd_status.get_sync_status")
    def test_show_prev_track(self, mock_sync, mock_ctx, mock_track, mock_client, capsys):
        """Test previous track display when enabled."""
        mock_mpd = MagicMock()
        mock_client.return_value = mock_mpd
        mock_mpd.status.return_value = {
            "state": "play",
            "elapsed": "30",
            "duration": "180",
        }
        mock_mpd.currentsong.return_value = {
            "title": "Current Song",
            "artist": "Current Artist",
            "file": "/music/song.mp3",
        }
        mock_track.return_value = "local"
        mock_ctx.return_value = {
            "current_pos": 5,
            "total": 10,
            "next": None,
            "prev": {"artist": "Prev Artist", "title": "Prev Song"}
        }
        mock_sync.return_value = "local"

        ytmpd_status.main()

        captured = capsys.readouterr()
        output = captured.out

        # Should have prev track info
        assert "↑" in output
        assert "Prev Artist" in output
        assert "Prev Song" in output
