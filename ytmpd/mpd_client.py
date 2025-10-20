"""MPD client module for ytmpd.

This module provides a high-level wrapper around python-mpd2 for MPD
communication, with a focus on playlist management operations.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from mpd import MPDClient as MPDClientBase
from mpd import CommandError, ConnectionError

from ytmpd.exceptions import MPDConnectionError, MPDPlaylistError
from ytmpd.xspf_generator import XSPFTrack, generate_xspf

logger = logging.getLogger(__name__)


@dataclass
class TrackWithMetadata:
    """Track with URL and metadata for M3U/XSPF playlist generation."""
    url: str
    title: str
    artist: str
    video_id: str
    duration_seconds: Optional[float] = None  # Duration in seconds (for XSPF conversion)


class MPDClient:
    """High-level MPD client for playlist management.

    This class wraps python-mpd2's MPDClient and provides convenient methods
    for connecting to MPD via Unix socket or TCP.

    Args:
        socket_path: Path to MPD Unix socket file, or "host:port" for TCP.
        playlist_directory: Path to MPD's playlist directory (required for TCP).
    """

    def __init__(self, socket_path: str, playlist_directory: Optional[str] = None):
        """Initialize client with Unix socket path or host:port.

        Args:
            socket_path: Path to MPD Unix socket (e.g., ~/.config/mpd/socket)
                        or "host:port" for TCP (e.g., "localhost:6600").
            playlist_directory: Path to MPD's playlist directory. If not specified,
                              defaults to ~/.config/mpd/playlists.
        """
        self.socket_path = str(Path(socket_path).expanduser()) if not ":" in socket_path else socket_path
        self._client: Optional[MPDClientBase] = None
        self._connected = False

        # Set playlist directory
        if playlist_directory:
            self.playlist_directory = Path(playlist_directory).expanduser()
        else:
            self.playlist_directory = Path.home() / ".config" / "mpd" / "playlists"

        # Detect connection type
        if ":" in socket_path:
            parts = socket_path.split(":", 1)
            self.connection_type = "tcp"
            self.host = parts[0]
            self.port = int(parts[1])
        else:
            self.connection_type = "unix"
            self.host = None
            self.port = None

    def connect(self) -> None:
        """Connect to MPD via Unix socket or TCP.

        Raises:
            MPDConnectionError: If connection fails (socket missing, MPD not running, etc.).
        """
        try:
            self._client = MPDClientBase()

            if self.connection_type == "unix":
                # Check if socket exists
                socket_file = Path(self.socket_path)
                if not socket_file.exists():
                    raise MPDConnectionError(
                        f"MPD socket not found at {self.socket_path}. "
                        "Is MPD running? Check your MPD configuration."
                    )

                logger.info(f"Connecting to MPD at {self.socket_path}")
                self._client.connect(self.socket_path)
            else:
                # TCP connection
                logger.info(f"Connecting to MPD at {self.host}:{self.port}")
                self._client.connect(self.host, self.port)

            self._connected = True
            logger.info("Successfully connected to MPD")
        except ConnectionError as e:
            raise MPDConnectionError(
                f"Failed to connect to MPD: {e}"
            ) from e
        except Exception as e:
            raise MPDConnectionError(
                f"Unexpected error connecting to MPD: {e}"
            ) from e

    def disconnect(self) -> None:
        """Cleanly disconnect from MPD."""
        if self._client and self._connected:
            try:
                logger.debug("Disconnecting from MPD")
                self._client.close()
                self._client.disconnect()
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
            finally:
                self._connected = False
                self._client = None

    def is_connected(self) -> bool:
        """Check if currently connected to MPD.

        Returns:
            True if connected, False otherwise.
        """
        if not self._connected or not self._client:
            return False

        # Test connection by sending a ping
        try:
            self._client.ping()
            return True
        except Exception:
            self._connected = False
            return False

    def get_playlist_directory(self) -> Path:
        """Get MPD's playlist directory path.

        Returns:
            Path to MPD's playlist directory.

        Raises:
            MPDPlaylistError: If playlist directory cannot be created.
        """
        try:
            # Ensure playlist directory exists
            if not self.playlist_directory.exists():
                logger.warning(f"Playlist directory {self.playlist_directory} does not exist, creating it")
                self.playlist_directory.mkdir(parents=True, exist_ok=True)

            logger.debug(f"MPD playlist directory: {self.playlist_directory}")
            return self.playlist_directory

        except Exception as e:
            raise MPDPlaylistError(f"Failed to get playlist directory: {e}") from e

    def list_playlists(self) -> list[str]:
        """Return list of all playlist names in MPD.

        Returns:
            List of playlist names as strings.

        Raises:
            MPDConnectionError: If not connected to MPD.
            MPDPlaylistError: If listing playlists fails.
        """
        self._ensure_connected()

        try:
            logger.debug("Listing MPD playlists")
            playlists = self._client.listplaylists()
            names = [p["playlist"] for p in playlists]
            logger.debug(f"Found {len(names)} playlists")
            return names
        except ConnectionError as e:
            raise MPDConnectionError(f"Lost connection to MPD: {e}") from e
        except Exception as e:
            raise MPDPlaylistError(f"Failed to list playlists: {e}") from e

    def playlist_exists(self, name: str) -> bool:
        """Check if a playlist with this name exists.

        Args:
            name: Playlist name to check.

        Returns:
            True if playlist exists, False otherwise.
        """
        try:
            playlists = self.list_playlists()
            return name in playlists
        except Exception:
            return False

    def create_or_replace_playlist(
        self,
        name: str,
        tracks: list[TrackWithMetadata],
        proxy_config: dict[str, Any] | None = None,
        playlist_format: str = "m3u",
        mpd_music_directory: Optional[str] = None,
    ) -> None:
        """Create a new playlist or replace existing one with given tracks.

        This method supports two playlist formats:
        - M3U: Traditional format with EXTINF tags (single "Name" field in MPD)
        - XSPF: XML format with separate artist/title fields (separate %artist%/%title% in MPD)

        XSPF playlists are created in MPD's music directory (not playlist directory)
        because MPD only supports XSPF files when loaded from the music library.

        Args:
            name: Playlist name.
            tracks: List of tracks with URLs and metadata.
            proxy_config: Optional proxy configuration dict with 'enabled', 'host', and 'port' keys.
                         If provided and enabled=True, generates proxy URLs instead of direct URLs.
            playlist_format: Playlist format - "m3u" or "xspf" (default: "m3u").
            mpd_music_directory: Path to MPD's music directory (required for XSPF format).

        Raises:
            MPDConnectionError: If not connected to MPD.
            MPDPlaylistError: If playlist operations fail.
            ValueError: If XSPF format requested but mpd_music_directory not provided.
        """
        self._ensure_connected()

        if not tracks:
            logger.warning(f"No tracks provided for playlist '{name}', skipping")
            return

        playlist_format = playlist_format.lower()

        if playlist_format == "xspf":
            self._create_xspf_playlist(name, tracks, proxy_config, mpd_music_directory)
        elif playlist_format == "m3u":
            self._create_m3u_playlist(name, tracks, proxy_config)
        else:
            raise ValueError(f"Unsupported playlist format: {playlist_format}. Use 'm3u' or 'xspf'.")

    def _create_m3u_playlist(
        self,
        name: str,
        tracks: list[TrackWithMetadata],
        proxy_config: dict[str, Any] | None = None,
    ) -> None:
        """Create M3U playlist (original implementation)."""
        try:
            # Validate playlist name to prevent path traversal attacks
            if '/' in name or '\\' in name or '..' in name:
                raise ValueError(f"Invalid playlist name (contains path separators): {name}")

            # Get MPD's playlist directory
            playlist_dir = self.get_playlist_directory()
            playlist_file = playlist_dir / f"{name}.m3u"

            logger.debug(f"Creating M3U playlist '{name}' with {len(tracks)} tracks")

            # Write M3U file with EXTINF metadata
            m3u_content = "#EXTM3U\n"
            for track in tracks:
                # EXTINF format: #EXTINF:duration,Artist - Title
                # Duration -1 means unknown
                artist_title = f"{track.artist} - {track.title}"
                m3u_content += f"#EXTINF:-1,{artist_title}\n"

                # Use proxy URL if proxy is enabled, otherwise use direct URL
                if proxy_config and proxy_config.get("enabled", False):
                    track_url = f"http://{proxy_config['host']}:{proxy_config['port']}/proxy/{track.video_id}"
                else:
                    track_url = track.url

                m3u_content += f"{track_url}\n"

            # Write the file
            playlist_file.write_text(m3u_content, encoding='utf-8')

            logger.info(f"Created M3U playlist '{name}' with {len(tracks)} tracks at {playlist_file}")

        except Exception as e:
            raise MPDPlaylistError(
                f"Error creating M3U playlist '{name}': {e}"
            ) from e

    def _create_xspf_playlist(
        self,
        name: str,
        tracks: list[TrackWithMetadata],
        proxy_config: dict[str, Any] | None = None,
        mpd_music_directory: Optional[str] = None,
    ) -> None:
        """Create XSPF playlist in MPD's music directory.

        XSPF playlists must be in the music directory (not playlist directory) to work with MPD.
        They provide separate artist/title metadata fields for better display in MPD clients.
        """
        if not mpd_music_directory:
            raise ValueError(
                "mpd_music_directory is required for XSPF format. "
                "Please configure mpd_music_directory in config.yaml."
            )

        try:
            # Validate playlist name to prevent path traversal attacks
            if '/' in name or '\\' in name or '..' in name:
                raise ValueError(f"Invalid playlist name (contains path separators): {name}")

            # Create _youtube subdirectory in music directory
            music_dir = Path(mpd_music_directory).expanduser()
            youtube_dir = music_dir / "_youtube"
            youtube_dir.mkdir(parents=True, exist_ok=True)

            playlist_file = youtube_dir / f"{name}.xspf"

            logger.debug(f"Creating XSPF playlist '{name}' with {len(tracks)} tracks")

            # Convert tracks to XSPF format
            xspf_tracks = []
            for track in tracks:
                # Use proxy URL if proxy is enabled, otherwise use direct URL
                if proxy_config and proxy_config.get("enabled", False):
                    track_url = f"http://{proxy_config['host']}:{proxy_config['port']}/proxy/{track.video_id}"
                else:
                    track_url = track.url

                # Convert duration to milliseconds if available
                duration_ms = None
                if track.duration_seconds is not None:
                    duration_ms = int(track.duration_seconds * 1000)

                xspf_tracks.append(
                    XSPFTrack(
                        location=track_url,
                        creator=track.artist,
                        title=track.title,
                        duration=duration_ms,
                    )
                )

            # Generate XSPF content
            xspf_content = generate_xspf(xspf_tracks)

            # Write the file
            playlist_file.write_text(xspf_content, encoding='utf-8')

            logger.info(f"Created XSPF playlist '{name}' with {len(tracks)} tracks at {playlist_file}")

        except Exception as e:
            raise MPDPlaylistError(
                f"Error creating XSPF playlist '{name}': {e}"
            ) from e

    def clear_playlist(self, name: str) -> None:
        """Delete a playlist by name.

        Args:
            name: Playlist name to delete.

        Raises:
            MPDConnectionError: If not connected to MPD.
            MPDPlaylistError: If deletion fails.
        """
        self._ensure_connected()

        try:
            logger.debug(f"Deleting playlist: {name}")
            self._client.rm(name)
            logger.info(f"Deleted playlist: {name}")
        except ConnectionError as e:
            raise MPDConnectionError(f"Lost connection to MPD: {e}") from e
        except CommandError as e:
            if "No such playlist" in str(e):
                logger.warning(f"Playlist '{name}' does not exist")
            else:
                raise MPDPlaylistError(f"Failed to delete playlist '{name}': {e}") from e
        except Exception as e:
            raise MPDPlaylistError(
                f"Unexpected error deleting playlist '{name}': {e}"
            ) from e

    def add_to_playlist(self, name: str, url: str) -> None:
        """Add a single URL to an existing playlist.

        Args:
            name: Playlist name.
            url: Stream URL to add.

        Raises:
            MPDConnectionError: If not connected to MPD.
            MPDPlaylistError: If operation fails.
        """
        self._ensure_connected()

        try:
            logger.debug(f"Adding URL to playlist '{name}'")
            self._client.playlistadd(name, url)
            logger.debug(f"Added URL to playlist '{name}'")
        except ConnectionError as e:
            raise MPDConnectionError(f"Lost connection to MPD: {e}") from e
        except CommandError as e:
            if "No such playlist" in str(e):
                raise MPDPlaylistError(f"Playlist '{name}' does not exist") from e
            else:
                raise MPDPlaylistError(
                    f"Failed to add URL to playlist '{name}': {e}"
                ) from e
        except Exception as e:
            raise MPDPlaylistError(
                f"Unexpected error adding to playlist '{name}': {e}"
            ) from e

    def currentsong(self) -> dict[str, str]:
        """Get the currently playing song from MPD.

        Returns:
            Dictionary with song info (file, title, artist, etc).
            Returns empty dict if no song is playing.

        Raises:
            MPDConnectionError: If not connected to MPD.
        """
        self._ensure_connected()
        return self._client.currentsong()

    def _ensure_connected(self) -> None:
        """Ensure we're connected to MPD, reconnect if needed.

        Raises:
            MPDConnectionError: If not connected and can't reconnect.
        """
        if not self.is_connected():
            # Connection lost or never established - try to (re)connect
            logger.warning("Lost connection to MPD, attempting to reconnect")
            self.disconnect()  # Clean up any stale connection
            time.sleep(0.5)  # Brief delay before reconnecting
            try:
                self.connect()
                logger.info("Successfully reconnected to MPD")
            except MPDConnectionError as e:
                logger.error(f"Failed to reconnect to MPD: {e}")
                raise

    def __enter__(self):
        """Context manager entry: connect to MPD.

        Returns:
            Self for use in with statement.
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: disconnect from MPD.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.

        Returns:
            False to propagate exceptions.
        """
        self.disconnect()
        return False
