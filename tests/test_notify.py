"""Tests for ytmpd.notify module."""

from unittest.mock import patch

import pytest

from ytmpd import notify
from ytmpd.notify import send_notification


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """Reset notification rate limiting state before each test."""
    notify._last_notification_time = 0.0
    yield


class TestSendNotification:
    """Tests for send_notification()."""

    @patch("ytmpd.notify.subprocess.run")
    def test_sends_notification(self, mock_run):
        """Notification is sent via notify-send."""
        result = send_notification("Title", "Body")

        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "notify-send"
        assert "--urgency" in args
        assert "normal" in args
        assert "Title" in args
        assert "Body" in args

    @patch("ytmpd.notify.subprocess.run")
    def test_custom_urgency(self, mock_run):
        """Custom urgency level is passed to notify-send."""
        send_notification("Title", "Body", urgency="critical")

        args = mock_run.call_args[0][0]
        idx = args.index("--urgency")
        assert args[idx + 1] == "critical"

    @patch("ytmpd.notify.subprocess.run")
    def test_custom_icon(self, mock_run):
        """Custom icon is passed to notify-send."""
        send_notification("Title", "Body", icon="dialog-error")

        args = mock_run.call_args[0][0]
        idx = args.index("--icon")
        assert args[idx + 1] == "dialog-error"

    @patch("ytmpd.notify.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_notify_send(self, mock_run):
        """Returns False when notify-send is not installed."""
        result = send_notification("Title", "Body")

        assert result is False

    @patch("ytmpd.notify.subprocess.run")
    def test_timeout_handling(self, mock_run):
        """notify-send is called with a timeout."""
        send_notification("Title", "Body")

        assert mock_run.call_args[1]["timeout"] == 5

    @patch("ytmpd.notify.subprocess.run", side_effect=Exception("unexpected"))
    def test_generic_exception(self, mock_run):
        """Returns False on unexpected errors."""
        result = send_notification("Title", "Body")

        assert result is False


class TestRateLimiting:
    """Tests for notification rate limiting."""

    @patch("ytmpd.notify.subprocess.run")
    def test_first_notification_sent(self, mock_run):
        """First notification is always sent."""
        result = send_notification("Title", "Body")

        assert result is True
        assert mock_run.call_count == 1

    @patch("ytmpd.notify.subprocess.run")
    def test_second_notification_rate_limited(self, mock_run):
        """Second notification within cooldown is rate-limited."""
        send_notification("Title", "Body")
        result = send_notification("Title 2", "Body 2")

        assert result is False
        assert mock_run.call_count == 1  # Only the first call

    @patch("ytmpd.notify.subprocess.run")
    @patch("ytmpd.notify.time.time")
    def test_notification_after_cooldown(self, mock_time, mock_run):
        """Notification is sent after cooldown expires."""
        mock_time.return_value = 10000.0
        send_notification("Title", "Body")

        # Advance past cooldown (3600 seconds)
        mock_time.return_value = 13601.0
        result = send_notification("Title 2", "Body 2")

        assert result is True
        assert mock_run.call_count == 2

    @patch("ytmpd.notify.subprocess.run")
    @patch("ytmpd.notify.time.time")
    def test_notification_before_cooldown_expires(self, mock_time, mock_run):
        """Notification is blocked before cooldown expires."""
        mock_time.return_value = 10000.0
        send_notification("Title", "Body")

        # Just before cooldown expires
        mock_time.return_value = 13599.0
        result = send_notification("Title 2", "Body 2")

        assert result is False
        assert mock_run.call_count == 1

    @patch("ytmpd.notify.subprocess.run", side_effect=FileNotFoundError)
    def test_failed_notification_does_not_update_timestamp(self, mock_run):
        """Failed notification does not count toward rate limiting."""
        result = send_notification("Title", "Body")
        assert result is False

        # _last_notification_time should still be 0 (from reset_rate_limit)
        assert notify._last_notification_time == 0.0
