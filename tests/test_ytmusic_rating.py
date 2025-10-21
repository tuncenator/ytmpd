"""Unit tests for YTMusicClient rating methods."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ytmpd.exceptions import YTMusicAPIError, YTMusicAuthError, YTMusicNotFoundError
from ytmpd.rating import RatingState
from ytmpd.ytmusic import YTMusicClient


class TestYTMusicClientRating:
    """Tests for YTMusicClient rating methods."""

    @pytest.fixture
    def mock_oauth_file(self, tmp_path: Path) -> Path:
        """Create a mock OAuth credentials file."""
        oauth_file = tmp_path / "browser.json"
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

    # Tests for get_track_rating()

    def test_get_track_rating_liked(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        """Test getting rating for a liked track."""
        # Mock API response with LIKE status
        mock_ytmusic.get_watch_playlist.return_value = {
            "tracks": [
                {
                    "videoId": "test123",
                    "title": "Test Song",
                    "likeStatus": "LIKE",
                }
            ]
        }

        client._client = mock_ytmusic
        rating = client.get_track_rating("test123")

        # Verify API call
        mock_ytmusic.get_watch_playlist.assert_called_once_with(videoId="test123", limit=1)

        # Verify rating state
        assert rating == RatingState.LIKED

    def test_get_track_rating_neutral(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        """Test getting rating for a neutral/unrated track."""
        # Mock API response with INDIFFERENT status
        mock_ytmusic.get_watch_playlist.return_value = {
            "tracks": [
                {
                    "videoId": "test456",
                    "title": "Neutral Song",
                    "likeStatus": "INDIFFERENT",
                }
            ]
        }

        client._client = mock_ytmusic
        rating = client.get_track_rating("test456")

        # Verify rating state (INDIFFERENT maps to NEUTRAL)
        assert rating == RatingState.NEUTRAL

    def test_get_track_rating_disliked(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        """Test getting rating for a disliked track.

        Note: Due to API limitation, DISLIKE appears as INDIFFERENT,
        so this test verifies that behavior.
        """
        # Mock API response - DISLIKE appears as INDIFFERENT
        mock_ytmusic.get_watch_playlist.return_value = {
            "tracks": [
                {
                    "videoId": "test789",
                    "title": "Disliked Song",
                    "likeStatus": "INDIFFERENT",  # API limitation
                }
            ]
        }

        client._client = mock_ytmusic
        rating = client.get_track_rating("test789")

        # Verify rating state (INDIFFERENT due to API limitation)
        assert rating == RatingState.NEUTRAL

    def test_get_track_rating_not_found(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        """Test error handling when track is not found."""
        # Mock API response with empty tracks list
        mock_ytmusic.get_watch_playlist.return_value = {"tracks": []}

        client._client = mock_ytmusic

        with pytest.raises(YTMusicNotFoundError) as exc_info:
            client.get_track_rating("nonexistent")

        assert "not found" in str(exc_info.value).lower()

    def test_get_track_rating_missing_like_status(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test error handling when likeStatus field is missing."""
        # Mock API response without likeStatus field
        mock_ytmusic.get_watch_playlist.return_value = {
            "tracks": [
                {
                    "videoId": "test999",
                    "title": "No Rating Field",
                    # Missing likeStatus
                }
            ]
        }

        client._client = mock_ytmusic

        with pytest.raises(YTMusicAPIError) as exc_info:
            client.get_track_rating("test999")

        assert "likeStatus" in str(exc_info.value)

    def test_get_track_rating_api_error(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        """Test error handling when API call fails."""
        # Mock API to raise an exception
        mock_ytmusic.get_watch_playlist.side_effect = Exception("API error")

        client._client = mock_ytmusic

        with pytest.raises(YTMusicAPIError) as exc_info:
            client.get_track_rating("test_error")

        assert "Failed to get track rating" in str(exc_info.value)

    def test_get_track_rating_not_authenticated(self, mock_oauth_file: Path) -> None:
        """Test error handling when client is not authenticated."""
        with patch("ytmpd.ytmusic.YTMusic", return_value=Mock()):
            client = YTMusicClient(auth_file=mock_oauth_file)
            client._client = None  # Simulate no authentication

        with pytest.raises(YTMusicAuthError) as exc_info:
            client.get_track_rating("test123")

        assert "not initialized" in str(exc_info.value).lower()

    def test_get_track_rating_retry_on_failure(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that get_track_rating retries on transient failures."""
        # First call fails, second succeeds
        mock_ytmusic.get_watch_playlist.side_effect = [
            Exception("Transient error"),
            {
                "tracks": [
                    {
                        "videoId": "test_retry",
                        "title": "Retry Song",
                        "likeStatus": "LIKE",
                    }
                ]
            },
        ]

        client._client = mock_ytmusic
        rating = client.get_track_rating("test_retry")

        # Verify it retried and succeeded
        assert rating == RatingState.LIKED
        assert mock_ytmusic.get_watch_playlist.call_count == 2

    # Tests for set_track_rating()

    def test_set_track_rating_like(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        """Test setting track rating to LIKE."""
        mock_ytmusic.rate_song.return_value = {"status": "success"}

        client._client = mock_ytmusic
        client.set_track_rating("test123", RatingState.LIKED)

        # Verify API call - need to check the actual call
        assert mock_ytmusic.rate_song.called
        call_kwargs = mock_ytmusic.rate_song.call_args[1]
        assert call_kwargs["videoId"] == "test123"

        # Verify the rating enum was converted to LikeStatus.LIKE
        from ytmusicapi.models.content.enums import LikeStatus

        assert call_kwargs["rating"] == LikeStatus.LIKE

    def test_set_track_rating_dislike(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        """Test setting track rating to DISLIKE."""
        mock_ytmusic.rate_song.return_value = {"status": "success"}

        client._client = mock_ytmusic
        client.set_track_rating("test456", RatingState.DISLIKED)

        # Verify API call
        from ytmusicapi.models.content.enums import LikeStatus

        call_kwargs = mock_ytmusic.rate_song.call_args[1]
        assert call_kwargs["videoId"] == "test456"
        assert call_kwargs["rating"] == LikeStatus.DISLIKE

    def test_set_track_rating_neutral(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        """Test setting track rating to NEUTRAL (INDIFFERENT)."""
        mock_ytmusic.rate_song.return_value = {"status": "success"}

        client._client = mock_ytmusic
        client.set_track_rating("test789", RatingState.NEUTRAL)

        # Verify API call
        from ytmusicapi.models.content.enums import LikeStatus

        call_kwargs = mock_ytmusic.rate_song.call_args[1]
        assert call_kwargs["videoId"] == "test789"
        assert call_kwargs["rating"] == LikeStatus.INDIFFERENT

    def test_set_track_rating_api_error(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        """Test error handling when API fails to set rating."""
        # Mock API to raise an exception
        mock_ytmusic.rate_song.side_effect = Exception("API error")

        client._client = mock_ytmusic

        with pytest.raises(YTMusicAPIError) as exc_info:
            client.set_track_rating("test_error", RatingState.LIKED)

        assert "Failed to set track rating" in str(exc_info.value)

    def test_set_track_rating_not_authenticated(self, mock_oauth_file: Path) -> None:
        """Test error handling when client is not authenticated."""
        with patch("ytmpd.ytmusic.YTMusic", return_value=Mock()):
            client = YTMusicClient(auth_file=mock_oauth_file)
            client._client = None  # Simulate no authentication

        with pytest.raises(YTMusicAuthError) as exc_info:
            client.set_track_rating("test123", RatingState.LIKED)

        assert "not initialized" in str(exc_info.value).lower()

    def test_set_track_rating_retry_on_failure(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test that set_track_rating retries on transient failures."""
        # First call fails, second succeeds
        mock_ytmusic.rate_song.side_effect = [
            Exception("Transient error"),
            {"status": "success"},
        ]

        client._client = mock_ytmusic
        # Should not raise - retry succeeds
        client.set_track_rating("test_retry", RatingState.LIKED)

        # Verify it retried
        assert mock_ytmusic.rate_song.call_count == 2

    # Integration tests

    def test_get_and_set_rating_integration(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        """Test integration of get and set rating methods."""
        # Setup: Track is initially neutral
        mock_ytmusic.get_watch_playlist.return_value = {
            "tracks": [
                {
                    "videoId": "integration_test",
                    "title": "Integration Test Song",
                    "likeStatus": "INDIFFERENT",
                }
            ]
        }
        mock_ytmusic.rate_song.return_value = {"status": "success"}

        client._client = mock_ytmusic

        # Get initial rating
        initial_rating = client.get_track_rating("integration_test")
        assert initial_rating == RatingState.NEUTRAL

        # Set rating to LIKED
        client.set_track_rating("integration_test", RatingState.LIKED)

        # Verify rate_song was called
        assert mock_ytmusic.rate_song.called

        # Simulate API now returning LIKE
        mock_ytmusic.get_watch_playlist.return_value = {
            "tracks": [
                {
                    "videoId": "integration_test",
                    "title": "Integration Test Song",
                    "likeStatus": "LIKE",
                }
            ]
        }

        # Get updated rating
        updated_rating = client.get_track_rating("integration_test")
        assert updated_rating == RatingState.LIKED

    def test_rate_limiting_applied(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        """Test that rate limiting is applied to rating methods."""
        import time

        mock_ytmusic.get_watch_playlist.return_value = {
            "tracks": [{"videoId": "rate_limit_test", "likeStatus": "LIKE"}]
        }

        client._client = mock_ytmusic

        # Make two consecutive calls
        start_time = time.time()
        client.get_track_rating("rate_limit_test")
        client.get_track_rating("rate_limit_test")
        elapsed = time.time() - start_time

        # Should have rate limiting (100ms minimum between requests)
        # With two calls, there should be at least one 100ms delay
        assert elapsed >= 0.1

    def test_invalid_rating_state_enum(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        """Test handling of invalid RatingState values."""
        client._client = mock_ytmusic

        # This would only happen with enum misuse, but good to verify the mapping works
        # All valid RatingState values should map correctly
        valid_states = [RatingState.NEUTRAL, RatingState.LIKED, RatingState.DISLIKED]

        mock_ytmusic.rate_song.return_value = {"status": "success"}

        for state in valid_states:
            client.set_track_rating("test_enum", state)
            # Should not raise - all valid states have mappings
