"""Unit tests for ytmpd.ytmusic module."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from ytmpd.exceptions import YTMusicAPIError, YTMusicAuthError, YTMusicNotFoundError
from ytmpd.ytmusic import Playlist, Track, YTMusicClient


class TestYTMusicClient:
    """Tests for YTMusicClient class."""

    @pytest.fixture
    def mock_oauth_file(self, tmp_path: Path) -> Path:
        """Create a mock OAuth credentials file."""
        oauth_file = tmp_path / "oauth.json"
        oauth_file.write_text(
            json.dumps(
                {
                    "access_token": "mock_token",
                    "refresh_token": "mock_refresh",
                    "token_type": "Bearer",
                }
            )
        )
        return oauth_file

    @pytest.fixture
    def mock_ytmusic(self) -> Mock:
        """Create a mock YTMusic instance."""
        return Mock()

    @pytest.fixture
    def client(self, mock_oauth_file: Path, mock_ytmusic: Mock) -> YTMusicClient:
        """Create a YTMusicClient instance with mocked dependencies."""
        with patch("ytmpd.ytmusic.YTMusic", return_value=mock_ytmusic):
            client = YTMusicClient(auth_file=mock_oauth_file)
        return client

    def test_init_creates_client_with_valid_oauth_file(
        self, mock_oauth_file: Path, mock_ytmusic: Mock
    ) -> None:
        """Test that client initializes successfully with valid OAuth file."""
        with patch("ytmpd.ytmusic.YTMusic", return_value=mock_ytmusic) as mock_ytmusic_cls:
            client = YTMusicClient(auth_file=mock_oauth_file)

            assert client._client is not None
            mock_ytmusic_cls.assert_called_once_with(str(mock_oauth_file))

    def test_init_raises_error_if_oauth_file_missing(self, tmp_path: Path) -> None:
        """Test that client raises error if OAuth file doesn't exist."""
        nonexistent_file = tmp_path / "nonexistent.json"

        with pytest.raises(YTMusicAuthError) as exc_info:
            YTMusicClient(auth_file=nonexistent_file)

        assert "not found" in str(exc_info.value)

    def test_init_uses_default_oauth_path_if_none_provided(self, mock_ytmusic: Mock) -> None:
        """Test that client uses default browser auth path when none is provided."""
        with patch("ytmpd.ytmusic.get_config_dir") as mock_get_config_dir:
            mock_config_dir = Path("/mock/config/dir")
            mock_get_config_dir.return_value = mock_config_dir

            # Create the browser.json file in the mock location
            with patch("pathlib.Path.exists", return_value=True):
                with patch("ytmpd.ytmusic.YTMusic", return_value=mock_ytmusic):
                    client = YTMusicClient()

                    expected_path = mock_config_dir / "browser.json"
                    assert client.auth_file == expected_path

    def test_search_returns_formatted_results(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that search returns properly formatted results."""
        # Mock search results from ytmusicapi
        mock_ytmusic.search.return_value = [
            {
                "videoId": "abc123",
                "title": "Test Song",
                "artists": [{"name": "Test Artist"}],
                "duration": "3:45",
            },
            {
                "videoId": "def456",
                "title": "Another Song",
                "artists": [{"name": "Another Artist"}],
                "duration": "4:20",
            },
        ]

        client._client = mock_ytmusic
        results = client.search("test query", limit=10)

        # Verify search was called correctly
        mock_ytmusic.search.assert_called_once_with("test query", filter="songs", limit=10)

        # Verify results are formatted correctly
        assert len(results) == 2
        assert results[0] == {
            "video_id": "abc123",
            "title": "Test Song",
            "artist": "Test Artist",
            "duration": 225,  # 3:45 = 225 seconds
        }
        assert results[1] == {
            "video_id": "def456",
            "title": "Another Song",
            "artist": "Another Artist",
            "duration": 260,  # 4:20 = 260 seconds
        }

    def test_search_raises_not_found_for_empty_results(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that search raises YTMusicNotFoundError for empty results."""
        mock_ytmusic.search.return_value = []
        client._client = mock_ytmusic

        with pytest.raises(YTMusicNotFoundError) as exc_info:
            client.search("nonexistent query")

        assert "No results found" in str(exc_info.value)

    def test_search_handles_missing_artist(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that search handles results with missing artist info."""
        mock_ytmusic.search.return_value = [
            {
                "videoId": "abc123",
                "title": "Test Song",
                "artists": [],  # Empty artists list
                "duration": "3:45",
            }
        ]

        client._client = mock_ytmusic
        results = client.search("test query")

        assert results[0]["artist"] == "Unknown Artist"

    def test_search_retries_on_transient_failure(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that search retries on transient API failures."""
        # First call fails, second call succeeds
        mock_ytmusic.search.side_effect = [
            Exception("Temporary error"),
            [
                {
                    "videoId": "abc123",
                    "title": "Test Song",
                    "artists": [{"name": "Test Artist"}],
                    "duration": "3:45",
                }
            ],
        ]

        client._client = mock_ytmusic

        # Mock time.sleep to speed up test
        with patch("time.sleep"):
            results = client.search("test query")

        assert len(results) == 1
        assert mock_ytmusic.search.call_count == 2

    def test_search_raises_api_error_after_max_retries(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that search raises APIError after exhausting retries."""
        mock_ytmusic.search.side_effect = Exception("Persistent error")
        client._client = mock_ytmusic

        with patch("time.sleep"):
            with pytest.raises(YTMusicAPIError) as exc_info:
                client.search("test query")

        assert "API call failed" in str(exc_info.value)
        assert mock_ytmusic.search.call_count == 3  # Default max_retries

    def test_get_song_info_returns_formatted_info(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that get_song_info returns properly formatted song information."""
        mock_ytmusic.get_song.return_value = {
            "videoDetails": {
                "videoId": "abc123",
                "title": "Test Song",
                "author": "Test Artist",
                "lengthSeconds": "225",
                "thumbnail": {
                    "thumbnails": [
                        {"url": "https://example.com/thumb1.jpg"},
                        {"url": "https://example.com/thumb2.jpg"},
                    ]
                },
            }
        }

        client._client = mock_ytmusic
        song_info = client.get_song_info("abc123")

        mock_ytmusic.get_song.assert_called_once_with("abc123")

        assert song_info == {
            "video_id": "abc123",
            "title": "Test Song",
            "artist": "Test Artist",
            "album": "",
            "duration": 225,
            "thumbnail_url": "https://example.com/thumb2.jpg",
        }

    def test_get_song_info_raises_not_found_for_invalid_video_id(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that get_song_info raises NotFoundError for invalid video ID."""
        mock_ytmusic.get_song.return_value = None
        client._client = mock_ytmusic

        with pytest.raises(YTMusicNotFoundError) as exc_info:
            client.get_song_info("invalid_id")

        assert "not found" in str(exc_info.value)

    def test_get_song_info_handles_missing_thumbnail(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that get_song_info handles missing thumbnail gracefully."""
        mock_ytmusic.get_song.return_value = {
            "videoDetails": {
                "videoId": "abc123",
                "title": "Test Song",
                "author": "Test Artist",
                "lengthSeconds": "225",
                "thumbnail": {"thumbnails": []},  # Empty thumbnails
            }
        }

        client._client = mock_ytmusic
        song_info = client.get_song_info("abc123")

        assert song_info["thumbnail_url"] == ""

    def test_parse_duration_handles_minutes_seconds(self) -> None:
        """Test duration parsing for M:SS format."""
        assert YTMusicClient._parse_duration("3:45") == 225
        assert YTMusicClient._parse_duration("0:30") == 30
        assert YTMusicClient._parse_duration("10:00") == 600

    def test_parse_duration_handles_hours_minutes_seconds(self) -> None:
        """Test duration parsing for H:MM:SS format."""
        assert YTMusicClient._parse_duration("1:23:45") == 5025
        assert YTMusicClient._parse_duration("2:00:00") == 7200

    def test_parse_duration_handles_invalid_format(self) -> None:
        """Test that invalid duration formats return 0."""
        assert YTMusicClient._parse_duration("invalid") == 0
        assert YTMusicClient._parse_duration("") == 0
        assert YTMusicClient._parse_duration("1:2:3:4") == 0

    def test_rate_limiting_enforced_between_requests(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that rate limiting is enforced between API requests."""
        mock_ytmusic.search.return_value = [
            {
                "videoId": "abc123",
                "title": "Test Song",
                "artists": [{"name": "Test Artist"}],
                "duration": "3:45",
            }
        ]

        client._client = mock_ytmusic
        client._min_request_interval = 0.05  # 50ms for faster testing

        start_time = time.time()
        client.search("query1")
        client.search("query2")
        elapsed = time.time() - start_time

        # Should take at least 50ms due to rate limiting
        assert elapsed >= 0.05

    def test_setup_browser_creates_credentials_file(self, tmp_path: Path) -> None:
        """Test that setup_browser calls ytmusicapi's setup function."""
        browser_file = tmp_path / "browser.json"
        mock_headers = "mock-header: value\nother-header: value2"

        with patch("ytmpd.ytmusic.get_config_dir", return_value=tmp_path):
            # Mock the input() function to simulate user input
            with patch("builtins.input", side_effect=["mock-header: value", "other-header: value2", EOFError()]):
                # Mock ytmusicapi.setup to avoid actual API call
                with patch("ytmusicapi.setup") as mock_setup:
                    mock_setup.return_value = None

                    YTMusicClient.setup_browser()

                    # Verify setup was called with correct path
                    assert mock_setup.call_count == 1
                    call_kwargs = mock_setup.call_args[1]
                    assert call_kwargs["filepath"] == str(browser_file)
                    assert "headers_raw" in call_kwargs

    def test_auth_errors_not_retried(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that authentication errors are raised early and not retried."""
        mock_ytmusic.search.side_effect = Exception("Authentication failed")
        client._client = mock_ytmusic

        # Auth errors are detected and raised as YTMusicAuthError which is then
        # wrapped in YTMusicAPIError by the search method's exception handler
        with pytest.raises((YTMusicAuthError, YTMusicAPIError)) as exc_info:
            client.search("test query")

        # Verify it's an authentication-related error
        assert "auth" in str(exc_info.value).lower()

        # Should only be called once (no retries for auth errors)
        assert mock_ytmusic.search.call_count == 1


class TestParseDuration:
    """Tests for _parse_duration static method."""

    def test_parses_standard_formats(self) -> None:
        """Test parsing of standard duration formats."""
        assert YTMusicClient._parse_duration("0:30") == 30
        assert YTMusicClient._parse_duration("1:00") == 60
        assert YTMusicClient._parse_duration("3:45") == 225
        assert YTMusicClient._parse_duration("10:30") == 630
        assert YTMusicClient._parse_duration("1:23:45") == 5025

    def test_handles_edge_cases(self) -> None:
        """Test parsing of edge cases."""
        assert YTMusicClient._parse_duration("0:00") == 0
        assert YTMusicClient._parse_duration("0:01") == 1
        assert YTMusicClient._parse_duration("") == 0
        assert YTMusicClient._parse_duration("invalid") == 0
        assert YTMusicClient._parse_duration("1:2:3:4") == 0


class TestPlaylistFetching:
    """Tests for playlist fetching functionality."""

    @pytest.fixture
    def mock_oauth_file(self, tmp_path: Path) -> Path:
        """Create a mock OAuth credentials file."""
        oauth_file = tmp_path / "oauth.json"
        oauth_file.write_text(
            json.dumps(
                {
                    "access_token": "mock_token",
                    "refresh_token": "mock_refresh",
                    "token_type": "Bearer",
                }
            )
        )
        return oauth_file

    @pytest.fixture
    def mock_ytmusic(self) -> Mock:
        """Create a mock YTMusic instance."""
        return Mock()

    @pytest.fixture
    def client(self, mock_oauth_file: Path, mock_ytmusic: Mock) -> YTMusicClient:
        """Create a YTMusicClient instance with mocked dependencies."""
        with patch("ytmpd.ytmusic.YTMusic", return_value=mock_ytmusic):
            client = YTMusicClient(auth_file=mock_oauth_file)
        return client

    def test_get_user_playlists_success(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test successful fetching of user playlists."""
        mock_ytmusic.get_library_playlists.return_value = [
            {"playlistId": "PL123", "title": "Favorites", "count": 50},
            {"playlistId": "PL456", "title": "Workout", "count": 30},
        ]

        client._client = mock_ytmusic
        playlists = client.get_user_playlists()

        mock_ytmusic.get_library_playlists.assert_called_once_with(limit=None)

        assert len(playlists) == 2
        assert playlists[0] == Playlist(id="PL123", name="Favorites", track_count=50)
        assert playlists[1] == Playlist(id="PL456", name="Workout", track_count=30)

    def test_get_user_playlists_handles_empty_list(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test handling of empty playlist list."""
        mock_ytmusic.get_library_playlists.return_value = []

        client._client = mock_ytmusic
        playlists = client.get_user_playlists()

        assert playlists == []

    def test_get_user_playlists_filters_empty_playlists(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that playlists with 0 tracks are filtered out."""
        mock_ytmusic.get_library_playlists.return_value = [
            {"playlistId": "PL123", "title": "Favorites", "count": 50},
            {"playlistId": "PL456", "title": "Empty Playlist", "count": 0},
            {"playlistId": "PL789", "title": "Workout", "count": 30},
        ]

        client._client = mock_ytmusic
        playlists = client.get_user_playlists()

        assert len(playlists) == 2
        assert playlists[0].name == "Favorites"
        assert playlists[1].name == "Workout"

    def test_get_user_playlists_skips_playlists_without_id(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that playlists without ID are skipped."""
        mock_ytmusic.get_library_playlists.return_value = [
            {"playlistId": "PL123", "title": "Favorites", "count": 50},
            {"title": "No ID Playlist", "count": 20},  # Missing playlistId
        ]

        client._client = mock_ytmusic
        playlists = client.get_user_playlists()

        assert len(playlists) == 1
        assert playlists[0].id == "PL123"

    def test_get_user_playlists_handles_malformed_entries(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that malformed playlist entries are skipped."""
        mock_ytmusic.get_library_playlists.return_value = [
            {"playlistId": "PL123", "title": "Favorites", "count": 50},
            {"playlistId": "PL456"},  # Missing title and count
            {"playlistId": "PL789", "title": "Workout", "count": 30},
        ]

        client._client = mock_ytmusic
        playlists = client.get_user_playlists()

        # Should skip the malformed entry but continue processing
        assert len(playlists) == 2

    def test_get_user_playlists_retries_on_network_error(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that playlist fetching retries on network errors."""
        mock_ytmusic.get_library_playlists.side_effect = [
            Exception("Network error"),
            [{"playlistId": "PL123", "title": "Favorites", "count": 50}],
        ]

        client._client = mock_ytmusic

        with patch("time.sleep"):
            playlists = client.get_user_playlists()

        assert len(playlists) == 1
        assert mock_ytmusic.get_library_playlists.call_count == 2

    def test_get_user_playlists_raises_api_error_after_max_retries(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that playlist fetching raises error after max retries."""
        mock_ytmusic.get_library_playlists.side_effect = Exception("Persistent error")
        client._client = mock_ytmusic

        with patch("time.sleep"):
            with pytest.raises(YTMusicAPIError):
                client.get_user_playlists()

        assert mock_ytmusic.get_library_playlists.call_count == 3

    def test_get_playlist_tracks_success(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test successful fetching of playlist tracks."""
        mock_ytmusic.get_playlist.return_value = {
            "tracks": [
                {
                    "videoId": "abc123",
                    "title": "Song 1",
                    "artists": [{"name": "Artist 1"}],
                },
                {
                    "videoId": "def456",
                    "title": "Song 2",
                    "artists": [{"name": "Artist 2"}],
                },
            ]
        }

        client._client = mock_ytmusic
        tracks = client.get_playlist_tracks("PL123")

        mock_ytmusic.get_playlist.assert_called_once_with("PL123", limit=None)

        assert len(tracks) == 2
        assert tracks[0] == Track(video_id="abc123", title="Song 1", artist="Artist 1")
        assert tracks[1] == Track(video_id="def456", title="Song 2", artist="Artist 2")

    def test_get_playlist_tracks_handles_empty_playlist(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test handling of empty playlist."""
        mock_ytmusic.get_playlist.return_value = {"tracks": []}

        client._client = mock_ytmusic
        tracks = client.get_playlist_tracks("PL123")

        assert tracks == []

    def test_get_playlist_tracks_filters_tracks_without_video_id(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that tracks without video_id are filtered out."""
        mock_ytmusic.get_playlist.return_value = {
            "tracks": [
                {
                    "videoId": "abc123",
                    "title": "Song 1",
                    "artists": [{"name": "Artist 1"}],
                },
                {
                    "title": "Podcast Episode",
                    "artists": [{"name": "Podcaster"}],
                },  # No videoId
                {
                    "videoId": "def456",
                    "title": "Song 2",
                    "artists": [{"name": "Artist 2"}],
                },
            ]
        }

        client._client = mock_ytmusic
        tracks = client.get_playlist_tracks("PL123")

        assert len(tracks) == 2
        assert tracks[0].video_id == "abc123"
        assert tracks[1].video_id == "def456"

    def test_get_playlist_tracks_handles_missing_artist(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test handling of tracks with missing artist info."""
        mock_ytmusic.get_playlist.return_value = {
            "tracks": [
                {
                    "videoId": "abc123",
                    "title": "Song 1",
                    "artists": [],  # Empty artists list
                }
            ]
        }

        client._client = mock_ytmusic
        tracks = client.get_playlist_tracks("PL123")

        assert len(tracks) == 1
        assert tracks[0].artist == "Unknown Artist"

    def test_get_playlist_tracks_handles_malformed_entries(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that malformed track entries use defaults."""
        mock_ytmusic.get_playlist.return_value = {
            "tracks": [
                {
                    "videoId": "abc123",
                    "title": "Song 1",
                    "artists": [{"name": "Artist 1"}],
                },
                {
                    "videoId": "def456"
                },  # Missing title and artists
                {
                    "videoId": "ghi789",
                    "title": "Song 2",
                    "artists": [{"name": "Artist 2"}],
                },
            ]
        }

        client._client = mock_ytmusic
        tracks = client.get_playlist_tracks("PL123")

        # Should include all tracks with defaults for missing fields
        assert len(tracks) == 3
        assert tracks[1].title == "Unknown Title"
        assert tracks[1].artist == "Unknown Artist"

    def test_get_playlist_tracks_raises_not_found_for_invalid_id(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that invalid playlist ID raises NotFoundError."""
        mock_ytmusic.get_playlist.return_value = None

        client._client = mock_ytmusic

        with pytest.raises(YTMusicNotFoundError):
            client.get_playlist_tracks("INVALID_ID")

    def test_get_playlist_tracks_retries_on_network_error(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that track fetching retries on network errors."""
        mock_ytmusic.get_playlist.side_effect = [
            Exception("Network error"),
            {
                "tracks": [
                    {
                        "videoId": "abc123",
                        "title": "Song 1",
                        "artists": [{"name": "Artist 1"}],
                    }
                ]
            },
        ]

        client._client = mock_ytmusic

        with patch("time.sleep"):
            tracks = client.get_playlist_tracks("PL123")

        assert len(tracks) == 1
        assert mock_ytmusic.get_playlist.call_count == 2

    def test_get_playlist_tracks_raises_api_error_after_max_retries(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that track fetching raises error after max retries."""
        mock_ytmusic.get_playlist.side_effect = Exception("Persistent error")
        client._client = mock_ytmusic

        with patch("time.sleep"):
            with pytest.raises(YTMusicAPIError):
                client.get_playlist_tracks("PL123")

        assert mock_ytmusic.get_playlist.call_count == 3
