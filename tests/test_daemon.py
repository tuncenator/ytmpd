"""Tests for ytmpd sync daemon."""

import json
import signal
import socket
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ytmpd.daemon import YTMPDaemon
from ytmpd.sync_engine import SyncResult


class TestDaemonInit:
    """Tests for daemon initialization."""

    @patch("ytmpd.daemon.YTMusicClient")
    @patch("ytmpd.daemon.MPDClient")
    @patch("ytmpd.daemon.StreamResolver")
    @patch("ytmpd.daemon.SyncEngine")
    @patch("ytmpd.daemon.load_config")
    @patch("ytmpd.daemon.get_config_dir")
    def test_daemon_initializes_components(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that daemon initializes all components correctly."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Verify components initialized
        assert daemon.ytmusic_client is not None
        assert daemon.mpd_client is not None
        assert daemon.stream_resolver is not None
        assert daemon.sync_engine is not None
        assert daemon.config == mock_load_config.return_value

    @patch("ytmpd.daemon.YTMusicClient")
    @patch("ytmpd.daemon.MPDClient")
    @patch("ytmpd.daemon.StreamResolver")
    @patch("ytmpd.daemon.SyncEngine")
    @patch("ytmpd.daemon.load_config")
    @patch("ytmpd.daemon.get_config_dir")
    def test_daemon_loads_state(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that daemon loads persisted state."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
        }

        # Create state file
        state_file = config_dir / "sync_state.json"
        state_data = {
            "last_sync": "2025-10-17T12:00:00Z",
            "last_sync_result": {
                "success": True,
                "playlists_synced": 5,
                "tracks_added": 100,
            },
            "daemon_start_time": "2025-10-17T10:00:00Z",
        }
        with open(state_file, "w") as f:
            json.dump(state_data, f)

        # Create daemon
        daemon = YTMPDaemon()

        # Verify state loaded
        assert daemon.state["last_sync"] == "2025-10-17T12:00:00Z"
        assert daemon.state["last_sync_result"]["playlists_synced"] == 5


class TestPerformSync:
    """Tests for sync execution."""

    @patch("ytmpd.daemon.YTMusicClient")
    @patch("ytmpd.daemon.MPDClient")
    @patch("ytmpd.daemon.StreamResolver")
    @patch("ytmpd.daemon.SyncEngine")
    @patch("ytmpd.daemon.load_config")
    @patch("ytmpd.daemon.get_config_dir")
    def test_perform_sync_updates_state(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine_class,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that perform_sync updates state correctly."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
        }

        # Mock sync result
        sync_result = SyncResult(
            success=True,
            playlists_synced=3,
            playlists_failed=0,
            tracks_added=50,
            tracks_failed=2,
            duration_seconds=10.5,
            errors=[],
        )
        mock_sync_engine = Mock()
        mock_sync_engine.sync_all_playlists.return_value = sync_result
        mock_sync_engine_class.return_value = mock_sync_engine

        # Create daemon
        daemon = YTMPDaemon()

        # Perform sync
        daemon._perform_sync()

        # Verify state updated
        assert daemon.state["last_sync"] is not None
        assert daemon.state["last_sync_result"]["success"] is True
        assert daemon.state["last_sync_result"]["playlists_synced"] == 3
        assert daemon.state["last_sync_result"]["tracks_added"] == 50

    @patch("ytmpd.daemon.YTMusicClient")
    @patch("ytmpd.daemon.MPDClient")
    @patch("ytmpd.daemon.StreamResolver")
    @patch("ytmpd.daemon.SyncEngine")
    @patch("ytmpd.daemon.load_config")
    @patch("ytmpd.daemon.get_config_dir")
    def test_perform_sync_handles_errors(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine_class,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that perform_sync handles errors gracefully."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
        }

        # Mock sync exception
        mock_sync_engine = Mock()
        mock_sync_engine.sync_all_playlists.side_effect = Exception("Sync failed")
        mock_sync_engine_class.return_value = mock_sync_engine

        # Create daemon
        daemon = YTMPDaemon()

        # Perform sync (should not raise)
        daemon._perform_sync()

        # Verify state updated with error
        assert daemon.state["last_sync"] is not None
        assert daemon.state["last_sync_result"]["success"] is False
        assert "Sync failed" in daemon.state["last_sync_result"]["errors"][0]

    @patch("ytmpd.daemon.YTMusicClient")
    @patch("ytmpd.daemon.MPDClient")
    @patch("ytmpd.daemon.StreamResolver")
    @patch("ytmpd.daemon.SyncEngine")
    @patch("ytmpd.daemon.load_config")
    @patch("ytmpd.daemon.get_config_dir")
    def test_perform_sync_skips_if_in_progress(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine_class,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that perform_sync skips if sync already in progress."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
        }

        mock_sync_engine = Mock()
        mock_sync_engine_class.return_value = mock_sync_engine

        # Create daemon
        daemon = YTMPDaemon()
        daemon._sync_in_progress = True

        # Perform sync
        daemon._perform_sync()

        # Verify sync not called
        mock_sync_engine.sync_all_playlists.assert_not_called()


class TestSocketCommands:
    """Tests for socket command handling."""

    @patch("ytmpd.daemon.YTMusicClient")
    @patch("ytmpd.daemon.MPDClient")
    @patch("ytmpd.daemon.StreamResolver")
    @patch("ytmpd.daemon.SyncEngine")
    @patch("ytmpd.daemon.load_config")
    @patch("ytmpd.daemon.get_config_dir")
    def test_cmd_sync_triggers_sync(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that 'sync' command triggers sync."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Call sync command
        response = daemon._cmd_sync()

        # Verify response
        assert response["success"] is True
        assert "triggered" in response["message"].lower()

    @patch("ytmpd.daemon.YTMusicClient")
    @patch("ytmpd.daemon.MPDClient")
    @patch("ytmpd.daemon.StreamResolver")
    @patch("ytmpd.daemon.SyncEngine")
    @patch("ytmpd.daemon.load_config")
    @patch("ytmpd.daemon.get_config_dir")
    def test_cmd_status_returns_state(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that 'status' command returns sync status."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
        }

        # Create daemon
        daemon = YTMPDaemon()
        daemon.state = {
            "last_sync": "2025-10-17T12:00:00Z",
            "last_sync_result": {
                "success": True,
                "playlists_synced": 5,
                "playlists_failed": 0,
                "tracks_added": 100,
                "tracks_failed": 2,
                "errors": [],
            },
            "daemon_start_time": "2025-10-17T10:00:00Z",
        }

        # Call status command
        response = daemon._cmd_status()

        # Verify response
        assert response["success"] is True
        assert response["last_sync"] == "2025-10-17T12:00:00Z"
        assert response["playlists_synced"] == 5
        assert response["tracks_added"] == 100
        assert response["last_sync_success"] is True

    @patch("ytmpd.daemon.YTMusicClient")
    @patch("ytmpd.daemon.MPDClient")
    @patch("ytmpd.daemon.StreamResolver")
    @patch("ytmpd.daemon.SyncEngine")
    @patch("ytmpd.daemon.load_config")
    @patch("ytmpd.daemon.get_config_dir")
    def test_cmd_list_returns_playlists(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic_class,
        tmp_path,
    ):
        """Test that 'list' command returns YouTube playlists."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
        }

        # Mock playlists
        mock_playlist1 = Mock()
        mock_playlist1.name = "Favorites"
        mock_playlist1.id = "PL123"
        mock_playlist1.track_count = 50

        mock_playlist2 = Mock()
        mock_playlist2.name = "Workout"
        mock_playlist2.id = "PL456"
        mock_playlist2.track_count = 30

        mock_ytmusic = Mock()
        mock_ytmusic.get_user_playlists.return_value = [mock_playlist1, mock_playlist2]
        mock_ytmusic_class.return_value = mock_ytmusic

        # Create daemon
        daemon = YTMPDaemon()

        # Call list command
        response = daemon._cmd_list()

        # Verify response
        assert response["success"] is True
        assert len(response["playlists"]) == 2
        assert response["playlists"][0]["name"] == "Favorites"
        assert response["playlists"][0]["track_count"] == 50
        assert response["playlists"][1]["name"] == "Workout"


class TestStatePersistence:
    """Tests for state persistence."""

    @patch("ytmpd.daemon.YTMusicClient")
    @patch("ytmpd.daemon.MPDClient")
    @patch("ytmpd.daemon.StreamResolver")
    @patch("ytmpd.daemon.SyncEngine")
    @patch("ytmpd.daemon.load_config")
    @patch("ytmpd.daemon.get_config_dir")
    def test_save_state_creates_file(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that save_state creates state file."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
        }

        # Create daemon
        daemon = YTMPDaemon()
        daemon.state = {
            "last_sync": "2025-10-17T12:00:00Z",
            "last_sync_result": {"success": True},
            "daemon_start_time": "2025-10-17T10:00:00Z",
        }

        # Save state
        daemon._save_state()

        # Verify file created
        state_file = config_dir / "sync_state.json"
        assert state_file.exists()

        # Verify content
        with open(state_file) as f:
            saved_state = json.load(f)
        assert saved_state["last_sync"] == "2025-10-17T12:00:00Z"

    @patch("ytmpd.daemon.YTMusicClient")
    @patch("ytmpd.daemon.MPDClient")
    @patch("ytmpd.daemon.StreamResolver")
    @patch("ytmpd.daemon.SyncEngine")
    @patch("ytmpd.daemon.load_config")
    @patch("ytmpd.daemon.get_config_dir")
    def test_load_state_reads_file(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that load_state reads existing state file."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
        }

        # Create state file
        state_file = config_dir / "sync_state.json"
        state_data = {
            "last_sync": "2025-10-17T12:00:00Z",
            "last_sync_result": {"success": True, "playlists_synced": 5},
            "daemon_start_time": "2025-10-17T10:00:00Z",
        }
        with open(state_file, "w") as f:
            json.dump(state_data, f)

        # Create daemon
        daemon = YTMPDaemon()

        # Verify state loaded
        assert daemon.state["last_sync"] == "2025-10-17T12:00:00Z"
        assert daemon.state["last_sync_result"]["playlists_synced"] == 5


class TestSignalHandling:
    """Tests for signal handling."""

    @patch("ytmpd.daemon.YTMusicClient")
    @patch("ytmpd.daemon.MPDClient")
    @patch("ytmpd.daemon.StreamResolver")
    @patch("ytmpd.daemon.SyncEngine")
    @patch("ytmpd.daemon.load_config")
    @patch("ytmpd.daemon.get_config_dir")
    def test_sighup_reloads_config(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that SIGHUP reloads configuration."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        initial_config = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
        }
        mock_load_config.return_value = initial_config

        # Create daemon
        daemon = YTMPDaemon()

        # Simulate SIGHUP
        new_config = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 10,  # Changed
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 60,  # Changed
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
        }
        mock_load_config.return_value = new_config

        daemon._signal_handler(signal.SIGHUP, None)

        # Verify config reloaded
        assert daemon.config["stream_cache_hours"] == 10
        assert daemon.config["sync_interval_minutes"] == 60


@patch("ytmpd.daemon.YTMusicClient")
@patch("ytmpd.daemon.MPDClient")
@patch("ytmpd.daemon.StreamResolver")
@patch("ytmpd.daemon.SyncEngine")
@patch("ytmpd.daemon.load_config")
@patch("ytmpd.daemon.get_config_dir")
class TestDaemonRadioSearchCommands:
    """Tests for new radio and search commands (Phase 2 stubs)."""

    # ========== Phase 2: Stub tests (removed - replaced by Phase 3 full implementation tests) ==========
    # test_cmd_radio_stub_with_video_id - REMOVED (Phase 3 implements full feature)
    # test_cmd_radio_stub_without_video_id - REMOVED (Phase 3 implements full feature)

    def test_cmd_radio_invalid_video_id_short(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that 'radio' command with too short video ID returns error."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
            "radio_playlist_limit": 25,
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Call radio command with invalid video ID (too short)
        response = daemon._cmd_radio("short")

        # Verify error response
        assert response["success"] is False
        assert "Invalid video ID format" in response["error"]

    def test_cmd_radio_invalid_video_id_chars(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that 'radio' command with invalid characters returns error."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
            "radio_playlist_limit": 25,
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Call radio command with invalid characters
        response = daemon._cmd_radio("invalid!@#$")

        # Verify error response
        assert response["success"] is False
        assert "Invalid video ID format" in response["error"]

    def test_cmd_search_stub(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that 'search' command returns stub response."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
            "radio_playlist_limit": 25,
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Call search command
        response = daemon._cmd_search("miles davis")

        # Verify response
        assert response["success"] is True
        assert "not yet implemented" in response["message"]

    def test_cmd_search_empty_query(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that 'search' command with empty query returns error."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
            "radio_playlist_limit": 25,
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Call search command with empty query
        response = daemon._cmd_search("")

        # Verify error response
        assert response["success"] is False
        assert "Empty search query" in response["error"]

    def test_cmd_search_whitespace_query(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that 'search' command with whitespace-only query returns error."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
            "radio_playlist_limit": 25,
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Call search command with whitespace query
        response = daemon._cmd_search("   ")

        # Verify error response
        assert response["success"] is False
        assert "Empty search query" in response["error"]

    def test_cmd_search_none_query(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that 'search' command with None query returns error."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
            "radio_playlist_limit": 25,
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Call search command with None
        response = daemon._cmd_search(None)

        # Verify error response
        assert response["success"] is False
        assert "Empty search query" in response["error"]

    def test_cmd_play_stub(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that 'play' command returns stub response."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
            "radio_playlist_limit": 25,
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Call play command
        response = daemon._cmd_play("2xOPkdtFeHM")

        # Verify response
        assert response["success"] is True
        assert "not yet implemented" in response["message"]

    def test_cmd_play_missing_video_id(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that 'play' command without video ID returns error."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
            "radio_playlist_limit": 25,
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Call play command without video ID
        response = daemon._cmd_play(None)

        # Verify error response
        assert response["success"] is False
        assert "Missing video ID" in response["error"]

    def test_cmd_queue_stub(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that 'queue' command returns stub response."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
            "radio_playlist_limit": 25,
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Call queue command
        response = daemon._cmd_queue("2xOPkdtFeHM")

        # Verify response
        assert response["success"] is True
        assert "not yet implemented" in response["message"]

    def test_cmd_queue_invalid_video_id(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test that 'queue' command with invalid video ID returns error."""
        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 8080,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
            "radio_playlist_limit": 25,
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Call queue command with invalid video ID
        response = daemon._cmd_queue("toolong12345")

        # Verify error response
        assert response["success"] is False
        assert "Invalid video ID format" in response["error"]

    # ========== Phase 3: Radio Feature Tests ==========

    def test_extract_video_id_from_proxy_url(
        self,
        mock_get_config_dir,
        mock_ytmusic_client,
        mock_mpd_client,
        mock_stream_resolver,
        mock_signal,
        monkeypatch,
    ):
        """Test extracting video ID from proxy URL."""
        from ytmpd.daemon import YTMPDaemon

        # Mock configuration
        monkeypatch.setattr(
            "ytmpd.daemon.load_config",
            lambda: {
                "mpd_socket_path": "~/.config/mpd/socket",
                "playlist_prefix": "YT: ",
                "sync_interval_minutes": 30,
                "enable_auto_sync": True,
                "proxy_enabled": True,
                "proxy_host": "localhost",
                "proxy_port": 6602,
                "proxy_track_mapping_db": "/tmp/track_mapping.db",
                "radio_playlist_limit": 25,
            },
        )

        # Create daemon
        daemon = YTMPDaemon()

        # Test valid proxy URL
        url = "http://localhost:6602/proxy/2xOPkdtFeHM"
        video_id = daemon._extract_video_id_from_url(url)
        assert video_id == "2xOPkdtFeHM"

        # Test another valid URL
        url2 = "http://localhost:6602/proxy/dQw4w9WgXcQ"
        video_id2 = daemon._extract_video_id_from_url(url2)
        assert video_id2 == "dQw4w9WgXcQ"

    def test_extract_video_id_from_invalid_url(
        self,
        mock_get_config_dir,
        mock_ytmusic_client,
        mock_mpd_client,
        mock_stream_resolver,
        mock_signal,
        monkeypatch,
    ):
        """Test extracting video ID from non-proxy URLs returns None."""
        from ytmpd.daemon import YTMPDaemon

        # Mock configuration
        monkeypatch.setattr(
            "ytmpd.daemon.load_config",
            lambda: {
                "mpd_socket_path": "~/.config/mpd/socket",
                "playlist_prefix": "YT: ",
                "sync_interval_minutes": 30,
                "enable_auto_sync": True,
                "proxy_enabled": True,
                "proxy_host": "localhost",
                "proxy_port": 6602,
                "proxy_track_mapping_db": "/tmp/track_mapping.db",
                "radio_playlist_limit": 25,
            },
        )

        # Create daemon
        daemon = YTMPDaemon()

        # Test empty URL
        assert daemon._extract_video_id_from_url("") is None

        # Test None URL
        assert daemon._extract_video_id_from_url(None) is None

        # Test non-proxy URL
        assert daemon._extract_video_id_from_url("http://example.com/video") is None

        # Test regular file path
        assert daemon._extract_video_id_from_url("/path/to/file.mp3") is None

        # Test URL with wrong video ID length
        assert daemon._extract_video_id_from_url("http://localhost:6602/proxy/short") is None

    def test_cmd_radio_no_current_track(
        self,
        mock_get_config_dir,
        mock_ytmusic_client,
        mock_mpd_client,
        mock_stream_resolver,
        mock_signal,
        monkeypatch,
    ):
        """Test radio command when no track is playing."""
        from ytmpd.daemon import YTMPDaemon
        from unittest.mock import Mock

        # Mock configuration
        monkeypatch.setattr(
            "ytmpd.daemon.load_config",
            lambda: {
                "mpd_socket_path": "~/.config/mpd/socket",
                "playlist_prefix": "YT: ",
                "sync_interval_minutes": 30,
                "enable_auto_sync": True,
                "proxy_enabled": True,
                "proxy_host": "localhost",
                "proxy_port": 6602,
                "proxy_track_mapping_db": "/tmp/track_mapping.db",
                "radio_playlist_limit": 25,
            },
        )

        # Create daemon
        daemon = YTMPDaemon()

        # Mock MPD client to return empty current song
        daemon.mpd_client.currentsong = Mock(return_value=None)

        # Call radio command
        response = daemon._cmd_radio(None)

        # Verify error response
        assert response["success"] is False
        assert "No track currently playing" in response["error"]

    def test_cmd_radio_non_youtube_track(
        self,
        mock_get_config_dir,
        mock_ytmusic_client,
        mock_mpd_client,
        mock_stream_resolver,
        mock_signal,
        monkeypatch,
    ):
        """Test radio command when current track is not a YouTube track."""
        from ytmpd.daemon import YTMPDaemon
        from unittest.mock import Mock

        # Mock configuration
        monkeypatch.setattr(
            "ytmpd.daemon.load_config",
            lambda: {
                "mpd_socket_path": "~/.config/mpd/socket",
                "playlist_prefix": "YT: ",
                "sync_interval_minutes": 30,
                "enable_auto_sync": True,
                "proxy_enabled": True,
                "proxy_host": "localhost",
                "proxy_port": 6602,
                "proxy_track_mapping_db": "/tmp/track_mapping.db",
                "radio_playlist_limit": 25,
            },
        )

        # Create daemon
        daemon = YTMPDaemon()

        # Mock MPD client to return non-YouTube track
        daemon.mpd_client.currentsong = Mock(return_value={
            "file": "/path/to/local/file.mp3",
            "title": "Local Track"
        })

        # Call radio command
        response = daemon._cmd_radio(None)

        # Verify error response
        assert response["success"] is False
        assert "not a YouTube track" in response["error"]

    def test_cmd_radio_success(
        self,
        mock_get_config_dir,
        mock_load_config,
        mock_sync_engine,
        mock_resolver,
        mock_mpd,
        mock_ytmusic,
        tmp_path,
    ):
        """Test successful radio playlist generation."""
        from ytmpd.daemon import YTMPDaemon
        from unittest.mock import Mock

        # Setup mocks
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "browser.json").touch()
        mock_get_config_dir.return_value = config_dir

        mock_load_config.return_value = {
            "mpd_socket_path": "/tmp/mpd.sock",
            "stream_cache_hours": 5,
            "playlist_prefix": "YT: ",
            "sync_interval_minutes": 30,
            "enable_auto_sync": True,
            "proxy_enabled": True,
            "proxy_host": "localhost",
            "proxy_port": 6602,
            "proxy_track_mapping_db": "/tmp/track_mapping.db",
            "radio_playlist_limit": 25,
        }

        # Create daemon
        daemon = YTMPDaemon()

        # Mock MPD client to return YouTube track
        daemon.mpd_client.currentsong = Mock(return_value={
            "file": "http://localhost:6602/proxy/2xOPkdtFeHM",
            "title": "Test Track"
        })

        # Mock YTMusic client's get_watch_playlist
        daemon.ytmusic_client._client = Mock()
        daemon.ytmusic_client._client.get_watch_playlist.return_value = {
            "tracks": [
                {
                    "videoId": "abc12345678",
                    "title": "Radio Track 1",
                    "artists": [{"name": "Artist 1"}],
                    "duration_seconds": 180
                },
                {
                    "videoId": "def12345678",
                    "title": "Radio Track 2",
                    "artists": [{"name": "Artist 2"}],
                    "duration_seconds": 200
                },
            ]
        }

        # Mock stream resolver
        daemon.stream_resolver.resolve_batch = Mock(return_value={
            "abc12345678": "http://stream1.url",
            "def12345678": "http://stream2.url",
        })

        # Mock MPD client's create_or_replace_playlist
        daemon.mpd_client.create_or_replace_playlist = Mock()

        # Call radio command
        response = daemon._cmd_radio(None)

        # Verify success response
        assert response["success"] is True
        assert response["tracks"] == 2
        assert response["playlist"] == "YT: Radio"
        assert "2 tracks" in response["message"]

        # Verify get_watch_playlist was called with correct params
        daemon.ytmusic_client._client.get_watch_playlist.assert_called_once_with(
            videoId="2xOPkdtFeHM",
            radio=True,
            limit=25
        )

        # Verify resolve_batch was NOT called (since proxy is enabled, lazy resolution is used)
        daemon.stream_resolver.resolve_batch.assert_not_called()

        # Verify playlist was created
        daemon.mpd_client.create_or_replace_playlist.assert_called_once()
        call_args = daemon.mpd_client.create_or_replace_playlist.call_args
        assert call_args[1]["name"] == "YT: Radio"
        assert len(call_args[1]["tracks"]) == 2
