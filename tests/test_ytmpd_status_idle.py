"""Tests for ytmpd-status idle mode, signal handling, and i3blocks integration."""

import importlib.machinery
import importlib.util
import os
import signal
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

# Load the ytmpd-status script as a module
script_path = Path(__file__).parent.parent / "bin" / "ytmpd-status"
spec = importlib.util.spec_from_file_location(
    "ytmpd_status_idle_tests",
    script_path,
    loader=importlib.machinery.SourceFileLoader("ytmpd_status_idle_tests", str(script_path))
)
ytmpd_status_idle = importlib.util.module_from_spec(spec)
sys.modules["ytmpd_status_idle_tests"] = ytmpd_status_idle
spec.loader.exec_module(ytmpd_status_idle)


class TestSignalHandlers:
    """Test signal handling for idle mode."""

    def test_signal_handler_refresh(self):
        """Test SIGUSR1 signal sets refresh flag."""
        # Reset global flags
        ytmpd_status_idle.should_refresh = False
        ytmpd_status_idle.should_exit = False

        # Call signal handler
        ytmpd_status_idle.signal_handler_refresh(signal.SIGUSR1, None)

        assert ytmpd_status_idle.should_refresh is True
        assert ytmpd_status_idle.should_exit is False

    def test_signal_handler_exit_sigterm(self):
        """Test SIGTERM signal sets exit flag."""
        # Reset global flags
        ytmpd_status_idle.should_refresh = False
        ytmpd_status_idle.should_exit = False

        # Call signal handler
        ytmpd_status_idle.signal_handler_exit(signal.SIGTERM, None)

        assert ytmpd_status_idle.should_refresh is False
        assert ytmpd_status_idle.should_exit is True

    def test_signal_handler_exit_sigint(self):
        """Test SIGINT signal sets exit flag."""
        # Reset global flags
        ytmpd_status_idle.should_refresh = False
        ytmpd_status_idle.should_exit = False

        # Call signal handler
        ytmpd_status_idle.signal_handler_exit(signal.SIGINT, None)

        assert ytmpd_status_idle.should_refresh is False
        assert ytmpd_status_idle.should_exit is True

    def test_refresh_flag_resets_after_use(self):
        """Test that refresh flag can be reset."""
        ytmpd_status_idle.should_refresh = True
        ytmpd_status_idle.should_refresh = False
        assert ytmpd_status_idle.should_refresh is False


class TestClickHandlers:
    """Test i3blocks click handler functionality."""

    def test_handle_click_no_button(self):
        """Test handle_click returns False when no BLOCK_BUTTON set."""
        mock_client = MagicMock()

        with patch.dict(os.environ, {}, clear=True):
            result = ytmpd_status_idle.handle_click(mock_client)

        assert result is False
        mock_client.assert_not_called()

    def test_handle_click_left_click_play(self):
        """Test left click (button 1) toggles to pause when playing."""
        mock_client = MagicMock()
        mock_client.status.return_value = {"state": "play"}

        with patch.dict(os.environ, {"BLOCK_BUTTON": "1"}):
            result = ytmpd_status_idle.handle_click(mock_client)

        assert result is True
        mock_client.status.assert_called_once()
        mock_client.pause.assert_called_once_with(1)

    def test_handle_click_left_click_pause(self):
        """Test left click (button 1) toggles to play when paused."""
        mock_client = MagicMock()
        mock_client.status.return_value = {"state": "pause"}

        with patch.dict(os.environ, {"BLOCK_BUTTON": "1"}):
            result = ytmpd_status_idle.handle_click(mock_client)

        assert result is True
        mock_client.status.assert_called_once()
        mock_client.pause.assert_called_once_with(0)

    def test_handle_click_left_click_stopped(self):
        """Test left click (button 1) plays when stopped."""
        mock_client = MagicMock()
        mock_client.status.return_value = {"state": "stop"}

        with patch.dict(os.environ, {"BLOCK_BUTTON": "1"}):
            result = ytmpd_status_idle.handle_click(mock_client)

        assert result is True
        mock_client.status.assert_called_once()
        mock_client.play.assert_called_once()

    def test_handle_click_middle_click(self):
        """Test middle click (button 2) stops playback."""
        mock_client = MagicMock()

        with patch.dict(os.environ, {"BLOCK_BUTTON": "2"}):
            result = ytmpd_status_idle.handle_click(mock_client)

        assert result is True
        mock_client.stop.assert_called_once()

    def test_handle_click_right_click(self):
        """Test right click (button 3) is reserved (no-op)."""
        mock_client = MagicMock()

        with patch.dict(os.environ, {"BLOCK_BUTTON": "3"}):
            result = ytmpd_status_idle.handle_click(mock_client)

        # Should return False since right click is not implemented
        assert result is False

    def test_handle_click_scroll_up(self):
        """Test scroll up (button 4) goes to next track."""
        mock_client = MagicMock()

        with patch.dict(os.environ, {"BLOCK_BUTTON": "4"}):
            result = ytmpd_status_idle.handle_click(mock_client)

        assert result is True
        mock_client.next.assert_called_once()

    def test_handle_click_scroll_down(self):
        """Test scroll down (button 5) goes to previous track."""
        mock_client = MagicMock()

        with patch.dict(os.environ, {"BLOCK_BUTTON": "5"}):
            result = ytmpd_status_idle.handle_click(mock_client)

        assert result is True
        mock_client.previous.assert_called_once()

    def test_handle_click_invalid_button(self):
        """Test invalid button number is ignored."""
        mock_client = MagicMock()

        with patch.dict(os.environ, {"BLOCK_BUTTON": "99"}):
            result = ytmpd_status_idle.handle_click(mock_client)

        assert result is False

    def test_handle_click_exception(self):
        """Test exception handling in click handler."""
        mock_client = MagicMock()
        mock_client.stop.side_effect = Exception("MPD error")

        with patch.dict(os.environ, {"BLOCK_BUTTON": "2"}):
            result = ytmpd_status_idle.handle_click(mock_client)

        assert result is False

    def test_handle_click_verbose(self, capsys):
        """Test verbose output in click handler."""
        mock_client = MagicMock()

        with patch.dict(os.environ, {"BLOCK_BUTTON": "2"}):
            ytmpd_status_idle.handle_click(mock_client, verbose=True)

        captured = capsys.readouterr()
        assert "Handling click: button 2" in captured.err


class TestDisplayStatus:
    """Test display_status function."""

    @patch("ytmpd_status_idle_tests.get_track_type")
    @patch("ytmpd_status_idle_tests.get_playlist_context")
    @patch("ytmpd_status_idle_tests.get_sync_status")
    @patch("ytmpd_status_idle_tests.smart_truncate")
    def test_display_status_playing(
        self, mock_truncate, mock_sync, mock_playlist, mock_track_type, capsys
    ):
        """Test display_status with playing track."""
        # Setup mocks
        mock_client = MagicMock()
        mock_client.status.return_value = {
            "state": "play",
            "elapsed": "120.5",
        }
        mock_client.currentsong.return_value = {
            "title": "Test Song",
            "artist": "Test Artist",
            "file": "test.mp3",
            "time": "300",
        }
        mock_track_type.return_value = "local"
        mock_playlist.return_value = {
            "position": 1,
            "total": 10,
            "next": None,
            "prev": None,
        }
        mock_sync.return_value = "resolved"
        mock_truncate.side_effect = lambda x, _: x  # Return unchanged

        # Create mock args
        mock_args = MagicMock()
        mock_args.icon_playing = "▶"
        mock_args.icon_paused = "⏸"
        mock_args.icon_stopped = "⏹"
        mock_args.color_local_playing = "#00FF00"
        mock_args.color_local_paused = "#FFFF00"
        mock_args.color_youtube_playing = "#FF6B35"
        mock_args.color_youtube_paused = "#FFB84D"
        mock_args.color_stopped = "#808080"
        mock_args.max_length = 50
        mock_args.bar_length = 10
        mock_args.show_bar = True
        mock_args.bar_style = ""
        mock_args.show_next = False
        mock_args.show_prev = False
        mock_args.compact = False
        mock_args.format = ""

        # Call function
        ytmpd_status_idle.display_status(mock_client, mock_args)

        # Check output
        captured = capsys.readouterr()
        assert "▶ Test Artist - Test Song" in captured.out
        assert "#00FF00" in captured.out

    @patch("ytmpd_status_idle_tests.get_track_type")
    @patch("ytmpd_status_idle_tests.get_playlist_context")
    @patch("ytmpd_status_idle_tests.get_sync_status")
    @patch("ytmpd_status_idle_tests.smart_truncate")
    def test_display_status_stopped(
        self, mock_truncate, mock_sync, mock_playlist, mock_track_type, capsys
    ):
        """Test display_status when stopped."""
        mock_client = MagicMock()
        mock_client.status.return_value = {"state": "stop"}
        mock_client.currentsong.return_value = {}

        mock_args = MagicMock()
        mock_args.icon_stopped = "⏹"
        mock_args.color_stopped = "#808080"

        ytmpd_status_idle.display_status(mock_client, mock_args)

        captured = capsys.readouterr()
        assert "⏹ Stopped" in captured.out
        assert "#808080" in captured.out

    @patch("ytmpd_status_idle_tests.get_track_type")
    @patch("ytmpd_status_idle_tests.get_playlist_context")
    @patch("ytmpd_status_idle_tests.get_sync_status")
    def test_display_status_exception(
        self, mock_sync, mock_playlist, mock_track_type, capsys
    ):
        """Test display_status handles exceptions gracefully."""
        mock_client = MagicMock()
        mock_client.status.side_effect = Exception("Test error")

        mock_args = MagicMock()
        mock_args.icon_stopped = "⏹"
        mock_args.color_stopped = "#808080"

        ytmpd_status_idle.display_status(mock_client, mock_args)

        captured = capsys.readouterr()
        assert "Error" in captured.out


class TestIdleMode:
    """Test idle mode functionality."""

    @patch("ytmpd_status_idle_tests.signal.signal")
    @patch("ytmpd_status_idle_tests.get_mpd_client")
    @patch("ytmpd_status_idle_tests.display_status")
    @patch("ytmpd_status_idle_tests.time.sleep")
    def test_run_idle_mode_basic(
        self, mock_sleep, mock_display, mock_get_client, mock_signal
    ):
        """Test basic idle mode operation."""
        # Setup mocks
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Make idle() return once then trigger exit
        def idle_side_effect(*args):
            ytmpd_status_idle.should_exit = True
            return ["player"]

        mock_client.idle.side_effect = idle_side_effect

        mock_args = MagicMock()
        mock_args.host = "localhost"
        mock_args.port = 6601
        mock_args.verbose = False
        mock_args.handle_clicks = False

        # Reset flags
        ytmpd_status_idle.should_refresh = False
        ytmpd_status_idle.should_exit = False

        # Run
        ytmpd_status_idle.run_idle_mode(mock_args)

        # Verify
        mock_signal.assert_any_call(signal.SIGUSR1, ytmpd_status_idle.signal_handler_refresh)
        mock_signal.assert_any_call(signal.SIGTERM, ytmpd_status_idle.signal_handler_exit)
        mock_signal.assert_any_call(signal.SIGINT, ytmpd_status_idle.signal_handler_exit)
        mock_get_client.assert_called()
        mock_display.assert_called()
        mock_client.idle.assert_called_once_with(["player"])
        mock_client.close.assert_called_once()

    @patch("ytmpd_status_idle_tests.signal.signal")
    @patch("ytmpd_status_idle_tests.get_mpd_client")
    @patch("ytmpd_status_idle_tests.display_status")
    @patch("ytmpd_status_idle_tests.time.sleep")
    def test_run_idle_mode_connection_retry(
        self, mock_sleep, mock_display, mock_get_client, mock_signal
    ):
        """Test idle mode retries connection on failure."""
        # Setup mocks - fail once, then succeed, then exit
        call_count = [0]

        def get_client_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # First call fails
            else:
                mock_client = MagicMock()

                def idle_side_effect(*args):
                    ytmpd_status_idle.should_exit = True
                    return ["player"]

                mock_client.idle.side_effect = idle_side_effect
                return mock_client

        mock_get_client.side_effect = get_client_side_effect

        mock_args = MagicMock()
        mock_args.host = "localhost"
        mock_args.port = 6601
        mock_args.verbose = False
        mock_args.handle_clicks = False

        # Reset flags
        ytmpd_status_idle.should_refresh = False
        ytmpd_status_idle.should_exit = False

        # Run
        ytmpd_status_idle.run_idle_mode(mock_args)

        # Verify it retried
        assert mock_get_client.call_count >= 2
        mock_sleep.assert_called()

    @patch("ytmpd_status_idle_tests.signal.signal")
    @patch("ytmpd_status_idle_tests.get_mpd_client")
    @patch("ytmpd_status_idle_tests.display_status")
    @patch("ytmpd_status_idle_tests.handle_click")
    @patch.dict(os.environ, {"BLOCK_BUTTON": "1"})
    def test_run_idle_mode_handle_clicks(
        self, mock_handle_click, mock_display, mock_get_client, mock_signal
    ):
        """Test idle mode handles click events."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Setup click handler to trigger once then exit
        call_count = [0]

        def click_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return True  # First call handles click
            else:
                ytmpd_status_idle.should_exit = True
                return False

        mock_handle_click.side_effect = click_side_effect

        mock_args = MagicMock()
        mock_args.host = "localhost"
        mock_args.port = 6601
        mock_args.verbose = False
        mock_args.handle_clicks = True

        # Reset flags
        ytmpd_status_idle.should_refresh = False
        ytmpd_status_idle.should_exit = False

        # Run
        ytmpd_status_idle.run_idle_mode(mock_args)

        # Verify click was handled
        mock_handle_click.assert_called()
        mock_display.assert_called()

    @patch("ytmpd_status_idle_tests.signal.signal")
    @patch("ytmpd_status_idle_tests.get_mpd_client")
    @patch("ytmpd_status_idle_tests.display_status")
    def test_run_idle_mode_manual_refresh(
        self, mock_display, mock_get_client, mock_signal
    ):
        """Test idle mode responds to manual refresh signal."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Setup to trigger manual refresh then exit
        call_count = [0]

        def display_side_effect(*args):
            call_count[0] += 1
            if call_count[0] == 1:
                # After first display, set refresh flag
                ytmpd_status_idle.should_refresh = True
            elif call_count[0] == 2:
                # After refresh display, exit
                ytmpd_status_idle.should_exit = True

        mock_display.side_effect = display_side_effect

        mock_args = MagicMock()
        mock_args.host = "localhost"
        mock_args.port = 6601
        mock_args.verbose = False
        mock_args.handle_clicks = False

        # Reset flags
        ytmpd_status_idle.should_refresh = False
        ytmpd_status_idle.should_exit = False

        # Run
        ytmpd_status_idle.run_idle_mode(mock_args)

        # Verify display was called at least twice
        assert mock_display.call_count >= 2


class TestArgumentParsing:
    """Test argument parsing for idle mode options."""

    @patch("sys.argv", ["ytmpd-status"])
    def test_parse_arguments_no_idle(self):
        """Test default (no idle mode)."""
        args = ytmpd_status_idle.parse_arguments()
        assert args.idle is False
        assert args.handle_clicks is False

    @patch("sys.argv", ["ytmpd-status", "--idle"])
    def test_parse_arguments_idle(self):
        """Test --idle flag."""
        args = ytmpd_status_idle.parse_arguments()
        assert args.idle is True

    @patch("sys.argv", ["ytmpd-status", "--handle-clicks"])
    def test_parse_arguments_handle_clicks(self):
        """Test --handle-clicks flag."""
        args = ytmpd_status_idle.parse_arguments()
        assert args.handle_clicks is True

    @patch("sys.argv", ["ytmpd-status", "--idle", "--handle-clicks"])
    def test_parse_arguments_both(self):
        """Test both flags together."""
        args = ytmpd_status_idle.parse_arguments()
        assert args.idle is True
        assert args.handle_clicks is True
