"""Tests for ytmpd.config module."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from ytmpd.config import get_config_dir, load_config


class TestGetConfigDir:
    """Tests for get_config_dir function."""

    def test_get_config_dir_returns_correct_path(self) -> None:
        """Test that get_config_dir returns the expected path."""
        config_dir = get_config_dir()
        expected_path = Path.home() / ".config" / "ytmpd"
        assert config_dir == expected_path


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_creates_directory_if_missing(self) -> None:
        """Test that load_config creates config directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

                # Check that directory was created
                assert mock_config_dir.exists()
                assert mock_config_dir.is_dir()

    def test_load_config_returns_defaults_when_no_file_exists(self) -> None:
        """Test that load_config returns default config when file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

                # Check default values
                assert "socket_path" in config
                assert "state_file" in config
                assert "log_level" in config
                assert "log_file" in config
                assert config["log_level"] == "INFO"

    def test_load_config_creates_default_config_file(self) -> None:
        """Test that load_config creates a config file with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                load_config()

                config_file = mock_config_dir / "config.yaml"
                assert config_file.exists()

                # Verify file content
                with open(config_file, "r") as f:
                    file_config = yaml.safe_load(f)

                assert file_config["log_level"] == "INFO"

    def test_load_config_reads_existing_config_file(self) -> None:
        """Test that load_config reads from existing config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)

            config_file = mock_config_dir / "config.yaml"
            custom_config = {
                "socket_path": "/custom/socket",
                "log_level": "DEBUG",
            }

            with open(config_file, "w") as f:
                yaml.safe_dump(custom_config, f)

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

                # Check that custom values are loaded
                assert config["socket_path"] == "/custom/socket"
                assert config["log_level"] == "DEBUG"
                # Check that defaults are still present for missing keys
                assert "state_file" in config
                assert "log_file" in config

    def test_load_config_merges_user_config_with_defaults(self) -> None:
        """Test that user config values override defaults but missing keys use defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)

            config_file = mock_config_dir / "config.yaml"
            # Only provide partial config
            partial_config = {
                "log_level": "WARNING",
            }

            with open(config_file, "w") as f:
                yaml.safe_dump(partial_config, f)

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

                # Custom value should override
                assert config["log_level"] == "WARNING"
                # Default values should be present
                assert config["socket_path"] == str(mock_config_dir / "socket")
                assert config["state_file"] == str(mock_config_dir / "state.json")
                assert config["log_file"] == str(mock_config_dir / "ytmpd.log")

    def test_load_config_handles_corrupted_file_gracefully(self) -> None:
        """Test that load_config falls back to defaults if config file is corrupted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)

            config_file = mock_config_dir / "config.yaml"
            # Write invalid YAML
            with open(config_file, "w") as f:
                f.write("invalid: yaml: content: [unclosed")

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

                # Should return defaults
                assert config["log_level"] == "INFO"
                assert "socket_path" in config


class TestMPDConfigFields:
    """Tests for MPD integration configuration fields."""

    def test_load_config_includes_mpd_defaults(self) -> None:
        """Test that load_config includes MPD field defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

                # Check MPD defaults are present
                assert "mpd_socket_path" in config
                assert "sync_interval_minutes" in config
                assert "enable_auto_sync" in config
                assert "playlist_prefix" in config
                assert "stream_cache_hours" in config

                # Check default values
                assert config["sync_interval_minutes"] == 30
                assert config["enable_auto_sync"] is True
                assert config["playlist_prefix"] == "YT: "
                assert config["stream_cache_hours"] == 5

    def test_mpd_socket_path_expansion(self) -> None:
        """Test that ~ is expanded in mpd_socket_path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)

            config_file = mock_config_dir / "config.yaml"
            custom_config = {
                "mpd_socket_path": "~/custom/mpd/socket",
            }

            with open(config_file, "w") as f:
                yaml.safe_dump(custom_config, f)

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

                # Check that ~ was expanded
                assert config["mpd_socket_path"] == str(
                    Path.home() / "custom" / "mpd" / "socket"
                )

    def test_sync_interval_validation_positive(self) -> None:
        """Test that sync_interval_minutes must be positive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)

            config_file = mock_config_dir / "config.yaml"
            invalid_config = {
                "sync_interval_minutes": -5,
            }

            with open(config_file, "w") as f:
                yaml.safe_dump(invalid_config, f)

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                with pytest.raises(ValueError, match="sync_interval_minutes must be a positive"):
                    load_config()

    def test_sync_interval_validation_zero(self) -> None:
        """Test that sync_interval_minutes cannot be zero."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)

            config_file = mock_config_dir / "config.yaml"
            invalid_config = {
                "sync_interval_minutes": 0,
            }

            with open(config_file, "w") as f:
                yaml.safe_dump(invalid_config, f)

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                with pytest.raises(ValueError, match="sync_interval_minutes must be a positive"):
                    load_config()

    def test_stream_cache_hours_validation_positive(self) -> None:
        """Test that stream_cache_hours must be positive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)

            config_file = mock_config_dir / "config.yaml"
            invalid_config = {
                "stream_cache_hours": -1,
            }

            with open(config_file, "w") as f:
                yaml.safe_dump(invalid_config, f)

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                with pytest.raises(ValueError, match="stream_cache_hours must be a positive"):
                    load_config()

    def test_playlist_prefix_empty_string_allowed(self) -> None:
        """Test that playlist_prefix can be an empty string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)

            config_file = mock_config_dir / "config.yaml"
            custom_config = {
                "playlist_prefix": "",
            }

            with open(config_file, "w") as f:
                yaml.safe_dump(custom_config, f)

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()
                assert config["playlist_prefix"] == ""

    def test_playlist_prefix_must_be_string(self) -> None:
        """Test that playlist_prefix must be a string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)

            config_file = mock_config_dir / "config.yaml"
            invalid_config = {
                "playlist_prefix": 123,  # Not a string
            }

            with open(config_file, "w") as f:
                yaml.safe_dump(invalid_config, f)

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                with pytest.raises(ValueError, match="playlist_prefix must be a string"):
                    load_config()

    def test_enable_auto_sync_must_be_boolean(self) -> None:
        """Test that enable_auto_sync must be a boolean."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)

            config_file = mock_config_dir / "config.yaml"
            invalid_config = {
                "enable_auto_sync": "yes",  # Not a boolean
            }

            with open(config_file, "w") as f:
                yaml.safe_dump(invalid_config, f)

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                with pytest.raises(ValueError, match="enable_auto_sync must be a boolean"):
                    load_config()

    def test_old_config_without_mpd_fields_still_loads(self) -> None:
        """Test backward compatibility: old configs without MPD fields still load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)

            config_file = mock_config_dir / "config.yaml"
            # Old config without MPD fields
            old_config = {
                "socket_path": "/old/socket",
                "log_level": "DEBUG",
            }

            with open(config_file, "w") as f:
                yaml.safe_dump(old_config, f)

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

                # Old fields preserved
                assert config["socket_path"] == "/old/socket"
                assert config["log_level"] == "DEBUG"

                # New fields use defaults
                assert config["sync_interval_minutes"] == 30
                assert config["enable_auto_sync"] is True
                assert config["playlist_prefix"] == "YT: "
                assert config["stream_cache_hours"] == 5

    def test_large_sync_interval_allowed(self) -> None:
        """Test that very large sync intervals are allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)

            config_file = mock_config_dir / "config.yaml"
            custom_config = {
                "sync_interval_minutes": 10080,  # One week
            }

            with open(config_file, "w") as f:
                yaml.safe_dump(custom_config, f)

            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()
                assert config["sync_interval_minutes"] == 10080
