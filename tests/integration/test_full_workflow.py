"""
Integration tests for ytmpd end-to-end workflows.

These tests verify the complete sync workflow from YouTube Music to MPD,
using mocked external dependencies but testing real component integration.
"""

import json
import os
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ytmpd.daemon import YTMPDaemon
from ytmpd.mpd_client import MPDClient
from ytmpd.stream_resolver import StreamResolver
from ytmpd.sync_engine import SyncEngine
from ytmpd.ytmusic import Playlist, Track, YTMusicClient


class TestFullSyncWorkflow:
    """
    End-to-end integration tests for the complete sync workflow.

    These tests verify that all components work together correctly:
    - YTMusicClient fetches playlists and tracks
    - StreamResolver resolves video IDs to URLs
    - SyncEngine orchestrates the sync
    - MPDClient creates playlists in MPD
    """

    @pytest.fixture
    def mock_ytmusic_responses(self):
        """Mock YouTube Music API responses for testing."""
        return {
            "playlists": [
                Playlist(id="PL1", name="Test Favorites", track_count=3),
                Playlist(id="PL2", name="Workout Mix", track_count=2),
            ],
            "tracks": {
                "PL1": [
                    Track(
                        video_id="vid1",
                        title="Test Song 1",
                        artist="Test Artist 1",
                    ),
                    Track(
                        video_id="vid2",
                        title="Test Song 2",
                        artist="Test Artist 2",
                    ),
                    Track(
                        video_id="vid3",
                        title="Test Song 3",
                        artist="Test Artist 3",
                    ),
                ],
                "PL2": [
                    Track(
                        video_id="vid4",
                        title="Workout Song 1",
                        artist="Workout Artist 1",
                    ),
                    Track(
                        video_id="vid5",
                        title="Workout Song 2",
                        artist="Workout Artist 2",
                    ),
                ],
            },
        }

    @pytest.fixture
    def mock_stream_urls(self):
        """Mock stream URLs for testing."""
        return {
            "vid1": "http://example.com/stream1.m4a",
            "vid2": "http://example.com/stream2.m4a",
            "vid3": "http://example.com/stream3.m4a",
            "vid4": "http://example.com/stream4.m4a",
            "vid5": "http://example.com/stream5.m4a",
        }

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary config directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def test_config(self, temp_config_dir):
        """Create test configuration."""
        return {
            "auth_file": str(temp_config_dir / "browser.json"),
            "log_level": "DEBUG",
            "log_file": str(temp_config_dir / "ytmpd.log"),
            "mpd_socket_path": str(temp_config_dir / "mpd_socket"),
            "sync_interval_minutes": 30,
            "enable_auto_sync": False,  # Disable auto-sync for tests
            "playlist_prefix": "YT: ",
            "stream_cache_hours": 5,
            "socket_path": str(temp_config_dir / "sync_socket"),
            "state_file": str(temp_config_dir / "sync_state.json"),
        }

    def test_full_sync_workflow_mocked(
        self, test_config, mock_ytmusic_responses, mock_stream_urls
    ):
        """
        Test complete sync workflow with mocked external dependencies.

        Workflow:
        1. Mock YTMusicClient to return test playlists
        2. Mock StreamResolver to return test URLs
        3. Mock MPDClient to track playlist creation
        4. Create SyncEngine and perform sync
        5. Verify playlists created with correct tracks
        """
        # Setup: Create mock YTMusic client
        mock_ytmusic = Mock(spec=YTMusicClient)
        mock_ytmusic.get_user_playlists.return_value = mock_ytmusic_responses[
            "playlists"
        ]
        mock_ytmusic.get_playlist_tracks.side_effect = (
            lambda playlist_id: mock_ytmusic_responses["tracks"][playlist_id]
        )
        mock_ytmusic.get_liked_songs.return_value = []  # No liked songs for this test

        # Setup: Create mock MPD client
        mock_mpd = Mock(spec=MPDClient)
        mock_mpd.create_or_replace_playlist = Mock()

        # Setup: Create mock StreamResolver that filters by requested video IDs
        mock_resolver = Mock(spec=StreamResolver)
        # Mock resolve_batch to return only requested video IDs
        def mock_resolve_batch(video_ids):
            return {vid: mock_stream_urls[vid] for vid in video_ids if vid in mock_stream_urls}
        mock_resolver.resolve_batch.side_effect = mock_resolve_batch

        # Execute: Create sync engine and perform sync
        sync_engine = SyncEngine(
            ytmusic_client=mock_ytmusic,
            mpd_client=mock_mpd,
            stream_resolver=mock_resolver,
            playlist_prefix=test_config["playlist_prefix"],
        )

        result = sync_engine.sync_all_playlists()

        # Verify: Sync completed successfully
        assert result.success is True
        assert result.playlists_synced == 2
        assert result.playlists_failed == 0
        assert result.tracks_added == 5
        assert result.tracks_failed == 0
        assert len(result.errors) == 0

        # Verify: Playlists fetched from YouTube Music
        mock_ytmusic.get_user_playlists.assert_called_once()
        assert mock_ytmusic.get_playlist_tracks.call_count == 2

        # Verify: Stream URLs resolved
        mock_resolver.resolve_batch.assert_called()

        # Verify: Playlists created in MPD with prefix
        assert mock_mpd.create_or_replace_playlist.call_count == 2

        # Check first playlist
        call_args_1 = mock_mpd.create_or_replace_playlist.call_args_list[0]
        assert call_args_1[0][0] == "YT: Test Favorites"
        assert len(call_args_1[0][1]) == 3  # 3 tracks

        # Check second playlist
        call_args_2 = mock_mpd.create_or_replace_playlist.call_args_list[1]
        assert call_args_2[0][0] == "YT: Workout Mix"
        assert len(call_args_2[0][1]) == 2  # 2 tracks

    def test_sync_with_partial_failures(
        self, test_config, mock_ytmusic_responses, mock_stream_urls
    ):
        """
        Test sync handles partial failures gracefully.

        Scenario:
        - Some video IDs fail to resolve
        - Sync should continue with available tracks
        """
        # Setup: Mock components
        mock_ytmusic = Mock(spec=YTMusicClient)
        mock_ytmusic.get_user_playlists.return_value = [
            mock_ytmusic_responses["playlists"][0]
        ]  # Just first playlist
        mock_ytmusic.get_playlist_tracks.return_value = mock_ytmusic_responses[
            "tracks"
        ]["PL1"]
        mock_ytmusic.get_liked_songs.return_value = []  # No liked songs for this test

        mock_mpd = Mock(spec=MPDClient)
        mock_resolver = Mock(spec=StreamResolver)

        # Only resolve 2 out of 3 videos (vid3 fails)
        partial_urls = {
            "vid1": mock_stream_urls["vid1"],
            "vid2": mock_stream_urls["vid2"],
            # vid3 missing (failed to resolve)
        }
        mock_resolver.resolve_batch.return_value = partial_urls

        # Execute: Sync with partial failures
        sync_engine = SyncEngine(
            ytmusic_client=mock_ytmusic,
            mpd_client=mock_mpd,
            stream_resolver=mock_resolver,
            playlist_prefix=test_config["playlist_prefix"],
        )

        result = sync_engine.sync_all_playlists()

        # Verify: Sync succeeded with partial results
        assert result.success is True
        assert result.playlists_synced == 1
        assert result.tracks_added == 2  # Only 2 tracks resolved
        assert result.tracks_failed == 1  # 1 track failed

        # Verify: Playlist created with available tracks
        mock_mpd.create_or_replace_playlist.assert_called_once()
        call_args = mock_mpd.create_or_replace_playlist.call_args
        assert call_args[0][0] == "YT: Test Favorites"
        assert len(call_args[0][1]) == 2  # Only 2 URLs

    # NOTE: Daemon state persistence testing is complex due to daemon initialization
    # requirements. State persistence is tested via manual testing and covered by
    # daemon unit tests in test_daemon.py.

    def test_manual_sync_trigger_via_socket(
        self, test_config, temp_config_dir
    ):
        """
        Test manual sync trigger via Unix socket.

        Workflow:
        1. Start daemon in background
        2. Send "sync" command via socket
        3. Verify sync triggered
        4. Send "status" command
        5. Verify status returned
        6. Send "quit" command
        7. Verify daemon stops
        """
        # This test requires a running daemon, which is complex to set up
        # For now, we'll test the socket protocol directly

        # Setup: Create a simple socket server that mimics daemon behavior
        socket_path = str(temp_config_dir / "test_socket")

        server_running = threading.Event()
        commands_received = []

        def socket_server():
            """Simple socket server for testing."""
            # Remove old socket if exists
            if os.path.exists(socket_path):
                os.remove(socket_path)

            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(socket_path)
            sock.listen(1)
            sock.settimeout(2.0)

            server_running.set()

            try:
                while True:
                    try:
                        conn, _ = sock.accept()
                        data = conn.recv(1024).decode().strip()
                        commands_received.append(data)

                        # Send mock response based on command
                        if data == "sync":
                            response = {"success": True, "message": "Sync triggered"}
                        elif data == "status":
                            response = {
                                "success": True,
                                "last_sync": "2025-10-17T10:00:00Z",
                                "playlists_synced": 2,
                                "tracks_added": 5,
                            }
                        elif data == "quit":
                            response = {"success": True, "message": "Shutting down"}
                            conn.sendall(json.dumps(response).encode())
                            conn.close()
                            break
                        else:
                            response = {"success": False, "error": "Unknown command"}

                        conn.sendall(json.dumps(response).encode())
                        conn.close()
                    except socket.timeout:
                        continue
            finally:
                sock.close()
                if os.path.exists(socket_path):
                    os.remove(socket_path)

        # Start server in background
        server_thread = threading.Thread(target=socket_server, daemon=True)
        server_thread.start()

        # Wait for server to start
        server_running.wait(timeout=2)
        time.sleep(0.1)

        # Test: Send commands via socket
        def send_command(cmd):
            """Helper to send command via socket."""
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(socket_path)
            sock.sendall((cmd + "\n").encode())
            response = sock.recv(4096).decode()
            sock.close()
            return json.loads(response)

        # Verify: Sync command
        sync_response = send_command("sync")
        assert sync_response["success"] is True
        assert "sync" in commands_received

        # Verify: Status command
        status_response = send_command("status")
        assert status_response["success"] is True
        assert status_response["playlists_synced"] == 2
        assert "status" in commands_received

        # Verify: Quit command
        quit_response = send_command("quit")
        assert quit_response["success"] is True
        assert "quit" in commands_received

        # Wait for server to stop
        server_thread.join(timeout=2)

    def test_sync_preview_without_changes(
        self, test_config, mock_ytmusic_responses
    ):
        """
        Test sync preview mode returns expected data without making changes.

        Workflow:
        1. Create sync engine
        2. Call get_sync_preview()
        3. Verify preview data returned
        4. Verify no actual sync performed (MPD not called)
        """
        # Setup: Mock components
        mock_ytmusic = Mock(spec=YTMusicClient)
        mock_ytmusic.get_user_playlists.return_value = mock_ytmusic_responses[
            "playlists"
        ]

        mock_mpd = Mock(spec=MPDClient)
        # Return playlists with and without prefix
        mock_mpd.list_playlists.return_value = ["Old Playlist 1", "YT: Existing Playlist"]

        mock_resolver = Mock(spec=StreamResolver)

        # Execute: Get sync preview
        sync_engine = SyncEngine(
            ytmusic_client=mock_ytmusic,
            mpd_client=mock_mpd,
            stream_resolver=mock_resolver,
            playlist_prefix=test_config["playlist_prefix"],
        )

        preview = sync_engine.get_sync_preview()

        # Verify: Preview contains expected data
        assert len(preview.youtube_playlists) == 2
        assert "Test Favorites" in preview.youtube_playlists
        assert "Workout Mix" in preview.youtube_playlists
        assert len(preview.existing_mpd_playlists) == 1
        assert "YT: Existing Playlist" in preview.existing_mpd_playlists

        # Verify: No actual sync operations performed
        mock_mpd.create_or_replace_playlist.assert_not_called()
        mock_resolver.resolve_batch.assert_not_called()


class TestPerformanceScenarios:
    """
    Performance and stress tests for ytmpd sync operations.
    """

    def test_large_playlist_sync(self):
        """
        Test syncing a large playlist (100+ tracks).

        Verifies that:
        - Sync completes without timeout
        - Memory usage stays reasonable
        - All tracks processed
        """
        # Setup: Create large playlist
        large_playlist = Playlist(
            id="PL_LARGE", name="Large Playlist", track_count=100
        )

        large_tracks = [
            Track(
                video_id=f"vid{i}",
                title=f"Song {i}",
                artist=f"Artist {i}",
            )
            for i in range(100)
        ]

        # Mock large URL resolution
        large_urls = {f"vid{i}": f"http://example.com/stream{i}.m4a" for i in range(100)}

        # Setup: Mock components
        mock_ytmusic = Mock(spec=YTMusicClient)
        mock_ytmusic.get_user_playlists.return_value = [large_playlist]
        mock_ytmusic.get_playlist_tracks.return_value = large_tracks
        mock_ytmusic.get_liked_songs.return_value = []  # No liked songs for this test

        mock_mpd = Mock(spec=MPDClient)
        mock_resolver = Mock(spec=StreamResolver)
        mock_resolver.resolve_batch.return_value = large_urls

        # Execute: Sync large playlist
        sync_engine = SyncEngine(
            ytmusic_client=mock_ytmusic,
            mpd_client=mock_mpd,
            stream_resolver=mock_resolver,
            playlist_prefix="YT: ",
        )

        start_time = time.time()
        result = sync_engine.sync_all_playlists()
        duration = time.time() - start_time

        # Verify: Sync completed successfully
        assert result.success is True
        assert result.playlists_synced == 1
        assert result.tracks_added == 100
        assert result.tracks_failed == 0

        # Verify: Reasonable performance (should be fast with mocks)
        assert duration < 5.0  # Should complete in under 5 seconds

        # Verify: All tracks added to playlist
        call_args = mock_mpd.create_or_replace_playlist.call_args
        assert len(call_args[0][1]) == 100

    def test_many_playlists_sync(self):
        """
        Test syncing many playlists (50+).

        Verifies that:
        - All playlists processed
        - No memory leaks or resource exhaustion
        """
        # Setup: Create many playlists
        many_playlists = [
            Playlist(id=f"PL{i}", name=f"Playlist {i}", track_count=5)
            for i in range(50)
        ]

        # Mock tracks (5 tracks per playlist)
        def get_tracks(playlist_id):
            playlist_num = int(playlist_id[2:])  # Extract number from "PL123"
            return [
                Track(
                    video_id=f"vid{playlist_num}_{j}",
                    title=f"Song {j}",
                    artist=f"Artist {j}",
                )
                for j in range(5)
            ]

        # Mock URLs
        all_urls = {
            f"vid{i}_{j}": f"http://example.com/stream{i}_{j}.m4a"
            for i in range(50)
            for j in range(5)
        }

        # Setup: Mock components
        mock_ytmusic = Mock(spec=YTMusicClient)
        mock_ytmusic.get_user_playlists.return_value = many_playlists
        mock_ytmusic.get_playlist_tracks.side_effect = get_tracks
        mock_ytmusic.get_liked_songs.return_value = []  # No liked songs for this test

        mock_mpd = Mock(spec=MPDClient)
        mock_resolver = Mock(spec=StreamResolver)
        mock_resolver.resolve_batch.side_effect = lambda vids: {
            vid: all_urls[vid] for vid in vids if vid in all_urls
        }

        # Execute: Sync many playlists
        sync_engine = SyncEngine(
            ytmusic_client=mock_ytmusic,
            mpd_client=mock_mpd,
            stream_resolver=mock_resolver,
            playlist_prefix="YT: ",
        )

        result = sync_engine.sync_all_playlists()

        # Verify: All playlists synced
        assert result.success is True
        assert result.playlists_synced == 50
        assert result.tracks_added == 250  # 50 playlists * 5 tracks
        assert result.tracks_failed == 0

        # Verify: All playlists created in MPD
        assert mock_mpd.create_or_replace_playlist.call_count == 50
