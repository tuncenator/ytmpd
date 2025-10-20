"""YouTube Music API wrapper for ytmpd.

This module provides a wrapper around ytmusicapi that handles authentication
and provides clean interfaces for search, playback, and song info retrieval.
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ytmusicapi import YTMusic

from ytmpd.config import get_config_dir
from ytmpd.exceptions import YTMusicAPIError, YTMusicAuthError, YTMusicNotFoundError

logger = logging.getLogger(__name__)


def _truncate_error(error: Exception, max_length: int = 200) -> str:
    """Truncate error message for logging to prevent massive log lines.

    Args:
        error: Exception to format.
        max_length: Maximum length of error string.

    Returns:
        Truncated error message.
    """
    error_str = str(error)
    if len(error_str) <= max_length:
        return error_str
    return error_str[:max_length] + "... (truncated)"


@dataclass
class Playlist:
    """Represents a YouTube Music playlist.

    Attributes:
        id: YouTube playlist ID.
        name: Display name of the playlist.
        track_count: Number of tracks in the playlist.
    """

    id: str
    name: str
    track_count: int


@dataclass
class Track:
    """Represents a track in a YouTube Music playlist.

    Attributes:
        video_id: YouTube video ID (e.g., "dQw4w9WgXcQ").
        title: Track title.
        artist: Artist name.
        duration_seconds: Track duration in seconds (None if unavailable).
    """

    video_id: str
    title: str
    artist: str
    duration_seconds: float | None = None


class YTMusicClient:
    """Client for interacting with YouTube Music API.

    This class wraps ytmusicapi and provides a clean interface for searching,
    retrieving song information, and handling authentication.
    """

    def __init__(self, auth_file: Path | None = None) -> None:
        """Initialize the YouTube Music client.

        Args:
            auth_file: Path to browser authentication file. If None, uses default location
                       (~/.config/ytmpd/browser.json).

        Raises:
            YTMusicAuthError: If authentication fails or credentials are invalid.
        """
        if auth_file is None:
            auth_file = get_config_dir() / "browser.json"

        self.auth_file = auth_file
        self._client: YTMusic | None = None
        self._last_request_time = 0.0
        self._min_request_interval = 0.1  # 100ms between requests (rate limiting)

        # Initialize the client
        self._init_client()

    def _init_client(self) -> None:
        """Initialize the ytmusicapi client.

        Raises:
            YTMusicAuthError: If authentication fails.
        """
        try:
            if not self.auth_file.exists():
                raise YTMusicAuthError(
                    f"Browser authentication file not found: {self.auth_file}\n"
                    f"Please run: python -m ytmpd.ytmusic setup-browser"
                )

            logger.info("Initializing YouTube Music client with browser authentication")

            # Initialize YTMusic with browser authentication file
            self._client = YTMusic(str(self.auth_file))
            logger.info("Successfully authenticated with YouTube Music")

        except YTMusicAuthError:
            raise
        except Exception as e:
            logger.error(f"Failed to initialize YouTube Music client: {e}")
            raise YTMusicAuthError(f"Authentication failed: {e}") from e

    def _rate_limit(self) -> None:
        """Enforce rate limiting between API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _retry_on_failure(self, func: Any, *args: Any, max_retries: int = 3, **kwargs: Any) -> Any:
        """Retry a function call on transient failures.

        Args:
            func: Function to call.
            *args: Positional arguments for the function.
            max_retries: Maximum number of retry attempts.
            **kwargs: Keyword arguments for the function.

        Returns:
            Result of the function call.

        Raises:
            YTMusicAPIError: If all retry attempts fail.
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(
                    f"API call failed (attempt {attempt + 1}/{max_retries}): {_truncate_error(e)}"
                )

                # Don't retry on authentication errors
                if "auth" in str(e).lower() or "credential" in str(e).lower():
                    raise YTMusicAuthError(f"Authentication error: {e}") from e

                # Exponential backoff
                if attempt < max_retries - 1:
                    sleep_time = 2 ** attempt
                    logger.info(f"Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)

        # All retries failed
        logger.error(f"API call failed after {max_retries} attempts: {_truncate_error(last_error)}")
        raise YTMusicAPIError(f"API call failed: {_truncate_error(last_error, max_length=300)}") from last_error

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search for songs on YouTube Music.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.

        Returns:
            List of song dictionaries with keys: video_id, title, artist, duration.

        Raises:
            YTMusicAPIError: If the search fails.
            YTMusicNotFoundError: If no results are found.
        """
        if not self._client:
            raise YTMusicAuthError("Client not initialized")

        logger.info(f"Searching for: {query}")
        self._rate_limit()

        def _search() -> list[dict[str, Any]]:
            results = self._client.search(query, filter="songs", limit=limit)
            return results

        try:
            raw_results = self._retry_on_failure(_search)

            if not raw_results:
                raise YTMusicNotFoundError(f"No results found for query: {query}")

            # Parse results into standardized format
            songs = []
            for result in raw_results:
                try:
                    # Extract artist name(s)
                    artists = result.get("artists", [])
                    artist_name = artists[0]["name"] if artists else "Unknown Artist"

                    # Extract duration (in seconds)
                    duration_text = result.get("duration", "0:00")
                    duration_seconds = self._parse_duration(duration_text)

                    song = {
                        "video_id": result.get("videoId", ""),
                        "title": result.get("title", "Unknown Title"),
                        "artist": artist_name,
                        "duration": duration_seconds,
                    }
                    songs.append(song)

                except Exception as e:
                    logger.warning(f"Failed to parse search result: {e}")
                    continue

            if not songs:
                raise YTMusicNotFoundError(f"No valid results found for query: {query}")

            logger.info(f"Found {len(songs)} results for: {query}")
            return songs

        except YTMusicNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise YTMusicAPIError(f"Search failed: {e}") from e

    def get_song_info(self, video_id: str) -> dict[str, Any]:
        """Get detailed information about a song.

        Args:
            video_id: YouTube video ID.

        Returns:
            Dictionary with keys: video_id, title, artist, album, duration, thumbnail_url.

        Raises:
            YTMusicAPIError: If retrieving song info fails.
            YTMusicNotFoundError: If the song is not found.
        """
        if not self._client:
            raise YTMusicAuthError("Client not initialized")

        logger.info(f"Getting song info for video_id: {video_id}")
        self._rate_limit()

        def _get_song() -> dict[str, Any]:
            return self._client.get_song(video_id)

        try:
            raw_info = self._retry_on_failure(_get_song)

            if not raw_info:
                raise YTMusicNotFoundError(f"Song not found: {video_id}")

            # Extract video details
            video_details = raw_info.get("videoDetails", {})

            # Parse song info into standardized format
            song_info = {
                "video_id": video_id,
                "title": video_details.get("title", "Unknown Title"),
                "artist": video_details.get("author", "Unknown Artist"),
                "album": "",  # Album info may not be available in videoDetails
                "duration": int(video_details.get("lengthSeconds", 0)),
                "thumbnail_url": "",
            }

            # Try to get thumbnail URL
            thumbnails = video_details.get("thumbnail", {}).get("thumbnails", [])
            if thumbnails:
                # Get the highest quality thumbnail
                song_info["thumbnail_url"] = thumbnails[-1].get("url", "")

            logger.info(f"Retrieved info for: {song_info['title']} by {song_info['artist']}")
            return song_info

        except YTMusicNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to get song info: {e}")
            raise YTMusicAPIError(f"Failed to get song info: {e}") from e

    def get_user_playlists(self) -> list[Playlist]:
        """Fetch all user playlists from YouTube Music.

        Returns:
            List of Playlist objects with id, name, and track_count.
            Empty playlists (track_count=0) are filtered out.

        Raises:
            YTMusicAuthError: If client is not authenticated.
            YTMusicAPIError: If fetching playlists fails.
        """
        if not self._client:
            raise YTMusicAuthError("Client not initialized")

        logger.info("Fetching user playlists")
        self._rate_limit()

        def _get_playlists() -> list[dict[str, Any]]:
            return self._client.get_library_playlists(limit=None)

        try:
            raw_playlists = self._retry_on_failure(_get_playlists)

            if not raw_playlists:
                logger.info("No playlists found")
                return []

            # Parse playlists into standardized format
            playlists = []
            for raw_playlist in raw_playlists:
                try:
                    playlist_id = raw_playlist.get("playlistId")
                    if not playlist_id:
                        logger.debug("Skipping playlist without ID")
                        continue

                    # Get track count - handle both 'count' and direct count field
                    track_count = raw_playlist.get("count", 0)
                    if track_count is None:
                        track_count = 0

                    # Filter out empty playlists
                    if track_count == 0:
                        logger.debug(f"Skipping empty playlist: {raw_playlist.get('title', 'Unknown')}")
                        continue

                    playlist = Playlist(
                        id=playlist_id,
                        name=raw_playlist.get("title", "Unknown Playlist"),
                        track_count=track_count,
                    )
                    playlists.append(playlist)

                except Exception as e:
                    logger.warning(f"Failed to parse playlist: {e}")
                    continue

            logger.info(f"Found {len(playlists)} playlists (filtered out empty playlists)")
            return playlists

        except Exception as e:
            logger.error(f"Failed to fetch playlists: {e}")
            raise YTMusicAPIError(f"Failed to fetch playlists: {e}") from e

    def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        """Get all tracks for a specific playlist.

        Args:
            playlist_id: YouTube playlist ID.

        Returns:
            List of Track objects with video_id, title, and artist.
            Tracks without video_id are filtered out.

        Raises:
            YTMusicAuthError: If client is not authenticated.
            YTMusicAPIError: If fetching tracks fails.
            YTMusicNotFoundError: If playlist is not found.
        """
        if not self._client:
            raise YTMusicAuthError("Client not initialized")

        logger.info(f"Fetching tracks for playlist: {playlist_id}")
        self._rate_limit()

        def _get_tracks() -> dict[str, Any]:
            return self._client.get_playlist(playlist_id, limit=None)

        try:
            raw_playlist = self._retry_on_failure(_get_tracks)

            if not raw_playlist:
                raise YTMusicNotFoundError(f"Playlist not found: {playlist_id}")

            # Get tracks from playlist
            raw_tracks = raw_playlist.get("tracks", [])
            if not raw_tracks:
                logger.info(f"No tracks found in playlist: {playlist_id}")
                return []

            # Parse tracks into standardized format
            tracks = []
            for raw_track in raw_tracks:
                try:
                    video_id = raw_track.get("videoId")

                    # Skip tracks without video_id (podcasts, etc.)
                    if not video_id:
                        logger.debug(f"Skipping track without video_id: {raw_track.get('title', 'Unknown')}")
                        continue

                    # Extract artist name(s)
                    artists = raw_track.get("artists", [])
                    if artists and isinstance(artists, list) and len(artists) > 0:
                        artist_name = artists[0].get("name", "Unknown Artist")
                    else:
                        artist_name = "Unknown Artist"

                    # Extract duration (YouTube Music API provides "duration" or "duration_seconds")
                    duration_seconds = None
                    if "duration_seconds" in raw_track:
                        duration_seconds = float(raw_track["duration_seconds"])
                    elif "duration" in raw_track:
                        # Duration might be in string format like "3:45"
                        duration_str = raw_track["duration"]
                        if isinstance(duration_str, str) and ":" in duration_str:
                            try:
                                parts = duration_str.split(":")
                                if len(parts) == 2:  # MM:SS
                                    duration_seconds = int(parts[0]) * 60 + int(parts[1])
                                elif len(parts) == 3:  # HH:MM:SS
                                    duration_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                            except (ValueError, IndexError):
                                logger.debug(f"Could not parse duration: {duration_str}")

                    track = Track(
                        video_id=video_id,
                        title=raw_track.get("title", "Unknown Title"),
                        artist=artist_name,
                        duration_seconds=duration_seconds,
                    )
                    tracks.append(track)

                except Exception as e:
                    logger.warning(f"Failed to parse track: {e}")
                    continue

            logger.info(f"Found {len(tracks)} valid tracks in playlist {playlist_id}")
            return tracks

        except YTMusicNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch playlist tracks: {e}")
            raise YTMusicAPIError(f"Failed to fetch playlist tracks: {e}") from e

    def get_liked_songs(self, limit: int | None = None) -> list[Track]:
        """Get user's liked songs from YouTube Music.

        This fetches the special "Liked Music" collection, which is separate from
        regular playlists.

        Args:
            limit: Maximum number of liked songs to fetch. None for all songs.

        Returns:
            List of Track objects with video_id, title, and artist.
            Tracks without video_id are filtered out.

        Raises:
            YTMusicAuthError: If client is not authenticated.
            YTMusicAPIError: If fetching liked songs fails.
        """
        if not self._client:
            raise YTMusicAuthError("Client not initialized")

        logger.info("Fetching liked songs")
        self._rate_limit()

        def _get_liked() -> dict[str, Any]:
            return self._client.get_liked_songs(limit=limit)

        try:
            raw_response = self._retry_on_failure(_get_liked)

            if not raw_response:
                logger.info("No liked songs found")
                return []

            # Get tracks from response
            raw_tracks = raw_response.get("tracks", [])
            if not raw_tracks:
                logger.info("No liked songs found")
                return []

            # Parse tracks into standardized format
            tracks = []
            for raw_track in raw_tracks:
                try:
                    video_id = raw_track.get("videoId")

                    # Skip tracks without video_id (podcasts, etc.)
                    if not video_id:
                        logger.debug(f"Skipping track without video_id: {raw_track.get('title', 'Unknown')}")
                        continue

                    # Extract artist name(s)
                    artists = raw_track.get("artists", [])
                    if artists and isinstance(artists, list) and len(artists) > 0:
                        artist_name = artists[0].get("name", "Unknown Artist")
                    else:
                        artist_name = "Unknown Artist"

                    # Extract duration (YouTube Music API provides "duration" or "duration_seconds")
                    duration_seconds = None
                    if "duration_seconds" in raw_track:
                        duration_seconds = float(raw_track["duration_seconds"])
                    elif "duration" in raw_track:
                        # Duration might be in string format like "3:45"
                        duration_str = raw_track["duration"]
                        if isinstance(duration_str, str) and ":" in duration_str:
                            try:
                                parts = duration_str.split(":")
                                if len(parts) == 2:  # MM:SS
                                    duration_seconds = int(parts[0]) * 60 + int(parts[1])
                                elif len(parts) == 3:  # HH:MM:SS
                                    duration_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                            except (ValueError, IndexError):
                                logger.debug(f"Could not parse duration: {duration_str}")

                    track = Track(
                        video_id=video_id,
                        title=raw_track.get("title", "Unknown Title"),
                        artist=artist_name,
                        duration_seconds=duration_seconds,
                    )
                    tracks.append(track)

                except Exception as e:
                    logger.warning(f"Failed to parse liked song: {e}")
                    continue

            logger.info(f"Found {len(tracks)} liked songs")
            return tracks

        except Exception as e:
            logger.error(f"Failed to fetch liked songs: {e}")
            raise YTMusicAPIError(f"Failed to fetch liked songs: {e}") from e

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        """Parse duration string (M:SS or H:MM:SS) into seconds.

        Args:
            duration_str: Duration string like "3:45" or "1:23:45".

        Returns:
            Duration in seconds.
        """
        try:
            parts = duration_str.split(":")
            if len(parts) == 2:
                # M:SS format
                minutes, seconds = parts
                return int(minutes) * 60 + int(seconds)
            elif len(parts) == 3:
                # H:MM:SS format
                hours, minutes, seconds = parts
                return int(hours) * 3600 + int(minutes) * 60 + int(seconds)
            else:
                logger.warning(f"Unexpected duration format: {duration_str}")
                return 0
        except (ValueError, AttributeError):
            logger.warning(f"Failed to parse duration: {duration_str}")
            return 0

    @staticmethod
    def setup_browser() -> None:
        """Set up browser authentication interactively.

        This is a one-time setup that creates the browser.json file in the config directory.

        Raises:
            YTMusicAuthError: If browser setup fails.
        """
        config_dir = get_config_dir()
        browser_file = config_dir / "browser.json"

        print("=" * 60)
        print("YouTube Music Browser Authentication Setup")
        print("=" * 60)
        print()
        print("This will guide you through setting up browser authentication")
        print("for YouTube Music.")
        print()
        print("Steps:")
        print("1. Open YouTube Music in your browser (music.youtube.com)")
        print("2. Open Developer Tools (F12)")
        print("3. Go to the Network tab")
        print("4. Find a POST request to 'browse'")
        print("5. Right click > Copy > Copy Request Headers")
        print()
        print("See: https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html")
        print()
        print("Paste the request headers below and press Enter twice:")
        print()

        try:
            # Read multi-line input until double newline
            lines = []
            print("(Press Ctrl+D or Ctrl+Z when done)")
            while True:
                try:
                    line = input()
                    lines.append(line)
                except EOFError:
                    break

            headers_raw = "\n".join(lines)

            if not headers_raw.strip():
                raise YTMusicAuthError("No headers provided")

            # Use ytmusicapi's built-in setup
            import ytmusicapi

            print()
            print(f"Creating browser authentication file: {browser_file}")
            ytmusicapi.setup(filepath=str(browser_file), headers_raw=headers_raw)

            print()
            print("=" * 60)
            print("Browser authentication setup complete!")
            print(f"Credentials saved to: {browser_file}")
            print()
            print("You can now start the ytmpd daemon with:")
            print("  python -m ytmpd")
            print("=" * 60)

        except KeyboardInterrupt:
            print("\n\nSetup cancelled by user.")
            raise YTMusicAuthError("Browser setup cancelled by user")
        except Exception as e:
            logger.error(f"Browser setup failed: {e}")
            raise YTMusicAuthError(f"Browser setup failed: {e}") from e


def main() -> None:
    """CLI entry point for browser authentication setup."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "setup-browser":
        try:
            YTMusicClient.setup_browser()
            sys.exit(0)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Usage: python -m ytmpd.ytmusic setup-browser")
        sys.exit(1)


if __name__ == "__main__":
    main()
