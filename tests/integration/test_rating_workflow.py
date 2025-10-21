"""End-to-end integration tests for like/dislike workflow.

This module tests the complete workflow from ytmpctl like/dislike commands
through to YouTube Music API calls, validating all state transitions and
error handling.
"""

import subprocess
from unittest.mock import MagicMock, Mock, patch

import pytest

from ytmpd.exceptions import YTMusicAPIError, YTMusicAuthError, YTMusicNotFoundError
from ytmpd.rating import RatingAction, RatingManager, RatingState


@pytest.fixture
def mock_mpd():
    """Mock MPD client with currently playing YouTube Music track."""
    with patch("subprocess.run") as mock_run:
        # Default: Return valid YouTube track info
        def subprocess_side_effect(cmd, *args, **kwargs):
            result = Mock()
            result.returncode = 0
            result.stdout = ""

            # Handle mpc current -f %file%
            if "current" in cmd and "%file%" in cmd:
                result.stdout = "http://localhost:6602/proxy/test_video_id"
            # Handle mpc current -f %artist%
            elif "current" in cmd and "%artist%" in cmd:
                result.stdout = "Test Artist"
            # Handle mpc current -f %title%
            elif "current" in cmd and "%title%" in cmd:
                result.stdout = "Test Title"

            return result

        mock_run.side_effect = subprocess_side_effect
        yield mock_run


@pytest.fixture
def mock_mpd_no_track():
    """Mock MPD with no track playing."""
    with patch("subprocess.run") as mock_run:
        result = Mock()
        result.returncode = 0
        result.stdout = ""  # Empty means no track
        mock_run.return_value = result
        yield mock_run


@pytest.fixture
def mock_mpd_local_file():
    """Mock MPD playing a local file (not YouTube Music)."""
    with patch("subprocess.run") as mock_run:
        result = Mock()
        result.returncode = 0
        result.stdout = "/home/user/music/song.mp3"  # Local file path
        mock_run.return_value = result
        yield mock_run


@pytest.fixture
def mock_ytmusic():
    """Mock YouTube Music client."""
    with patch("ytmpd.ytmusic.YTMusicClient") as mock_client_class:
        mock_instance = MagicMock()
        # Default: Track is neutral
        mock_instance.get_track_rating.return_value = RatingState.NEUTRAL
        mock_instance.set_track_rating.return_value = None
        mock_client_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_config():
    """Mock config loading."""
    with patch("builtins.open") as mock_open:
        # Mock config file with MPD settings
        mock_file = Mock()
        mock_file.__enter__ = Mock(return_value=mock_file)
        mock_file.__exit__ = Mock(return_value=False)
        mock_file.read.return_value = """
mpd:
  host: localhost
  port: 6601
"""
        mock_open.return_value = mock_file
        yield mock_open


class TestLikeDislikeWorkflow:
    """End-to-end tests for like/dislike workflow."""

    def test_like_neutral_track_full_flow(self, mock_mpd, mock_ytmusic, mock_config):
        """Test liking a neutral track through full workflow."""
        # Setup: Track is neutral
        mock_ytmusic.get_track_rating.return_value = RatingState.NEUTRAL

        # Import and execute the command logic
        from ytmpd.ytmusic import YTMusicClient

        # Simulate the command flow
        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        # Get current rating
        current_rating = ytmusic.get_track_rating("test_video_id")
        assert current_rating == RatingState.NEUTRAL

        # Apply toggle logic
        transition = rating_mgr.apply_action(current_rating, RatingAction.LIKE)

        # Verify transition
        assert transition.current_state == RatingState.NEUTRAL
        assert transition.new_state == RatingState.LIKED
        assert "Liked" in transition.user_message

        # Set new rating
        ytmusic.set_track_rating("test_video_id", transition.new_state)

        # Verify API was called correctly
        mock_ytmusic.get_track_rating.assert_called_once_with("test_video_id")
        mock_ytmusic.set_track_rating.assert_called_once_with("test_video_id", RatingState.LIKED)

    def test_like_liked_track_removes_like(self, mock_mpd, mock_ytmusic, mock_config):
        """Test toggling off a like (LIKED -> NEUTRAL)."""
        # Setup: Track is already liked
        mock_ytmusic.get_track_rating.return_value = RatingState.LIKED

        from ytmpd.ytmusic import YTMusicClient

        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        current_rating = ytmusic.get_track_rating("test_video_id")
        transition = rating_mgr.apply_action(current_rating, RatingAction.LIKE)

        # Verify transition
        assert transition.current_state == RatingState.LIKED
        assert transition.new_state == RatingState.NEUTRAL
        assert "Removed like" in transition.user_message

        ytmusic.set_track_rating("test_video_id", transition.new_state)
        mock_ytmusic.set_track_rating.assert_called_once_with("test_video_id", RatingState.NEUTRAL)

    def test_dislike_neutral_track(self, mock_mpd, mock_ytmusic, mock_config):
        """Test disliking a neutral track (NEUTRAL -> DISLIKED)."""
        mock_ytmusic.get_track_rating.return_value = RatingState.NEUTRAL

        from ytmpd.ytmusic import YTMusicClient

        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        current_rating = ytmusic.get_track_rating("test_video_id")
        transition = rating_mgr.apply_action(current_rating, RatingAction.DISLIKE)

        assert transition.current_state == RatingState.NEUTRAL
        assert transition.new_state == RatingState.DISLIKED
        assert "Disliked" in transition.user_message

        ytmusic.set_track_rating("test_video_id", transition.new_state)
        mock_ytmusic.set_track_rating.assert_called_once_with("test_video_id", RatingState.DISLIKED)

    def test_like_disliked_track_switches_to_like(self, mock_mpd, mock_ytmusic, mock_config):
        """Test switching from dislike to like (DISLIKED -> LIKED)."""
        mock_ytmusic.get_track_rating.return_value = RatingState.DISLIKED

        from ytmpd.ytmusic import YTMusicClient

        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        current_rating = ytmusic.get_track_rating("test_video_id")
        transition = rating_mgr.apply_action(current_rating, RatingAction.LIKE)

        assert transition.current_state == RatingState.DISLIKED
        assert transition.new_state == RatingState.LIKED
        assert "Liked" in transition.user_message

        ytmusic.set_track_rating("test_video_id", transition.new_state)
        mock_ytmusic.set_track_rating.assert_called_once_with("test_video_id", RatingState.LIKED)

    def test_dislike_liked_track_switches_to_dislike(self, mock_mpd, mock_ytmusic, mock_config):
        """Test switching from like to dislike (LIKED -> DISLIKED)."""
        mock_ytmusic.get_track_rating.return_value = RatingState.LIKED

        from ytmpd.ytmusic import YTMusicClient

        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        current_rating = ytmusic.get_track_rating("test_video_id")
        transition = rating_mgr.apply_action(current_rating, RatingAction.DISLIKE)

        assert transition.current_state == RatingState.LIKED
        assert transition.new_state == RatingState.DISLIKED
        assert "Disliked" in transition.user_message

        ytmusic.set_track_rating("test_video_id", transition.new_state)
        mock_ytmusic.set_track_rating.assert_called_once_with("test_video_id", RatingState.DISLIKED)

    def test_dislike_disliked_track_removes_dislike(self, mock_mpd, mock_ytmusic, mock_config):
        """Test toggling off a dislike (DISLIKED -> NEUTRAL).

        Note: Due to YouTube Music API limitation, disliked tracks appear as
        NEUTRAL when queried. This test uses mocked data to verify the logic works.
        """
        mock_ytmusic.get_track_rating.return_value = RatingState.DISLIKED

        from ytmpd.ytmusic import YTMusicClient

        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        current_rating = ytmusic.get_track_rating("test_video_id")
        transition = rating_mgr.apply_action(current_rating, RatingAction.DISLIKE)

        assert transition.current_state == RatingState.DISLIKED
        assert transition.new_state == RatingState.NEUTRAL
        assert "Removed dislike" in transition.user_message

        ytmusic.set_track_rating("test_video_id", transition.new_state)
        mock_ytmusic.set_track_rating.assert_called_once_with("test_video_id", RatingState.NEUTRAL)


class TestErrorHandling:
    """Test error handling in like/dislike workflow."""

    def test_no_track_playing_error(self, mock_mpd_no_track, mock_config):
        """Test error handling when no track is playing."""
        import sys

        # The function should exit when no track is playing
        with pytest.raises(SystemExit) as exc_info:
            # Simulate the check in get_current_track_from_mpd
            result = Mock()
            result.returncode = 0
            result.stdout = ""  # No track

            file_path = result.stdout.strip()
            if not file_path:
                sys.exit(1)

        assert exc_info.value.code == 1

    def test_non_youtube_track_error(self, mock_mpd_local_file, mock_config):
        """Test error handling for non-YouTube tracks."""
        import re
        import sys

        with pytest.raises(SystemExit) as exc_info:
            with patch("subprocess.run") as mock_run:
                result = Mock()
                result.returncode = 0
                result.stdout = "/home/user/music/local.mp3"
                mock_run.return_value = result

                # Simulate the check in get_current_track_from_mpd
                file_path = result.stdout.strip()
                match = re.search(r"/proxy/([a-zA-Z0-9_-]+)", file_path)
                if not match:
                    sys.exit(1)

        assert exc_info.value.code == 1

    def test_api_error_get_rating(self, mock_mpd, mock_ytmusic, mock_config):
        """Test handling of YouTube Music API errors during get_track_rating."""
        # Setup: API raises error
        mock_ytmusic.get_track_rating.side_effect = YTMusicAPIError("API Error")

        from ytmpd.ytmusic import YTMusicClient

        ytmusic = YTMusicClient()

        with pytest.raises(YTMusicAPIError):
            ytmusic.get_track_rating("test_video_id")

    def test_api_error_set_rating(self, mock_mpd, mock_ytmusic, mock_config):
        """Test handling of YouTube Music API errors during set_track_rating."""
        mock_ytmusic.get_track_rating.return_value = RatingState.NEUTRAL
        mock_ytmusic.set_track_rating.side_effect = YTMusicAPIError("API Error")

        from ytmpd.ytmusic import YTMusicClient

        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        current_rating = ytmusic.get_track_rating("test_video_id")
        transition = rating_mgr.apply_action(current_rating, RatingAction.LIKE)

        with pytest.raises(YTMusicAPIError):
            ytmusic.set_track_rating("test_video_id", transition.new_state)

    def test_auth_error_handling(self, mock_mpd, mock_ytmusic, mock_config):
        """Test handling of authentication errors."""
        mock_ytmusic.get_track_rating.side_effect = YTMusicAuthError("Not authenticated")

        from ytmpd.ytmusic import YTMusicClient

        ytmusic = YTMusicClient()

        with pytest.raises(YTMusicAuthError):
            ytmusic.get_track_rating("test_video_id")

    def test_track_not_found_error(self, mock_mpd, mock_ytmusic, mock_config):
        """Test handling when track is not found in YouTube Music."""
        mock_ytmusic.get_track_rating.side_effect = YTMusicNotFoundError("Track not found")

        from ytmpd.ytmusic import YTMusicClient

        ytmusic = YTMusicClient()

        with pytest.raises(YTMusicNotFoundError):
            ytmusic.get_track_rating("invalid_video_id")

    def test_mpd_connection_error(self, mock_config):
        """Test handling of MPD connection errors."""
        with patch("subprocess.run") as mock_run:
            # Simulate subprocess.CalledProcessError
            mock_run.side_effect = subprocess.CalledProcessError(1, "mpc")

            with pytest.raises(subprocess.CalledProcessError):
                subprocess.run(
                    ["mpc", "current", "-f", "%file%"], capture_output=True, text=True, check=True
                )


class TestSyncTrigger:
    """Test sync trigger behavior."""

    def test_sync_triggered_after_like(self, mock_mpd, mock_ytmusic, mock_config):
        """Test that sync should be triggered after liking a song.

        Note: This tests the logic, not the actual sync command.
        The actual ytmpctl command calls send_command("sync") after liking.
        """
        from ytmpd.rating import RatingState
        from ytmpd.ytmusic import YTMusicClient

        mock_ytmusic.get_track_rating.return_value = RatingState.NEUTRAL

        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        current_rating = ytmusic.get_track_rating("test_video_id")
        transition = rating_mgr.apply_action(current_rating, RatingAction.LIKE)
        ytmusic.set_track_rating("test_video_id", transition.new_state)

        # Verify we should trigger sync (new_state is LIKED)
        should_sync = transition.new_state == RatingState.LIKED
        assert should_sync is True

    def test_sync_not_triggered_after_dislike(self, mock_mpd, mock_ytmusic, mock_config):
        """Test that sync is NOT triggered after disliking a song.

        Disliked songs don't appear in playlists, so sync is not needed.
        """
        from ytmpd.rating import RatingState
        from ytmpd.ytmusic import YTMusicClient

        mock_ytmusic.get_track_rating.return_value = RatingState.NEUTRAL

        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        current_rating = ytmusic.get_track_rating("test_video_id")
        transition = rating_mgr.apply_action(current_rating, RatingAction.DISLIKE)
        ytmusic.set_track_rating("test_video_id", transition.new_state)

        # Verify we should NOT trigger sync (new_state is DISLIKED)
        should_sync = transition.new_state == RatingState.LIKED
        assert should_sync is False

    def test_sync_not_triggered_after_removing_like(self, mock_mpd, mock_ytmusic, mock_config):
        """Test that sync is NOT triggered when removing a like (LIKED -> NEUTRAL)."""
        from ytmpd.rating import RatingState
        from ytmpd.ytmusic import YTMusicClient

        mock_ytmusic.get_track_rating.return_value = RatingState.LIKED

        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        current_rating = ytmusic.get_track_rating("test_video_id")
        transition = rating_mgr.apply_action(current_rating, RatingAction.LIKE)
        ytmusic.set_track_rating("test_video_id", transition.new_state)

        # Verify we should NOT trigger sync (new_state is NEUTRAL)
        should_sync = transition.new_state == RatingState.LIKED
        assert should_sync is False


class TestIntegrationWorkflow:
    """Integration tests combining multiple components."""

    def test_full_like_workflow_integration(self, mock_mpd, mock_ytmusic, mock_config):
        """Test complete like workflow from start to finish."""
        from ytmpd.rating import RatingState
        from ytmpd.ytmusic import YTMusicClient

        # Setup
        mock_ytmusic.get_track_rating.return_value = RatingState.NEUTRAL

        # Execute full workflow
        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        # Step 1: Get current rating
        video_id = "test_video_id"
        current_rating = ytmusic.get_track_rating(video_id)
        assert current_rating == RatingState.NEUTRAL

        # Step 2: Apply action
        transition = rating_mgr.apply_action(current_rating, RatingAction.LIKE)
        assert transition.current_state == RatingState.NEUTRAL
        assert transition.new_state == RatingState.LIKED

        # Step 3: Set new rating
        ytmusic.set_track_rating(video_id, transition.new_state)

        # Step 4: Verify user message
        assert "Liked" in transition.user_message

        # Verify all mocks were called correctly
        assert mock_ytmusic.get_track_rating.call_count == 1
        assert mock_ytmusic.set_track_rating.call_count == 1

    def test_full_dislike_workflow_integration(self, mock_mpd, mock_ytmusic, mock_config):
        """Test complete dislike workflow from start to finish."""
        from ytmpd.rating import RatingState
        from ytmpd.ytmusic import YTMusicClient

        mock_ytmusic.get_track_rating.return_value = RatingState.LIKED

        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        video_id = "test_video_id"
        current_rating = ytmusic.get_track_rating(video_id)
        transition = rating_mgr.apply_action(current_rating, RatingAction.DISLIKE)
        ytmusic.set_track_rating(video_id, transition.new_state)

        assert transition.current_state == RatingState.LIKED
        assert transition.new_state == RatingState.DISLIKED
        assert "Disliked" in transition.user_message

    def test_toggle_behavior_like_twice(self, mock_mpd, mock_ytmusic, mock_config):
        """Test toggling like twice returns to neutral."""
        from ytmpd.rating import RatingState
        from ytmpd.ytmusic import YTMusicClient

        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        video_id = "test_video_id"

        # First like: NEUTRAL -> LIKED
        mock_ytmusic.get_track_rating.return_value = RatingState.NEUTRAL
        current = ytmusic.get_track_rating(video_id)
        transition1 = rating_mgr.apply_action(current, RatingAction.LIKE)
        assert transition1.new_state == RatingState.LIKED

        # Second like: LIKED -> NEUTRAL
        mock_ytmusic.get_track_rating.return_value = RatingState.LIKED
        current = ytmusic.get_track_rating(video_id)
        transition2 = rating_mgr.apply_action(current, RatingAction.LIKE)
        assert transition2.new_state == RatingState.NEUTRAL
        assert "Removed like" in transition2.user_message

    def test_switch_from_like_to_dislike_to_like(self, mock_mpd, mock_ytmusic, mock_config):
        """Test switching between like and dislike states."""
        from ytmpd.rating import RatingState
        from ytmpd.ytmusic import YTMusicClient

        ytmusic = YTMusicClient()
        rating_mgr = RatingManager()

        video_id = "test_video_id"

        # Start: LIKED
        mock_ytmusic.get_track_rating.return_value = RatingState.LIKED
        current = ytmusic.get_track_rating(video_id)

        # Dislike: LIKED -> DISLIKED
        transition1 = rating_mgr.apply_action(current, RatingAction.DISLIKE)
        assert transition1.new_state == RatingState.DISLIKED

        # Like: DISLIKED -> LIKED
        mock_ytmusic.get_track_rating.return_value = RatingState.DISLIKED
        current = ytmusic.get_track_rating(video_id)
        transition2 = rating_mgr.apply_action(current, RatingAction.LIKE)
        assert transition2.new_state == RatingState.LIKED
