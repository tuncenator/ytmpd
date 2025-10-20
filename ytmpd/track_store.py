"""Track metadata storage for ICY proxy server.

This module provides a SQLite-backed storage system for tracking video metadata,
including YouTube stream URLs, artist names, and track titles. The store is used
by the ICY proxy server to lookup metadata when serving proxied streams to MPD.
"""

import sqlite3
import time
from pathlib import Path
from typing import Any


class TrackStore:
    """Manages persistent storage of track metadata using SQLite.

    The store maintains a mapping from YouTube video IDs to their metadata,
    including the current stream URL (which expires), artist, and title.

    Schema:
        - video_id (TEXT PRIMARY KEY): YouTube video ID
        - stream_url (TEXT): Current YouTube stream URL (nullable for lazy resolution)
        - artist (TEXT): Track artist name (nullable)
        - title (TEXT NOT NULL): Track title
        - updated_at (REAL): Unix timestamp of last update

    Example:
        >>> store = TrackStore("~/.config/ytmpd/track_mapping.db")
        >>> store.add_track(
        ...     video_id="dQw4w9WgXcQ",
        ...     stream_url="https://youtube.com/watch?v=...",
        ...     title="Never Gonna Give You Up",
        ...     artist="Rick Astley"
        ... )
        >>> track = store.get_track("dQw4w9WgXcQ")
        >>> print(f"{track['artist']} - {track['title']}")
        Rick Astley - Never Gonna Give You Up
    """

    def __init__(self, db_path: str) -> None:
        """Initialize database connection and create schema if needed.

        Args:
            db_path: Path to SQLite database file. Parent directories will be
                    created if they don't exist. Use ':memory:' for in-memory
                    database (useful for testing).
        """
        # Expand user home directory and create parent directories
        if db_path != ":memory:":
            db_file = Path(db_path).expanduser()
            db_file.parent.mkdir(parents=True, exist_ok=True)
            self.db_path = str(db_file)
        else:
            self.db_path = db_path

        # Allow multi-threaded access (proxy server runs in async thread)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Enable dict-like access
        self._create_schema()

    def _create_schema(self) -> None:
        """Create database schema if it doesn't exist.

        Note: stream_url is nullable to support lazy resolution where URLs
        are resolved on-demand by the proxy server rather than during sync.
        """
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    video_id TEXT PRIMARY KEY,
                    stream_url TEXT,
                    artist TEXT,
                    title TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            # Create index on updated_at for potential cleanup queries
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tracks_updated_at
                ON tracks(updated_at)
            """)

    def add_track(
        self,
        video_id: str,
        stream_url: str | None,
        title: str,
        artist: str | None = None
    ) -> None:
        """Add or update a track in the database.

        If a track with the given video_id already exists, it will be updated
        with the new values. This is useful for refreshing expired stream URLs.

        Args:
            video_id: YouTube video ID (e.g., "dQw4w9WgXcQ")
            stream_url: Current YouTube stream URL, or None for lazy resolution
            title: Track title
            artist: Track artist name (optional)

        Raises:
            sqlite3.Error: If database operation fails

        Note:
            When stream_url is None, the track is saved with metadata only.
            The proxy server will resolve the URL on-demand when the track is played.
        """
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO tracks (video_id, stream_url, artist, title, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    stream_url = excluded.stream_url,
                    artist = excluded.artist,
                    title = excluded.title,
                    updated_at = excluded.updated_at
                """,
                (video_id, stream_url, artist, title, time.time())
            )

    def get_track(self, video_id: str) -> dict[str, Any] | None:
        """Retrieve track metadata by video_id.

        Args:
            video_id: YouTube video ID to lookup

        Returns:
            Dictionary containing track metadata with keys:
                - video_id (str)
                - stream_url (str)
                - artist (str | None)
                - title (str)
                - updated_at (float)
            Returns None if video_id not found in database.

        Example:
            >>> track = store.get_track("dQw4w9WgXcQ")
            >>> if track:
            ...     print(f"{track['artist']} - {track['title']}")
        """
        cursor = self.conn.execute(
            "SELECT * FROM tracks WHERE video_id = ?",
            (video_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_stream_url(self, video_id: str, stream_url: str) -> None:
        """Update the stream URL for an existing track.

        This is useful for refreshing expired YouTube stream URLs without
        modifying other track metadata.

        Args:
            video_id: YouTube video ID of the track to update
            stream_url: New YouTube stream URL

        Raises:
            sqlite3.Error: If database operation fails

        Note:
            This method will succeed even if the video_id doesn't exist in
            the database (no rows will be affected). Use get_track() first
            to check if a track exists.
        """
        with self.conn:
            self.conn.execute(
                """
                UPDATE tracks
                SET stream_url = ?, updated_at = ?
                WHERE video_id = ?
                """,
                (stream_url, time.time(), video_id)
            )

    def close(self) -> None:
        """Close database connection.

        Should be called when the TrackStore is no longer needed to ensure
        proper cleanup of database resources.
        """
        self.conn.close()

    def __enter__(self) -> "TrackStore":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - closes database connection."""
        self.close()
