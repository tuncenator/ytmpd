"""Tests for ytmpd-status CLI argument parsing and configuration."""

import argparse
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Load ytmpd-status script as a module
# We need to do this because the script doesn't have a .py extension
# Use a unique module name to avoid conflicts with other test files
_script_path = Path(__file__).parent.parent / "bin" / "ytmpd-status"
_ytmpd_status_code = _script_path.read_text()

# Create a module object with unique name for CLI tests
import types
ytmpd_status = types.ModuleType("ytmpd_status_cli_tests")
ytmpd_status.__file__ = str(_script_path)

# Execute the script code in the module's namespace
exec(_ytmpd_status_code, ytmpd_status.__dict__)

# Add to sys.modules so imports work correctly
sys.modules["ytmpd_status_cli_tests"] = ytmpd_status


class TestArgumentParsing:
    """Test CLI argument parsing."""

    def test_parse_args_defaults(self):
        """Test default argument values."""
        with patch("sys.argv", ["ytmpd-status"]):
            args = ytmpd_status.parse_arguments()

            # Connection defaults
            assert args.host == "localhost"
            assert args.port == 6601

            # Display defaults
            assert args.max_length == 50
            assert args.format == ""
            assert args.compact is False

            # Progress bar defaults
            assert args.show_bar is True
            assert args.bar_length == 10
            assert args.bar_style == ""  # auto becomes empty string

            # Playlist defaults
            assert args.show_next is False
            assert args.show_prev is False
            assert args.show_position is False

            # Color defaults
            assert args.color_youtube_playing == "#FF6B35"
            assert args.color_youtube_paused == "#FFB84D"
            assert args.color_local_playing == "#00FF00"
            assert args.color_local_paused == "#FFFF00"
            assert args.color_stopped == "#808080"

            # Icon defaults
            assert args.icon_playing == "▶"
            assert args.icon_paused == "⏸"
            assert args.icon_stopped == "⏹"

            # Debug defaults
            assert args.verbose is False

    def test_parse_args_connection_options(self):
        """Test connection option parsing."""
        with patch("sys.argv", ["ytmpd-status", "--host", "example.com", "--port", "6600"]):
            args = ytmpd_status.parse_arguments()
            assert args.host == "example.com"
            assert args.port == 6600

    def test_parse_args_display_options(self):
        """Test display option parsing."""
        with patch("sys.argv", ["ytmpd-status", "-l", "80", "-f", "{icon} {title}", "-c"]):
            args = ytmpd_status.parse_arguments()
            assert args.max_length == 80
            assert args.format == "{icon} {title}"
            assert args.compact is True

    def test_parse_args_progress_bar_options(self):
        """Test progress bar option parsing."""
        with patch("sys.argv", ["ytmpd-status", "--no-show-bar", "--bar-length", "15", "--bar-style", "blocks"]):
            args = ytmpd_status.parse_arguments()
            assert args.show_bar is False
            assert args.bar_length == 15
            assert args.bar_style == "blocks"

    def test_parse_args_show_bar_flag(self):
        """Test --show-bar explicitly enables bar."""
        with patch("sys.argv", ["ytmpd-status", "--show-bar"]):
            args = ytmpd_status.parse_arguments()
            assert args.show_bar is True

    def test_parse_args_playlist_options(self):
        """Test playlist context option parsing."""
        with patch("sys.argv", ["ytmpd-status", "--show-next", "--show-prev", "--show-position"]):
            args = ytmpd_status.parse_arguments()
            assert args.show_next is True
            assert args.show_prev is True
            assert args.show_position is True

    def test_parse_args_color_options(self):
        """Test custom color option parsing."""
        with patch(
            "sys.argv",
            [
                "ytmpd-status",
                "--color-youtube-playing", "#FF0000",
                "--color-youtube-paused", "#FF00FF",
                "--color-local-playing", "#00FFFF",
                "--color-local-paused", "#FFFF00",
                "--color-stopped", "#000000",
            ],
        ):
            args = ytmpd_status.parse_arguments()
            assert args.color_youtube_playing == "#FF0000"
            assert args.color_youtube_paused == "#FF00FF"
            assert args.color_local_playing == "#00FFFF"
            assert args.color_local_paused == "#FFFF00"
            assert args.color_stopped == "#000000"

    def test_parse_args_icon_options(self):
        """Test custom icon option parsing."""
        with patch(
            "sys.argv",
            [
                "ytmpd-status",
                "--icon-playing", "►",
                "--icon-paused", "||",
                "--icon-stopped", "■",
            ],
        ):
            args = ytmpd_status.parse_arguments()
            assert args.icon_playing == "►"
            assert args.icon_paused == "||"
            assert args.icon_stopped == "■"

    def test_parse_args_verbose_flag(self):
        """Test verbose flag."""
        with patch("sys.argv", ["ytmpd-status", "-v"]):
            args = ytmpd_status.parse_arguments()
            assert args.verbose is True


class TestEnvironmentVariableCompatibility:
    """Test backward compatibility with environment variables."""

    def test_env_var_max_length(self):
        """Test YTMPD_STATUS_MAX_LENGTH environment variable."""
        with patch.dict(os.environ, {"YTMPD_STATUS_MAX_LENGTH": "100"}):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.max_length == 100

    def test_env_var_bar_length(self):
        """Test YTMPD_STATUS_BAR_LENGTH environment variable."""
        with patch.dict(os.environ, {"YTMPD_STATUS_BAR_LENGTH": "20"}):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.bar_length == 20

    def test_env_var_show_bar_true(self):
        """Test YTMPD_STATUS_SHOW_BAR=true."""
        with patch.dict(os.environ, {"YTMPD_STATUS_SHOW_BAR": "true"}):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.show_bar is True

    def test_env_var_show_bar_false(self):
        """Test YTMPD_STATUS_SHOW_BAR=false."""
        with patch.dict(os.environ, {"YTMPD_STATUS_SHOW_BAR": "false"}):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.show_bar is False

    def test_env_var_bar_style(self):
        """Test YTMPD_STATUS_BAR_STYLE environment variable."""
        with patch.dict(os.environ, {"YTMPD_STATUS_BAR_STYLE": "smooth"}):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.bar_style == "smooth"

    def test_env_var_show_next(self):
        """Test YTMPD_STATUS_SHOW_NEXT environment variable."""
        with patch.dict(os.environ, {"YTMPD_STATUS_SHOW_NEXT": "true"}):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.show_next is True

    def test_env_var_show_prev(self):
        """Test YTMPD_STATUS_SHOW_PREV environment variable."""
        with patch.dict(os.environ, {"YTMPD_STATUS_SHOW_PREV": "1"}):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.show_prev is True

    def test_env_var_compact(self):
        """Test YTMPD_STATUS_COMPACT environment variable."""
        with patch.dict(os.environ, {"YTMPD_STATUS_COMPACT": "yes"}):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.compact is True

    def test_env_var_format(self):
        """Test YTMPD_STATUS_FORMAT environment variable."""
        with patch.dict(os.environ, {"YTMPD_STATUS_FORMAT": "{icon} {artist}"}):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.format == "{icon} {artist}"

    def test_env_var_colors(self):
        """Test color environment variables."""
        with patch.dict(
            os.environ,
            {
                "YTMPD_STATUS_COLOR_YOUTUBE_PLAYING": "#AABBCC",
                "YTMPD_STATUS_COLOR_STOPPED": "#112233",
            },
        ):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.color_youtube_playing == "#AABBCC"
                assert args.color_stopped == "#112233"

    def test_env_var_icons(self):
        """Test icon environment variables."""
        with patch.dict(
            os.environ,
            {
                "YTMPD_STATUS_ICON_PLAYING": "►",
                "YTMPD_STATUS_ICON_PAUSED": "P",
            },
        ):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.icon_playing == "►"
                assert args.icon_paused == "P"


class TestPriorityOrder:
    """Test that CLI args override environment variables."""

    def test_cli_overrides_env_max_length(self):
        """CLI --max-length should override YTMPD_STATUS_MAX_LENGTH."""
        with patch.dict(os.environ, {"YTMPD_STATUS_MAX_LENGTH": "100"}):
            with patch("sys.argv", ["ytmpd-status", "--max-length", "80"]):
                args = ytmpd_status.parse_arguments()
                assert args.max_length == 80

    def test_cli_overrides_env_bar_length(self):
        """CLI --bar-length should override YTMPD_STATUS_BAR_LENGTH."""
        with patch.dict(os.environ, {"YTMPD_STATUS_BAR_LENGTH": "20"}):
            with patch("sys.argv", ["ytmpd-status", "--bar-length", "15"]):
                args = ytmpd_status.parse_arguments()
                assert args.bar_length == 15

    def test_cli_overrides_env_show_bar(self):
        """CLI --no-show-bar should override YTMPD_STATUS_SHOW_BAR=true."""
        with patch.dict(os.environ, {"YTMPD_STATUS_SHOW_BAR": "true"}):
            with patch("sys.argv", ["ytmpd-status", "--no-show-bar"]):
                args = ytmpd_status.parse_arguments()
                assert args.show_bar is False

    def test_cli_overrides_env_compact(self):
        """CLI --compact should override YTMPD_STATUS_COMPACT=false."""
        with patch.dict(os.environ, {"YTMPD_STATUS_COMPACT": "false"}):
            with patch("sys.argv", ["ytmpd-status", "--compact"]):
                args = ytmpd_status.parse_arguments()
                assert args.compact is True

    def test_cli_overrides_env_format(self):
        """CLI --format should override YTMPD_STATUS_FORMAT."""
        with patch.dict(os.environ, {"YTMPD_STATUS_FORMAT": "{icon} {artist}"}):
            with patch("sys.argv", ["ytmpd-status", "--format", "{title}"]):
                args = ytmpd_status.parse_arguments()
                assert args.format == "{title}"

    def test_cli_overrides_env_color(self):
        """CLI color args should override env vars."""
        with patch.dict(os.environ, {"YTMPD_STATUS_COLOR_YOUTUBE_PLAYING": "#000000"}):
            with patch("sys.argv", ["ytmpd-status", "--color-youtube-playing", "#FFFFFF"]):
                args = ytmpd_status.parse_arguments()
                assert args.color_youtube_playing == "#FFFFFF"


class TestValidation:
    """Test configuration validation."""

    def test_validate_port_valid(self):
        """Test valid port numbers."""
        assert ytmpd_status.validate_port("1") == 1
        assert ytmpd_status.validate_port("6600") == 6600
        assert ytmpd_status.validate_port("65535") == 65535

    def test_validate_port_invalid_too_low(self):
        """Test port number too low."""
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid port"):
            ytmpd_status.validate_port("0")

    def test_validate_port_invalid_too_high(self):
        """Test port number too high."""
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid port"):
            ytmpd_status.validate_port("65536")

    def test_validate_port_invalid_not_number(self):
        """Test port not a number."""
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid port"):
            ytmpd_status.validate_port("abc")

    def test_validate_color_valid(self):
        """Test valid color formats."""
        assert ytmpd_status.validate_color("#FF6B35") == "#FF6B35"
        assert ytmpd_status.validate_color("#000000") == "#000000"
        assert ytmpd_status.validate_color("#FFFFFF") == "#FFFFFF"
        assert ytmpd_status.validate_color("#abc123") == "#abc123"

    def test_validate_color_invalid_no_hash(self):
        """Test color without # prefix."""
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid color format"):
            ytmpd_status.validate_color("FF6B35")

    def test_validate_color_invalid_too_short(self):
        """Test color string too short."""
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid color format"):
            ytmpd_status.validate_color("#FFF")

    def test_validate_color_invalid_too_long(self):
        """Test color string too long."""
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid color format"):
            ytmpd_status.validate_color("#FF6B3500")

    def test_validate_color_invalid_chars(self):
        """Test color with invalid characters."""
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid color format"):
            ytmpd_status.validate_color("#GGHHII")

    def test_validate_positive_int_valid(self):
        """Test valid positive integers."""
        assert ytmpd_status.validate_positive_int("10", 1, 50, "test") == 10
        assert ytmpd_status.validate_positive_int("1", 1, 50, "test") == 1
        assert ytmpd_status.validate_positive_int("50", 1, 50, "test") == 50

    def test_validate_positive_int_too_low(self):
        """Test value below minimum."""
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid test"):
            ytmpd_status.validate_positive_int("0", 1, 50, "test")

    def test_validate_positive_int_too_high(self):
        """Test value above maximum."""
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid test"):
            ytmpd_status.validate_positive_int("51", 1, 50, "test")

    def test_validate_positive_int_not_number(self):
        """Test non-numeric value."""
        with pytest.raises(argparse.ArgumentTypeError, match="Invalid test"):
            ytmpd_status.validate_positive_int("abc", 1, 50, "test")

    def test_parse_args_invalid_max_length(self):
        """Test max-length out of range."""
        with patch("sys.argv", ["ytmpd-status", "--max-length", "250"]):
            with pytest.raises(SystemExit):
                ytmpd_status.parse_arguments()

    def test_parse_args_invalid_bar_length(self):
        """Test bar-length out of range."""
        with patch("sys.argv", ["ytmpd-status", "--bar-length", "100"]):
            with pytest.raises(SystemExit):
                ytmpd_status.parse_arguments()


class TestFormatString:
    """Test format string templating."""

    def test_format_with_template_basic(self):
        """Test basic placeholder replacement."""
        template = "{icon} {artist} - {title}"
        data = {"icon": "▶", "artist": "Test Artist", "title": "Test Song"}
        result = ytmpd_status.format_with_template(template, data)
        assert result == "▶ Test Artist - Test Song"

    def test_format_with_template_time(self):
        """Test time placeholders."""
        template = "[{elapsed}/{duration}]"
        data = {"elapsed": "2:30", "duration": "5:00"}
        result = ytmpd_status.format_with_template(template, data)
        assert result == "[2:30/5:00]"

    def test_format_with_template_bar(self):
        """Test progress bar placeholder."""
        template = "{icon} {title} {bar}"
        data = {"icon": "▶", "title": "Song", "bar": "████░░░░░░"}
        result = ytmpd_status.format_with_template(template, data)
        assert result == "▶ Song ████░░░░░░"

    def test_format_with_template_missing_placeholder(self):
        """Test missing placeholder (should leave empty)."""
        template = "{icon} {artist}"
        data = {"icon": "▶", "artist": None}
        result = ytmpd_status.format_with_template(template, data)
        assert result == "▶ "

    def test_format_with_template_unused_placeholders(self):
        """Test template with placeholders not in data (unchanged)."""
        template = "{icon} {undefined}"
        data = {"icon": "▶"}
        result = ytmpd_status.format_with_template(template, data)
        assert result == "▶ {undefined}"

    def test_format_with_template_playlist_info(self):
        """Test playlist position placeholders."""
        template = "{icon} {title} [{position}/{total}]"
        data = {"icon": "▶", "title": "Song", "position": "5", "total": "25"}
        result = ytmpd_status.format_with_template(template, data)
        assert result == "▶ Song [5/25]"

    def test_format_with_template_complex(self):
        """Test complex format with multiple placeholders."""
        template = "{icon} {artist} - {title} ({album}) [{elapsed} {bar} {duration}]"
        data = {
            "icon": "▶",
            "artist": "Artist",
            "title": "Title",
            "album": "Album",
            "elapsed": "1:23",
            "duration": "4:56",
            "bar": "███░░░░░░░",
        }
        result = ytmpd_status.format_with_template(template, data)
        assert result == "▶ Artist - Title (Album) [1:23 ███░░░░░░░ 4:56]"


class TestBarStyleConversion:
    """Test bar style 'auto' conversion."""

    def test_bar_style_auto_converts_to_empty(self):
        """Test that bar_style='auto' is converted to empty string."""
        with patch("sys.argv", ["ytmpd-status", "--bar-style", "auto"]):
            args = ytmpd_status.parse_arguments()
            assert args.bar_style == ""

    def test_bar_style_explicit_not_converted(self):
        """Test that explicit bar styles are not converted."""
        for style in ["blocks", "smooth", "simple"]:
            with patch("sys.argv", ["ytmpd-status", "--bar-style", style]):
                args = ytmpd_status.parse_arguments()
                assert args.bar_style == style


class TestHostAndPort:
    """Test host and port environment variable support."""

    def test_env_var_host(self):
        """Test YTMPD_STATUS_HOST environment variable."""
        with patch.dict(os.environ, {"YTMPD_STATUS_HOST": "192.168.1.100"}):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.host == "192.168.1.100"

    def test_env_var_port(self):
        """Test YTMPD_STATUS_PORT environment variable."""
        with patch.dict(os.environ, {"YTMPD_STATUS_PORT": "6700"}):
            with patch("sys.argv", ["ytmpd-status"]):
                args = ytmpd_status.parse_arguments()
                assert args.port == 6700
