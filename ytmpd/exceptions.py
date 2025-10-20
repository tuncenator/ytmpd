"""Custom exceptions for ytmpd.

This module defines custom exception classes used throughout the ytmpd application
for better error handling and debugging.
"""


class YTMPDError(Exception):
    """Base exception for all ytmpd errors."""

    pass


class YTMusicAuthError(YTMPDError):
    """Raised when YouTube Music authentication fails."""

    pass


class YTMusicAPIError(YTMPDError):
    """Raised when a YouTube Music API call fails."""

    pass


class YTMusicNotFoundError(YTMPDError):
    """Raised when a requested resource is not found in YouTube Music."""

    pass


class ConfigError(YTMPDError):
    """Raised when configuration is invalid or cannot be loaded."""

    pass


class PlayerError(YTMPDError):
    """Raised when player operations fail."""

    pass


class ServerError(YTMPDError):
    """Raised when socket server operations fail."""

    pass


class MPDConnectionError(YTMPDError):
    """Raised when connection to MPD fails."""

    pass


class MPDPlaylistError(YTMPDError):
    """Raised when MPD playlist operations fail."""

    pass


class ProxyError(YTMPDError):
    """Base exception for proxy errors."""

    pass


class YouTubeStreamError(ProxyError):
    """Raised when YouTube stream fetch fails."""

    pass


class TrackNotFoundError(ProxyError):
    """Raised when track not found in store."""

    pass


class URLRefreshError(ProxyError):
    """Raised when URL refresh fails."""

    pass
