"""Desktop notification helper for ytmpd.

Sends notifications via notify-send when auto-auth refresh fails,
with rate limiting to prevent spam.
"""

import logging
import subprocess
import time

logger = logging.getLogger(__name__)

# Module-level rate limiting state
_last_notification_time: float = 0.0
_notification_cooldown: float = 3600.0  # 1 hour


def send_notification(
    title: str,
    message: str,
    urgency: str = "normal",
    icon: str = "dialog-warning",
) -> bool:
    """Send desktop notification via notify-send.

    Notifications are rate-limited to a maximum of one per hour to avoid spam.

    Args:
        title: Notification title.
        message: Notification body text.
        urgency: Urgency level ("low", "normal", or "critical").
        icon: Icon name for the notification.

    Returns:
        True if notification was sent, False if rate-limited, failed, or
        notify-send is not available.
    """
    global _last_notification_time

    # Rate limiting
    now = time.time()
    if now - _last_notification_time < _notification_cooldown:
        logger.debug("Notification rate-limited (max 1 per hour)")
        return False

    try:
        subprocess.run(
            [
                "notify-send",
                "--urgency",
                urgency,
                "--icon",
                icon,
                "--app-name",
                "ytmpd",
                title,
                message,
            ],
            timeout=5,
            capture_output=True,
        )
        _last_notification_time = now
        logger.info("Desktop notification sent: %s", title)
        return True
    except FileNotFoundError:
        logger.warning("notify-send not found; desktop notifications unavailable")
        return False
    except subprocess.TimeoutExpired:
        logger.warning("notify-send timed out")
        return False
    except Exception as e:
        logger.warning("Failed to send notification: %s", e)
        return False
