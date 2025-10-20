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

    @patch("ytmpd_status.MPDClient")
    def test_successful_connection(self, mock_mpd_class):
        """Test successful MPD connection."""
        mock_client = MagicMock()
        mock_mpd_class.return_value = mock_client

        client = ytmpd_status.get_mpd_client("localhost", 6601)

        assert client is not None
        mock_client.connect.assert_called_once_with("localhost", 6601)

    @patch("ytmpd_status.MPDClient")
    def test_connection_refused(self, mock_mpd_class):
        """Test connection failure when MPD is not running."""
        mock_client = MagicMock()
        mock_client.connect.side_effect = ConnectionRefusedError()
        mock_mpd_class.return_value = mock_client

        client = ytmpd_status.get_mpd_client("localhost", 6601)

        assert client is None

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

    @patch("ytmpd_status.get_mpd_client")
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
        assert lines[0].endswith("...")

    @patch("ytmpd_status.get_mpd_client")
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
