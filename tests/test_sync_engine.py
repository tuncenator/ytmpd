"""
Tests for the sync engine module.
"""

import pytest
from unittest.mock import Mock, patch, call

from ytmpd.sync_engine import SyncEngine, SyncResult, SyncPreview
from ytmpd.ytmusic import Playlist, Track
from ytmpd.mpd_client import TrackWithMetadata
from ytmpd.exceptions import (
    YTMusicAPIError,
    MPDConnectionError,
    MPDPlaylistError,
)


class TestSyncEngineInit:
    """Tests for SyncEngine initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default prefix."""
        ytmusic = Mock()
        mpd = Mock()
        resolver = Mock()

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)

        assert engine.ytmusic == ytmusic
        assert engine.mpd == mpd
        assert engine.resolver == resolver
        assert engine.prefix == "YT: "

    def test_init_with_custom_prefix(self):
        """Test initialization with custom prefix."""
        ytmusic = Mock()
        mpd = Mock()
        resolver = Mock()

        engine = SyncEngine(ytmusic, mpd, resolver, playlist_prefix="YouTube - ", sync_liked_songs=False)

        assert engine.prefix == "YouTube - "

    def test_init_with_empty_prefix(self):
        """Test initialization with empty prefix."""
        ytmusic = Mock()
        mpd = Mock()
        resolver = Mock()

        engine = SyncEngine(ytmusic, mpd, resolver, playlist_prefix="", sync_liked_songs=False)

        assert engine.prefix == ""


class TestSyncAllPlaylists:
    """Tests for sync_all_playlists method."""

    def test_sync_all_playlists_success(self):
        """Test successful sync of multiple playlists."""
        # Mock dependencies
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=3),
            Playlist(id="PL2", name="Workout", track_count=2),
        ]
        ytmusic.get_playlist_tracks.side_effect = [
            [
                Track(video_id="vid1", title="Song 1", artist="Artist 1"),
                Track(video_id="vid2", title="Song 2", artist="Artist 2"),
                Track(video_id="vid3", title="Song 3", artist="Artist 3"),
            ],
            [
                Track(video_id="vid4", title="Song 4", artist="Artist 4"),
                Track(video_id="vid5", title="Song 5", artist="Artist 5"),
            ],
        ]

        mpd = Mock()
        resolver = Mock()
        resolver.resolve_batch.side_effect = [
            {
                "vid1": "http://example.com/1.m4a",
                "vid2": "http://example.com/2.m4a",
                "vid3": "http://example.com/3.m4a",
            },
            {
                "vid4": "http://example.com/4.m4a",
                "vid5": "http://example.com/5.m4a",
            },
        ]

        engine = SyncEngine(ytmusic, mpd, resolver, playlist_prefix="YT: ", sync_liked_songs=False)
        result = engine.sync_all_playlists()

        # Verify result
        assert result.success is True
        assert result.playlists_synced == 2
        assert result.playlists_failed == 0
        assert result.tracks_added == 5
        assert result.tracks_failed == 0
        assert result.duration_seconds > 0
        assert len(result.errors) == 0

        # Verify MPD playlists created
        assert mpd.create_or_replace_playlist.call_count == 2
        mpd.create_or_replace_playlist.assert_any_call(
            "YT: Favorites",
            [
                TrackWithMetadata(url="http://example.com/1.m4a", title="Song 1", artist="Artist 1", video_id="vid1"),
                TrackWithMetadata(url="http://example.com/2.m4a", title="Song 2", artist="Artist 2", video_id="vid2"),
                TrackWithMetadata(url="http://example.com/3.m4a", title="Song 3", artist="Artist 3", video_id="vid3"),
            ],
            proxy_config=None,
        )
        mpd.create_or_replace_playlist.assert_any_call(
            "YT: Workout",
            [
                TrackWithMetadata(url="http://example.com/4.m4a", title="Song 4", artist="Artist 4", video_id="vid4"),
                TrackWithMetadata(url="http://example.com/5.m4a", title="Song 5", artist="Artist 5", video_id="vid5"),
            ],
            proxy_config=None,
        )

    def test_sync_all_playlists_empty(self):
        """Test sync when no playlists exist."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = []

        mpd = Mock()
        resolver = Mock()

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        result = engine.sync_all_playlists()

        assert result.success is True
        assert result.playlists_synced == 0
        assert result.playlists_failed == 0
        assert result.tracks_added == 0
        assert result.tracks_failed == 0
        assert len(result.errors) == 0

        # Verify no MPD operations performed
        mpd.create_or_replace_playlist.assert_not_called()

    def test_sync_all_playlists_partial_track_failures(self):
        """Test sync when some tracks fail to resolve."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=3),
        ]
        ytmusic.get_playlist_tracks.return_value = [
            Track(video_id="vid1", title="Song 1", artist="Artist 1"),
            Track(video_id="vid2", title="Song 2", artist="Artist 2"),
            Track(video_id="vid3", title="Song 3", artist="Artist 3"),
        ]

        mpd = Mock()
        resolver = Mock()
        # Only resolve 2 out of 3 tracks
        resolver.resolve_batch.return_value = {
            "vid1": "http://example.com/1.m4a",
            "vid3": "http://example.com/3.m4a",
        }

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        result = engine.sync_all_playlists()

        assert result.success is True
        assert result.playlists_synced == 1
        assert result.playlists_failed == 0
        assert result.tracks_added == 2
        assert result.tracks_failed == 1

        # Verify playlist created with only successful tracks
        mpd.create_or_replace_playlist.assert_called_once_with(
            "YT: Favorites",
            [
                TrackWithMetadata(url="http://example.com/1.m4a", title="Song 1", artist="Artist 1", video_id="vid1"),
                TrackWithMetadata(url="http://example.com/3.m4a", title="Song 3", artist="Artist 3", video_id="vid3"),
            ],
            proxy_config=None,
        )

    def test_sync_all_playlists_all_tracks_fail(self):
        """Test sync when all tracks fail to resolve."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=2),
        ]
        ytmusic.get_playlist_tracks.return_value = [
            Track(video_id="vid1", title="Song 1", artist="Artist 1"),
            Track(video_id="vid2", title="Song 2", artist="Artist 2"),
        ]

        mpd = Mock()
        resolver = Mock()
        # No tracks resolved
        resolver.resolve_batch.return_value = {}

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        result = engine.sync_all_playlists()

        # Playlist should fail if no tracks resolve
        assert result.success is False
        assert result.playlists_synced == 0
        assert result.playlists_failed == 1
        assert result.tracks_added == 0
        assert result.tracks_failed == 0  # Failed at playlist level, not track level
        assert len(result.errors) > 0

        # Verify no playlist created
        mpd.create_or_replace_playlist.assert_not_called()

    def test_sync_all_playlists_one_playlist_fails(self):
        """Test sync when one playlist fails but others succeed."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=2),
            Playlist(id="PL2", name="Workout", track_count=2),
        ]

        # First playlist will fail when fetching tracks
        ytmusic.get_playlist_tracks.side_effect = [
            YTMusicAPIError("Failed to fetch tracks"),
            [
                Track(video_id="vid3", title="Song 3", artist="Artist 3"),
                Track(video_id="vid4", title="Song 4", artist="Artist 4"),
            ],
        ]

        mpd = Mock()
        resolver = Mock()
        resolver.resolve_batch.return_value = {
            "vid3": "http://example.com/3.m4a",
            "vid4": "http://example.com/4.m4a",
        }

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        result = engine.sync_all_playlists()

        # Should continue syncing despite one failure
        assert result.success is False  # One failure means not fully successful
        assert result.playlists_synced == 1
        assert result.playlists_failed == 1
        assert result.tracks_added == 2
        assert result.tracks_failed == 0
        assert len(result.errors) == 1

        # Verify only second playlist created
        mpd.create_or_replace_playlist.assert_called_once_with(
            "YT: Workout",
            [
                TrackWithMetadata(url="http://example.com/3.m4a", title="Song 3", artist="Artist 3", video_id="vid3"),
                TrackWithMetadata(url="http://example.com/4.m4a", title="Song 4", artist="Artist 4", video_id="vid4"),
            ],
            proxy_config=None,
        )

    def test_sync_all_playlists_ytmusic_api_error(self):
        """Test sync when YouTube Music API fails."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.side_effect = YTMusicAPIError("API error")

        mpd = Mock()
        resolver = Mock()

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        result = engine.sync_all_playlists()

        assert result.success is False
        assert result.playlists_synced == 0
        assert result.playlists_failed == 0
        assert result.tracks_added == 0
        assert result.tracks_failed == 0
        assert len(result.errors) == 1
        assert "YouTube Music" in result.errors[0]

    def test_sync_all_playlists_mpd_error(self):
        """Test sync when MPD operations fail."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=2),
        ]
        ytmusic.get_playlist_tracks.return_value = [
            Track(video_id="vid1", title="Song 1", artist="Artist 1"),
            Track(video_id="vid2", title="Song 2", artist="Artist 2"),
        ]

        mpd = Mock()
        mpd.create_or_replace_playlist.side_effect = MPDPlaylistError("MPD error")

        resolver = Mock()
        resolver.resolve_batch.return_value = {
            "vid1": "http://example.com/1.m4a",
            "vid2": "http://example.com/2.m4a",
        }

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        result = engine.sync_all_playlists()

        assert result.success is False
        assert result.playlists_synced == 0
        assert result.playlists_failed == 1
        assert len(result.errors) == 1

    def test_sync_all_playlists_custom_prefix(self):
        """Test sync uses custom prefix."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=1),
        ]
        ytmusic.get_playlist_tracks.return_value = [
            Track(video_id="vid1", title="Song 1", artist="Artist 1"),
        ]

        mpd = Mock()
        resolver = Mock()
        resolver.resolve_batch.return_value = {
            "vid1": "http://example.com/1.m4a",
        }

        engine = SyncEngine(ytmusic, mpd, resolver, playlist_prefix="YouTube - ", sync_liked_songs=False)
        result = engine.sync_all_playlists()

        assert result.success is True
        mpd.create_or_replace_playlist.assert_called_once_with(
            "YouTube - Favorites",
            [TrackWithMetadata(url="http://example.com/1.m4a", title="Song 1", artist="Artist 1", video_id="vid1")],
            proxy_config=None,
        )


class TestSyncSinglePlaylist:
    """Tests for sync_single_playlist method."""

    def test_sync_single_playlist_success(self):
        """Test successful sync of a single playlist."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=2),
            Playlist(id="PL2", name="Workout", track_count=2),
        ]
        ytmusic.get_playlist_tracks.return_value = [
            Track(video_id="vid1", title="Song 1", artist="Artist 1"),
            Track(video_id="vid2", title="Song 2", artist="Artist 2"),
        ]

        mpd = Mock()
        resolver = Mock()
        resolver.resolve_batch.return_value = {
            "vid1": "http://example.com/1.m4a",
            "vid2": "http://example.com/2.m4a",
        }

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        result = engine.sync_single_playlist("Favorites")

        assert result.success is True
        assert result.playlists_synced == 1
        assert result.playlists_failed == 0
        assert result.tracks_added == 2
        assert result.tracks_failed == 0

        # Verify correct playlist fetched and synced
        ytmusic.get_playlist_tracks.assert_called_once_with("PL1")
        mpd.create_or_replace_playlist.assert_called_once_with(
            "YT: Favorites",
            [
                TrackWithMetadata(url="http://example.com/1.m4a", title="Song 1", artist="Artist 1", video_id="vid1"),
                TrackWithMetadata(url="http://example.com/2.m4a", title="Song 2", artist="Artist 2", video_id="vid2"),
            ],
            proxy_config=None,
        )

    def test_sync_single_playlist_not_found(self):
        """Test sync when playlist name doesn't exist."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=2),
        ]

        mpd = Mock()
        resolver = Mock()

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        result = engine.sync_single_playlist("NonExistent")

        assert result.success is False
        assert result.playlists_synced == 0
        assert result.playlists_failed == 1
        assert len(result.errors) == 1
        assert "not found" in result.errors[0]

        # Verify no sync attempted
        ytmusic.get_playlist_tracks.assert_not_called()
        mpd.create_or_replace_playlist.assert_not_called()

    def test_sync_single_playlist_with_failures(self):
        """Test sync single playlist with some track failures."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=3),
        ]
        ytmusic.get_playlist_tracks.return_value = [
            Track(video_id="vid1", title="Song 1", artist="Artist 1"),
            Track(video_id="vid2", title="Song 2", artist="Artist 2"),
            Track(video_id="vid3", title="Song 3", artist="Artist 3"),
        ]

        mpd = Mock()
        resolver = Mock()
        # Only 2 out of 3 resolve
        resolver.resolve_batch.return_value = {
            "vid1": "http://example.com/1.m4a",
            "vid2": "http://example.com/2.m4a",
        }

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        result = engine.sync_single_playlist("Favorites")

        assert result.success is True
        assert result.playlists_synced == 1
        assert result.playlists_failed == 0
        assert result.tracks_added == 2
        assert result.tracks_failed == 1


class TestGetSyncPreview:
    """Tests for get_sync_preview method."""

    def test_get_sync_preview_success(self):
        """Test successful preview generation."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=50),
            Playlist(id="PL2", name="Workout", track_count=30),
            Playlist(id="PL3", name="Chill", track_count=20),
        ]

        mpd = Mock()
        mpd.list_playlists.return_value = [
            "YT: Favorites",
            "YT: Workout",
            "Other Playlist",
        ]

        resolver = Mock()

        engine = SyncEngine(ytmusic, mpd, resolver, playlist_prefix="YT: ", sync_liked_songs=False)
        preview = engine.get_sync_preview()

        assert len(preview.youtube_playlists) == 3
        assert "Favorites" in preview.youtube_playlists
        assert "Workout" in preview.youtube_playlists
        assert "Chill" in preview.youtube_playlists
        assert preview.total_tracks == 100  # 50 + 30 + 20
        assert len(preview.existing_mpd_playlists) == 2
        assert "YT: Favorites" in preview.existing_mpd_playlists
        assert "YT: Workout" in preview.existing_mpd_playlists
        assert "Other Playlist" not in preview.existing_mpd_playlists

    def test_get_sync_preview_no_playlists(self):
        """Test preview when no playlists exist."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = []

        mpd = Mock()
        mpd.list_playlists.return_value = []

        resolver = Mock()

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        preview = engine.get_sync_preview()

        assert len(preview.youtube_playlists) == 0
        assert preview.total_tracks == 0
        assert len(preview.existing_mpd_playlists) == 0

    def test_get_sync_preview_mpd_error(self):
        """Test preview continues even if MPD listing fails."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=50),
        ]

        mpd = Mock()
        mpd.list_playlists.side_effect = MPDConnectionError("Not connected")

        resolver = Mock()

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        preview = engine.get_sync_preview()

        # Should still return YouTube info despite MPD error
        assert len(preview.youtube_playlists) == 1
        assert preview.total_tracks == 50
        assert len(preview.existing_mpd_playlists) == 0  # Empty due to error

    def test_get_sync_preview_custom_prefix(self):
        """Test preview with custom prefix filtering."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=10),
        ]

        mpd = Mock()
        mpd.list_playlists.return_value = [
            "YouTube - Favorites",
            "YouTube - Workout",
            "YT: OldPrefix",
            "Local Playlist",
        ]

        resolver = Mock()

        engine = SyncEngine(ytmusic, mpd, resolver, playlist_prefix="YouTube - ", sync_liked_songs=False)
        preview = engine.get_sync_preview()

        # Only playlists with "YouTube - " prefix should be included
        assert len(preview.existing_mpd_playlists) == 2
        assert "YouTube - Favorites" in preview.existing_mpd_playlists
        assert "YouTube - Workout" in preview.existing_mpd_playlists
        assert "YT: OldPrefix" not in preview.existing_mpd_playlists


class TestSyncDataStructures:
    """Tests for SyncResult and SyncPreview dataclasses."""

    def test_sync_result_creation(self):
        """Test SyncResult can be created with all fields."""
        result = SyncResult(
            success=True,
            playlists_synced=5,
            playlists_failed=1,
            tracks_added=100,
            tracks_failed=10,
            duration_seconds=45.2,
            errors=["Error 1", "Error 2"],
        )

        assert result.success is True
        assert result.playlists_synced == 5
        assert result.playlists_failed == 1
        assert result.tracks_added == 100
        assert result.tracks_failed == 10
        assert result.duration_seconds == 45.2
        assert len(result.errors) == 2

    def test_sync_preview_creation(self):
        """Test SyncPreview can be created with all fields."""
        preview = SyncPreview(
            youtube_playlists=["Favorites", "Workout"],
            total_tracks=80,
            existing_mpd_playlists=["YT: Favorites"],
        )

        assert len(preview.youtube_playlists) == 2
        assert preview.total_tracks == 80
        assert len(preview.existing_mpd_playlists) == 1


class TestSyncEngineIntegration:
    """Integration-style tests with more realistic scenarios."""

    def test_sync_preserves_track_order(self):
        """Test that track order is preserved in synced playlist."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=3),
        ]
        ytmusic.get_playlist_tracks.return_value = [
            Track(video_id="vid1", title="Song 1", artist="Artist 1"),
            Track(video_id="vid2", title="Song 2", artist="Artist 2"),
            Track(video_id="vid3", title="Song 3", artist="Artist 3"),
        ]

        mpd = Mock()
        resolver = Mock()
        resolver.resolve_batch.return_value = {
            "vid1": "http://example.com/1.m4a",
            "vid2": "http://example.com/2.m4a",
            "vid3": "http://example.com/3.m4a",
        }

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        result = engine.sync_all_playlists()

        # Verify order is preserved
        mpd.create_or_replace_playlist.assert_called_once()
        call_args = mpd.create_or_replace_playlist.call_args
        tracks = call_args[0][1]  # Second positional argument

        assert tracks == [
            TrackWithMetadata(url="http://example.com/1.m4a", title="Song 1", artist="Artist 1", video_id="vid1"),
            TrackWithMetadata(url="http://example.com/2.m4a", title="Song 2", artist="Artist 2", video_id="vid2"),
            TrackWithMetadata(url="http://example.com/3.m4a", title="Song 3", artist="Artist 3", video_id="vid3"),
        ]

    def test_sync_skips_unresolved_but_keeps_order(self):
        """Test that unresolved tracks are skipped but order preserved."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=4),
        ]
        ytmusic.get_playlist_tracks.return_value = [
            Track(video_id="vid1", title="Song 1", artist="Artist 1"),
            Track(video_id="vid2", title="Song 2", artist="Artist 2"),
            Track(video_id="vid3", title="Song 3", artist="Artist 3"),
            Track(video_id="vid4", title="Song 4", artist="Artist 4"),
        ]

        mpd = Mock()
        resolver = Mock()
        # vid2 and vid3 fail to resolve
        resolver.resolve_batch.return_value = {
            "vid1": "http://example.com/1.m4a",
            "vid4": "http://example.com/4.m4a",
        }

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        result = engine.sync_all_playlists()

        # Verify vid1 comes before vid4 (order preserved)
        call_args = mpd.create_or_replace_playlist.call_args
        tracks = call_args[0][1]

        assert tracks == [
            TrackWithMetadata(url="http://example.com/1.m4a", title="Song 1", artist="Artist 1", video_id="vid1"),
            TrackWithMetadata(url="http://example.com/4.m4a", title="Song 4", artist="Artist 4", video_id="vid4"),
        ]
        assert result.tracks_added == 2
        assert result.tracks_failed == 2

    def test_sync_empty_playlist_is_skipped(self):
        """Test that playlists with no tracks are skipped gracefully."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Favorites", track_count=0),  # This should already be filtered by get_user_playlists
            Playlist(id="PL2", name="Workout", track_count=2),
        ]
        # First call returns empty list (edge case if filtering failed)
        ytmusic.get_playlist_tracks.side_effect = [
            [],
            [
                Track(video_id="vid1", title="Song 1", artist="Artist 1"),
                Track(video_id="vid2", title="Song 2", artist="Artist 2"),
            ],
        ]

        mpd = Mock()
        resolver = Mock()
        resolver.resolve_batch.return_value = {
            "vid1": "http://example.com/1.m4a",
            "vid2": "http://example.com/2.m4a",
        }

        engine = SyncEngine(ytmusic, mpd, resolver, sync_liked_songs=False)
        result = engine.sync_all_playlists()

        # Both playlists are counted as "synced" - empty one is skipped gracefully
        # Empty playlist is handled with warning but counts as "successful"
        assert result.playlists_synced == 2
        assert result.playlists_failed == 0
        assert result.tracks_added == 2  # Only from Workout playlist

        # Only Workout playlist should be created in MPD (empty one skipped)
        mpd.create_or_replace_playlist.assert_called_once_with(
            "YT: Workout",
            [
                TrackWithMetadata(url="http://example.com/1.m4a", title="Song 1", artist="Artist 1", video_id="vid1"),
                TrackWithMetadata(url="http://example.com/2.m4a", title="Song 2", artist="Artist 2", video_id="vid2"),
            ],
            proxy_config=None,
        )
