"""Tests for history_reporting configuration validation."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from ytmpd.config import _validate_config, load_config


class TestHistoryReportingDefaults:
    """Tests for history_reporting defaults in load_config."""

    def test_defaults_include_history_reporting(self) -> None:
        """Default config has history_reporting section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

        assert "history_reporting" in config
        assert config["history_reporting"]["enabled"] is False
        assert config["history_reporting"]["min_play_seconds"] == 30

    def test_user_override_merged(self) -> None:
        """User-provided history_reporting values are merged with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)
            config_file = mock_config_dir / "config.yaml"
            config_file.write_text(yaml.dump({"history_reporting": {"enabled": True}}))
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

        assert config["history_reporting"]["enabled"] is True
        # min_play_seconds should be filled from defaults
        assert config["history_reporting"]["min_play_seconds"] == 30

    def test_missing_section_gets_defaults(self) -> None:
        """Config without history_reporting section gets populated with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            mock_config_dir.mkdir(parents=True)
            config_file = mock_config_dir / "config.yaml"
            config_file.write_text(yaml.dump({"log_level": "DEBUG"}))
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

        assert "history_reporting" in config
        assert config["history_reporting"]["enabled"] is False
        assert config["history_reporting"]["min_play_seconds"] == 30


class TestHistoryReportingValidation:
    """Tests for _validate_config history_reporting validation."""

    @staticmethod
    def _base_config() -> dict:
        """Return a minimal valid config dict."""
        return {
            "history_reporting": {
                "enabled": False,
                "min_play_seconds": 30,
            },
        }

    def test_valid_config_passes(self) -> None:
        config = self._base_config()
        result = _validate_config(config)
        assert result["history_reporting"]["enabled"] is False
        assert result["history_reporting"]["min_play_seconds"] == 30

    def test_enabled_true_passes(self) -> None:
        config = self._base_config()
        config["history_reporting"]["enabled"] = True
        result = _validate_config(config)
        assert result["history_reporting"]["enabled"] is True

    def test_enabled_non_bool_raises(self) -> None:
        config = self._base_config()
        config["history_reporting"]["enabled"] = "yes"
        with pytest.raises(ValueError, match="history_reporting.enabled must be a boolean"):
            _validate_config(config)

    def test_min_play_seconds_valid(self) -> None:
        config = self._base_config()
        config["history_reporting"]["min_play_seconds"] = 60
        result = _validate_config(config)
        assert result["history_reporting"]["min_play_seconds"] == 60

    def test_min_play_seconds_minimum_boundary(self) -> None:
        config = self._base_config()
        config["history_reporting"]["min_play_seconds"] = 5
        result = _validate_config(config)
        assert result["history_reporting"]["min_play_seconds"] == 5

    def test_min_play_seconds_below_minimum_raises(self) -> None:
        config = self._base_config()
        config["history_reporting"]["min_play_seconds"] = 4
        with pytest.raises(ValueError, match="min_play_seconds must be an integer >= 5"):
            _validate_config(config)

    def test_min_play_seconds_zero_raises(self) -> None:
        config = self._base_config()
        config["history_reporting"]["min_play_seconds"] = 0
        with pytest.raises(ValueError, match="min_play_seconds must be an integer >= 5"):
            _validate_config(config)

    def test_min_play_seconds_negative_raises(self) -> None:
        config = self._base_config()
        config["history_reporting"]["min_play_seconds"] = -1
        with pytest.raises(ValueError, match="min_play_seconds must be an integer >= 5"):
            _validate_config(config)

    def test_min_play_seconds_float_raises(self) -> None:
        config = self._base_config()
        config["history_reporting"]["min_play_seconds"] = 30.5
        with pytest.raises(ValueError, match="min_play_seconds must be an integer >= 5"):
            _validate_config(config)

    def test_min_play_seconds_string_raises(self) -> None:
        config = self._base_config()
        config["history_reporting"]["min_play_seconds"] = "30"
        with pytest.raises(ValueError, match="min_play_seconds must be an integer >= 5"):
            _validate_config(config)

    def test_non_dict_history_reporting_raises(self) -> None:
        config = {"history_reporting": "invalid"}
        with pytest.raises(ValueError, match="history_reporting must be a mapping"):
            _validate_config(config)

    def test_low_min_play_seconds_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """min_play_seconds between 5 and 9 logs a warning."""
        config = self._base_config()
        config["history_reporting"]["min_play_seconds"] = 7
        _validate_config(config)
        assert "very low" in caplog.text
