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
