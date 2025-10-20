"""Tests for MPD client module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from mpd import CommandError, ConnectionError

from ytmpd.exceptions import MPDConnectionError, MPDPlaylistError
from ytmpd.mpd_client import MPDClient, TrackWithMetadata


class TestMPDClientInit:
    """Tests for MPDClient initialization."""

    def test_init_stores_socket_path(self):
        """Test that socket path is stored correctly."""
        client = MPDClient("/path/to/socket")
        assert client.socket_path == "/path/to/socket"

    def test_init_expands_tilde(self):
        """Test that ~ is expanded in socket path."""
        client = MPDClient("~/mpd/socket")
        assert client.socket_path == str(Path.home() / "mpd" / "socket")

    def test_init_starts_disconnected(self):
        """Test that client starts in disconnected state."""
        client = MPDClient("/path/to/socket")
        assert not client.is_connected()


class TestMPDClientConnection:
    """Tests for MPD connection management."""

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_connect_success(self, mock_path, mock_mpd_base):
        """Test successful connection to MPD."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        # Verify connection was attempted
        mock_client.connect.assert_called_once_with(client.socket_path)
        assert client.is_connected()

    def test_connect_socket_missing(self):
        """Test connection fails when socket file doesn't exist."""
        # Use a temp path that definitely doesn't exist
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent_socket = Path(tmpdir) / "nonexistent" / "socket"

            client = MPDClient(str(nonexistent_socket))

            with pytest.raises(MPDConnectionError) as exc_info:
                client.connect()

            assert "socket not found" in str(exc_info.value).lower()
            assert "Is MPD running?" in str(exc_info.value)

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_connect_mpd_not_running(self, mock_path, mock_mpd_base):
        """Test connection fails when MPD is not running."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock connection failure
        mock_client = Mock()
        mock_client.connect.side_effect = ConnectionError("Connection refused")
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")

        with pytest.raises(MPDConnectionError) as exc_info:
            client.connect()

        assert "Failed to connect" in str(exc_info.value)

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_disconnect(self, mock_path, mock_mpd_base):
        """Test disconnection from MPD."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()
        client.disconnect()

        # Verify disconnect was called
        mock_client.close.assert_called_once()
        mock_client.disconnect.assert_called_once()
        assert not client.is_connected()

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_disconnect_handles_errors(self, mock_path, mock_mpd_base):
        """Test disconnect handles errors gracefully."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_client.close.side_effect = Exception("Close failed")
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        # Should not raise exception
        client.disconnect()
        assert not client.is_connected()

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_is_connected_pings_mpd(self, mock_path, mock_mpd_base):
        """Test is_connected() verifies connection with ping."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        # Should return True when ping succeeds
        assert client.is_connected()
        mock_client.ping.assert_called()

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_is_connected_detects_stale_connection(self, mock_path, mock_mpd_base):
        """Test is_connected() detects stale connections."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        # Simulate stale connection
        mock_client.ping.side_effect = ConnectionError("Connection lost")

        assert not client.is_connected()


class TestMPDClientPlaylists:
    """Tests for playlist operations."""

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_list_playlists_success(self, mock_path, mock_mpd_base):
        """Test listing playlists returns correct data."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_client.listplaylists.return_value = [
            {"playlist": "Favorites"},
            {"playlist": "Workout"},
            {"playlist": "YT: Chill"},
        ]
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        playlists = client.list_playlists()

        assert playlists == ["Favorites", "Workout", "YT: Chill"]
        mock_client.listplaylists.assert_called_once()

    @patch("ytmpd.mpd_client.MPDClientBase")
    def test_list_playlists_not_connected(self, mock_mpd_base):
        """Test listing playlists fails when not connected and reconnect fails."""
        # Make connection fail during reconnect attempt
        mock_mpd_base.return_value.connect.side_effect = ConnectionError("Connection refused")

        client = MPDClient("/path/to/socket")

        with pytest.raises(MPDConnectionError) as exc_info:
            client.list_playlists()

        assert "MPD socket not found" in str(exc_info.value)

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_playlist_exists_true(self, mock_path, mock_mpd_base):
        """Test playlist_exists returns True for existing playlist."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_client.listplaylists.return_value = [
            {"playlist": "Favorites"},
            {"playlist": "Workout"},
        ]
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        assert client.playlist_exists("Favorites")

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_playlist_exists_false(self, mock_path, mock_mpd_base):
        """Test playlist_exists returns False for non-existent playlist."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_client.listplaylists.return_value = [
            {"playlist": "Favorites"},
        ]
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        assert not client.playlist_exists("NonExistent")

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_create_or_replace_playlist_new(self, mock_path, mock_mpd_base):
        """Test creating a new playlist."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_client.listplaylists.return_value = []
        mock_mpd_base.return_value = mock_client

        # Mock playlist directory and file
        mock_playlist_dir = Mock()
        mock_playlist_file = Mock()
        mock_playlist_dir.__truediv__ = Mock(return_value=mock_playlist_file)

        client = MPDClient("/path/to/socket")
        client.connect()
        client.playlist_directory = mock_playlist_dir

        tracks = [
            TrackWithMetadata(url="http://example.com/track1.m4a", title="Track 1", artist="Artist 1", video_id="test_video_id"),
            TrackWithMetadata(url="http://example.com/track2.m4a", title="Track 2", artist="Artist 2", video_id="test_video_id"),
        ]
        client.create_or_replace_playlist("Test Playlist", tracks)

        # Verify M3U file was written
        mock_playlist_file.write_text.assert_called_once()
        written_content = mock_playlist_file.write_text.call_args[0][0]
        assert "#EXTM3U" in written_content
        assert "#EXTINF:-1,Artist 1 - Track 1" in written_content
        assert "http://example.com/track1.m4a" in written_content
        assert "#EXTINF:-1,Artist 2 - Track 2" in written_content
        assert "http://example.com/track2.m4a" in written_content

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_create_or_replace_playlist_replaces_existing(
        self, mock_path, mock_mpd_base
    ):
        """Test replacing an existing playlist."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_client.listplaylists.return_value = [{"playlist": "Test Playlist"}]
        mock_mpd_base.return_value = mock_client

        # Mock playlist directory and file
        mock_playlist_dir = Mock()
        mock_playlist_file = Mock()
        mock_playlist_dir.__truediv__ = Mock(return_value=mock_playlist_file)

        client = MPDClient("/path/to/socket")
        client.connect()
        client.playlist_directory = mock_playlist_dir

        tracks = [TrackWithMetadata(url="http://example.com/track1.m4a", title="Track 1", artist="Artist 1", video_id="test_video_id")]
        client.create_or_replace_playlist("Test Playlist", tracks)

        # Verify M3U file was written (replaces existing file automatically)
        mock_playlist_file.write_text.assert_called_once()
        written_content = mock_playlist_file.write_text.call_args[0][0]
        assert "#EXTM3U" in written_content
        assert "http://example.com/track1.m4a" in written_content

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_create_or_replace_playlist_empty_urls(self, mock_path, mock_mpd_base):
        """Test creating playlist with empty URL list is skipped."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        # Should not raise, just skip
        client.create_or_replace_playlist("Empty Playlist", [])

        # Verify no operations were performed
        mock_client.save.assert_not_called()

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_create_or_replace_playlist_handles_invalid_urls(
        self, mock_path, mock_mpd_base
    ):
        """Test that all URLs are written to M3U file (MPD validates them later)."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_client.listplaylists.return_value = []
        mock_mpd_base.return_value = mock_client

        # Mock playlist directory and file
        mock_playlist_dir = Mock()
        mock_playlist_file = Mock()
        mock_playlist_dir.__truediv__ = Mock(return_value=mock_playlist_file)

        client = MPDClient("/path/to/socket")
        client.connect()
        client.playlist_directory = mock_playlist_dir

        tracks = [
            TrackWithMetadata(url="http://example.com/track1.m4a", title="Track 1", artist="Artist 1", video_id="test_video_id"),
            TrackWithMetadata(url="http://example.com/invalid.m4a", title="Invalid", artist="Artist", video_id="test_video_id"),
            TrackWithMetadata(url="http://example.com/track2.m4a", title="Track 2", artist="Artist 2", video_id="test_video_id"),
        ]
        client.create_or_replace_playlist("Test Playlist", tracks)

        # All tracks should be written to M3U file
        mock_playlist_file.write_text.assert_called_once()
        written_content = mock_playlist_file.write_text.call_args[0][0]
        assert "http://example.com/track1.m4a" in written_content
        assert "http://example.com/invalid.m4a" in written_content
        assert "http://example.com/track2.m4a" in written_content

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_create_or_replace_playlist_all_urls_fail(self, mock_path, mock_mpd_base):
        """Test that write errors are properly raised."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_client.listplaylists.return_value = []
        mock_mpd_base.return_value = mock_client

        # Mock playlist directory and file that raises an error on write
        mock_playlist_dir = Mock()
        mock_playlist_file = Mock()
        mock_playlist_file.write_text.side_effect = PermissionError("Cannot write")
        mock_playlist_dir.__truediv__ = Mock(return_value=mock_playlist_file)

        client = MPDClient("/path/to/socket")
        client.connect()
        client.playlist_directory = mock_playlist_dir

        tracks = [TrackWithMetadata(url="http://example.com/track.m4a", title="Track", artist="Artist", video_id="test_video_id")]

        with pytest.raises(MPDPlaylistError) as exc_info:
            client.create_or_replace_playlist("Test Playlist", tracks)

        assert "Error creating M3U playlist" in str(exc_info.value)

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_clear_playlist_success(self, mock_path, mock_mpd_base):
        """Test deleting a playlist."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        client.clear_playlist("Test Playlist")

        mock_client.rm.assert_called_once_with("Test Playlist")

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_clear_playlist_not_found(self, mock_path, mock_mpd_base):
        """Test deleting non-existent playlist logs warning."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_client.rm.side_effect = CommandError("No such playlist")
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        # Should not raise, just log warning
        client.clear_playlist("NonExistent")

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_add_to_playlist_success(self, mock_path, mock_mpd_base):
        """Test adding URL to existing playlist."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        client.add_to_playlist("Test Playlist", "http://example.com/track.m4a")

        mock_client.playlistadd.assert_called_once_with(
            "Test Playlist", "http://example.com/track.m4a"
        )

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_add_to_playlist_not_found(self, mock_path, mock_mpd_base):
        """Test adding to non-existent playlist raises error."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_client.playlistadd.side_effect = CommandError("No such playlist")
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        with pytest.raises(MPDPlaylistError) as exc_info:
            client.add_to_playlist("NonExistent", "http://example.com/track.m4a")

        assert "does not exist" in str(exc_info.value)


class TestMPDClientReconnection:
    """Tests for reconnection logic."""

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_is_connected_detects_lost_connection(self, mock_path, mock_mpd_base):
        """Test that is_connected() properly detects when connection is lost."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_mpd_base.return_value = mock_client

        client = MPDClient("/path/to/socket")
        client.connect()

        # Initially connected
        assert client.is_connected()

        # Simulate connection lost
        mock_client.ping.side_effect = ConnectionError("Connection lost")

        # Should detect the lost connection
        assert not client.is_connected()

        # And set internal state correctly
        assert not client._connected


class TestMPDClientContextManager:
    """Tests for context manager support."""

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_context_manager_connects_and_disconnects(self, mock_path, mock_mpd_base):
        """Test context manager properly connects and disconnects."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_mpd_base.return_value = mock_client

        with MPDClient("/path/to/socket") as client:
            assert client.is_connected()

        # After exiting context, should be disconnected
        assert not client.is_connected()
        mock_client.close.assert_called()
        mock_client.disconnect.assert_called()

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_context_manager_disconnects_on_exception(self, mock_path, mock_mpd_base):
        """Test context manager disconnects even when exception occurs."""
        # Mock socket exists
        mock_path.return_value.expanduser.return_value.exists.return_value = True

        # Mock MPD client
        mock_client = Mock()
        mock_mpd_base.return_value = mock_client

        try:
            with MPDClient("/path/to/socket") as client:
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Should still disconnect
        mock_client.close.assert_called()
        mock_client.disconnect.assert_called()
