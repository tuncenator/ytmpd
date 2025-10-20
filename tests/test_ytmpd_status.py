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

        assert len(lines) == 3
        assert lines[0].startswith("▶")  # Playing icon
        assert "Test Artist - Test Song" in lines[0]
        assert "[0:45/3:00]" in lines[0]

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
