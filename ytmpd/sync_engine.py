"""
Playlist sync engine for ytmpd.

This module orchestrates the synchronization of YouTube Music playlists to MPD,
handling playlist fetching, stream URL resolution, and MPD playlist management.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from ytmpd.exceptions import MPDConnectionError, MPDPlaylistError, YTMusicAPIError
from ytmpd.mpd_client import MPDClient, TrackWithMetadata
from ytmpd.stream_resolver import StreamResolver
from ytmpd.ytmusic import Playlist, Track, YTMusicClient

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation.

    Attributes:
        success: Whether the sync completed without critical errors.
        playlists_synced: Number of playlists successfully synced.
        playlists_failed: Number of playlists that failed to sync.
        tracks_added: Total number of tracks added to MPD.
        tracks_failed: Total number of tracks that failed to resolve.
        duration_seconds: Time taken for sync operation.
        errors: List of error messages encountered during sync.
    """

    success: bool
    playlists_synced: int
    playlists_failed: int
    tracks_added: int
    tracks_failed: int
    duration_seconds: float
    errors: list[str]


@dataclass
class SyncPreview:
    """Preview of what would be synced without making changes.

    Attributes:
        youtube_playlists: List of YouTube playlist names.
        total_tracks: Total number of tracks across all playlists.
        existing_mpd_playlists: List of existing MPD playlists with the prefix.
    """

    youtube_playlists: list[str]
    total_tracks: int
    existing_mpd_playlists: list[str]


class SyncEngine:
    """Core sync engine for YouTube Music to MPD synchronization.

    This class orchestrates the entire sync process:
    1. Fetch YouTube Music playlists
    2. Resolve video IDs to stream URLs
    3. Create/update MPD playlists with proper prefixing

    Example:
        ytmusic = YTMusicClient(auth_file=Path("~/.config/ytmpd/browser.json"))
        mpd = MPDClient("~/.config/mpd/socket")
        resolver = StreamResolver(cache_hours=5)
        engine = SyncEngine(ytmusic, mpd, resolver, playlist_prefix="YT: ")

        mpd.connect()
        result = engine.sync_all_playlists()
        print(f"Synced {result.playlists_synced} playlists")
        mpd.disconnect()
    """

    def __init__(
        self,
        ytmusic_client: YTMusicClient,
        mpd_client: MPDClient,
        stream_resolver: StreamResolver,
        playlist_prefix: str = "YT: ",
        track_store: Optional["TrackStore"] = None,
        proxy_config: Optional[dict] = None,
        should_stop_callback: Optional[callable] = None,
        playlist_format: str = "m3u",
        mpd_music_directory: Optional[str] = None,
        sync_liked_songs: bool = True,
        liked_songs_playlist_name: str = "Liked Songs",
    ):
        """Initialize sync engine with dependencies.

        Args:
            ytmusic_client: Client for fetching YouTube Music playlists.
            mpd_client: Client for MPD playlist management.
            stream_resolver: Resolver for converting video IDs to stream URLs.
            playlist_prefix: Prefix to add to YouTube playlists in MPD (default: "YT: ").
            track_store: Optional TrackStore for saving track metadata mappings.
            proxy_config: Optional proxy configuration dict for generating proxy URLs.
            should_stop_callback: Optional callback that returns True when sync should be cancelled.
            playlist_format: Playlist format - "m3u" or "xspf" (default: "m3u").
            mpd_music_directory: Path to MPD's music directory (required for XSPF format).
            sync_liked_songs: Whether to sync liked songs as a playlist (default: True).
            liked_songs_playlist_name: Name for the liked songs playlist (default: "Liked Songs").
        """
        self.ytmusic = ytmusic_client
        self.mpd = mpd_client
        self.resolver = stream_resolver
        self.prefix = playlist_prefix
        self.track_store = track_store
        self.proxy_config = proxy_config
        self.should_stop = should_stop_callback or (lambda: False)
        self.playlist_format = playlist_format
        self.mpd_music_directory = mpd_music_directory
        self.sync_liked_songs = sync_liked_songs
        self.liked_songs_playlist_name = liked_songs_playlist_name
        logger.info(
            f"SyncEngine initialized with prefix '{self.prefix}', format '{self.playlist_format}', "
            f"sync_liked_songs={self.sync_liked_songs}"
        )

    def sync_all_playlists(self) -> SyncResult:
        """Perform a full sync of all YouTube Music playlists to MPD.

        This method:
        1. Fetches all YouTube Music playlists
        2. For each playlist:
           a. Gets tracks from YouTube Music
           b. Resolves video IDs to stream URLs
           c. Creates/updates MPD playlist with prefix
        3. Returns statistics about the sync operation

        Returns:
            SyncResult with statistics and any errors encountered.
        """
        start_time = time.time()
        playlists_synced = 0
        playlists_failed = 0
        tracks_added = 0
        tracks_failed = 0
        errors: list[str] = []

        logger.info("Starting full playlist sync")

        try:
            # Fetch all YouTube Music playlists
            playlists = self.ytmusic.get_user_playlists()
            logger.info(f"Found {len(playlists)} playlists to sync")

            # Create a list to sync (playlists + liked songs if enabled)
            playlists_to_sync = list(playlists)

            # Add liked songs as a special "playlist" if enabled
            if self.sync_liked_songs:
                try:
                    liked_tracks = self.ytmusic.get_liked_songs()
                    if liked_tracks:
                        # Create a fake Playlist object for liked songs
                        liked_playlist = Playlist(
                            id="__LIKED_SONGS__",
                            name=self.liked_songs_playlist_name,
                            track_count=len(liked_tracks)
                        )
                        playlists_to_sync.append(liked_playlist)
                        logger.info(f"Found {len(liked_tracks)} liked songs to sync")
                    else:
                        logger.info("No liked songs found")
                except Exception as e:
                    error_msg = f"Failed to fetch liked songs: {e}"
                    logger.warning(error_msg)
                    errors.append(error_msg)

            if not playlists_to_sync:
                logger.info("No playlists to sync")
                duration = time.time() - start_time
                return SyncResult(
                    success=True,
                    playlists_synced=0,
                    playlists_failed=0,
                    tracks_added=0,
                    tracks_failed=0,
                    duration_seconds=duration,
                    errors=[],
                )

            # Sync each playlist
            for idx, playlist in enumerate(playlists_to_sync, 1):
                # Check if we should stop (e.g., daemon shutting down)
                if self.should_stop():
                    logger.info(f"Sync cancelled after {playlists_synced} playlists (requested by daemon)")
                    break

                logger.info(f"Syncing playlist: {playlist.name} ({idx}/{len(playlists)})")

                try:
                    result = self._sync_single_playlist_internal(playlist)
                    playlists_synced += 1
                    tracks_added += result["tracks_added"]
                    tracks_failed += result["tracks_failed"]

                    if result["tracks_failed"] > 0:
                        logger.warning(
                            f"Playlist '{playlist.name}': {result['tracks_added']} tracks added, "
                            f"{result['tracks_failed']} tracks failed"
                        )

                except Exception as e:
                    playlists_failed += 1
                    error_msg = f"Failed to sync playlist '{playlist.name}': {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    # Continue with next playlist - don't let one failure stop sync

        except YTMusicAPIError as e:
            error_msg = f"Failed to fetch playlists from YouTube Music: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            duration = time.time() - start_time
            return SyncResult(
                success=False,
                playlists_synced=playlists_synced,
                playlists_failed=playlists_failed,
                tracks_added=tracks_added,
                tracks_failed=tracks_failed,
                duration_seconds=duration,
                errors=errors,
            )

        except Exception as e:
            error_msg = f"Unexpected error during sync: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            duration = time.time() - start_time
            return SyncResult(
                success=False,
                playlists_synced=playlists_synced,
                playlists_failed=playlists_failed,
                tracks_added=tracks_added,
                tracks_failed=tracks_failed,
                duration_seconds=duration,
                errors=errors,
            )

        # Calculate final statistics
        duration = time.time() - start_time
        success = playlists_failed == 0 and len(errors) == 0

        logger.info(
            f"Sync complete: {playlists_synced} playlists synced, "
            f"{playlists_failed} failed, {tracks_added} tracks added, "
            f"{tracks_failed} tracks failed ({duration:.1f}s)"
        )

        return SyncResult(
            success=success,
            playlists_synced=playlists_synced,
            playlists_failed=playlists_failed,
            tracks_added=tracks_added,
            tracks_failed=tracks_failed,
            duration_seconds=duration,
            errors=errors,
        )

    def sync_single_playlist(self, playlist_name: str) -> SyncResult:
        """Sync a specific playlist by name.

        Args:
            playlist_name: Name of the YouTube Music playlist to sync.

        Returns:
            SyncResult with statistics for this single playlist sync.

        Raises:
            YTMusicAPIError: If playlist cannot be found or fetched.
        """
        start_time = time.time()
        logger.info(f"Syncing single playlist: {playlist_name}")

        try:
            # Find the playlist by name
            playlists = self.ytmusic.get_user_playlists()
            matching_playlist: Optional[Playlist] = None

            for playlist in playlists:
                if playlist.name == playlist_name:
                    matching_playlist = playlist
                    break

            if not matching_playlist:
                error_msg = f"Playlist '{playlist_name}' not found in YouTube Music"
                logger.error(error_msg)
                duration = time.time() - start_time
                return SyncResult(
                    success=False,
                    playlists_synced=0,
                    playlists_failed=1,
                    tracks_added=0,
                    tracks_failed=0,
                    duration_seconds=duration,
                    errors=[error_msg],
                )

            # Sync the playlist
            result = self._sync_single_playlist_internal(matching_playlist)
            duration = time.time() - start_time

            logger.info(
                f"Playlist '{playlist_name}' synced: {result['tracks_added']} tracks added, "
                f"{result['tracks_failed']} tracks failed ({duration:.1f}s)"
            )

            return SyncResult(
                success=True,
                playlists_synced=1,
                playlists_failed=0,
                tracks_added=result["tracks_added"],
                tracks_failed=result["tracks_failed"],
                duration_seconds=duration,
                errors=[],
            )

        except Exception as e:
            error_msg = f"Failed to sync playlist '{playlist_name}': {e}"
            logger.error(error_msg)
            duration = time.time() - start_time
            return SyncResult(
                success=False,
                playlists_synced=0,
                playlists_failed=1,
                tracks_added=0,
                tracks_failed=0,
                duration_seconds=duration,
                errors=[error_msg],
            )

    def get_sync_preview(self) -> SyncPreview:
        """Get a preview of what would be synced without making changes.

        This method fetches YouTube Music playlists and existing MPD playlists
        but does not perform any sync operations.

        Returns:
            SyncPreview with counts and lists of playlists.

        Raises:
            YTMusicAPIError: If fetching YouTube playlists fails.
            MPDConnectionError: If MPD is not connected.
        """
        logger.info("Generating sync preview")

        # Fetch YouTube Music playlists
        playlists = self.ytmusic.get_user_playlists()
        youtube_playlist_names = [p.name for p in playlists]

        # Calculate total tracks
        total_tracks = sum(p.track_count for p in playlists)

        # Get existing MPD playlists with our prefix
        try:
            all_mpd_playlists = self.mpd.list_playlists()
            existing_mpd_playlists = [
                p for p in all_mpd_playlists if p.startswith(self.prefix)
            ]
        except (MPDConnectionError, MPDPlaylistError) as e:
            logger.warning(f"Could not list MPD playlists: {e}")
            existing_mpd_playlists = []

        logger.info(
            f"Preview: {len(playlists)} YouTube playlists, {total_tracks} total tracks, "
            f"{len(existing_mpd_playlists)} existing MPD playlists with prefix"
        )

        return SyncPreview(
            youtube_playlists=youtube_playlist_names,
            total_tracks=total_tracks,
            existing_mpd_playlists=existing_mpd_playlists,
        )

    def _sync_single_playlist_internal(self, playlist: Playlist) -> dict[str, int]:
        """Internal method to sync a single playlist.

        Args:
            playlist: Playlist object to sync.

        Returns:
            Dict with keys 'tracks_added' and 'tracks_failed'.

        Raises:
            YTMusicAPIError: If fetching tracks fails.
            MPDConnectionError: If MPD connection is lost.
            MPDPlaylistError: If creating playlist in MPD fails.
        """
        # Get tracks for this playlist
        # Special handling for liked songs
        if playlist.id == "__LIKED_SONGS__":
            tracks = self.ytmusic.get_liked_songs()
            logger.info(f"Retrieved {len(tracks)} liked songs")
        else:
            tracks = self.ytmusic.get_playlist_tracks(playlist.id)
            logger.info(f"Retrieved {len(tracks)} tracks for playlist '{playlist.name}'")

        if not tracks:
            logger.warning(f"Playlist '{playlist.name}' has no tracks, skipping")
            return {"tracks_added": 0, "tracks_failed": 0}

        # Extract video IDs
        video_ids = [track.video_id for track in tracks]

        # When proxy is enabled, skip URL resolution - proxy will resolve on-demand
        if self.proxy_config and self.proxy_config.get("enabled", False):
            logger.info(
                f"Proxy enabled - skipping URL resolution for {len(video_ids)} tracks "
                f"(will resolve on-demand when played)"
            )
            # Use empty dict to signal lazy resolution
            resolved_urls = {}
            tracks_added = len(video_ids)
            tracks_failed = 0
        else:
            # Resolve video IDs to stream URLs (batch processing for performance)
            logger.debug(f"Resolving {len(video_ids)} video IDs to stream URLs")
            resolved_urls = self.resolver.resolve_batch(video_ids)

            # Count successes and failures
            tracks_added = len(resolved_urls)
            tracks_failed = len(video_ids) - tracks_added

            if tracks_added == 0:
                logger.error(
                    f"No tracks could be resolved for playlist '{playlist.name}', skipping"
                )
                raise MPDPlaylistError(
                    f"Failed to resolve any tracks for playlist '{playlist.name}'"
                )

            logger.info(
                f"Resolved {tracks_added}/{len(video_ids)} tracks for '{playlist.name}'"
            )

        # Create list of tracks with metadata in the same order as tracks
        tracks_with_metadata = []
        lazy_resolution = self.proxy_config and self.proxy_config.get("enabled", False)

        for track in tracks:
            # When proxy enabled, use placeholder URL (proxy will resolve on-demand)
            if lazy_resolution:
                # Placeholder URL - not used since proxy URLs are generated in create_or_replace_playlist
                stream_url = None

                # Save track mapping to TrackStore WITHOUT stream_url for lazy resolution
                if self.track_store:
                    try:
                        self.track_store.add_track(
                            video_id=track.video_id,
                            stream_url=None,  # Will be resolved on-demand by proxy
                            title=track.title,
                            artist=track.artist,
                        )
                        logger.debug(f"Saved track metadata for lazy resolution: {track.video_id}")
                    except Exception as e:
                        logger.warning(f"Failed to save track metadata for {track.video_id}: {e}")

                tracks_with_metadata.append(
                    TrackWithMetadata(
                        url=stream_url or "",  # Empty URL, proxy URL will be used from M3U
                        title=track.title,
                        artist=track.artist,
                        video_id=track.video_id,
                        duration_seconds=track.duration_seconds,
                    )
                )
            # When proxy disabled, only include successfully resolved tracks
            elif track.video_id in resolved_urls:
                stream_url = resolved_urls[track.video_id]

                # Save track mapping to TrackStore if enabled
                if self.track_store:
                    try:
                        self.track_store.add_track(
                            video_id=track.video_id,
                            stream_url=stream_url,
                            title=track.title,
                            artist=track.artist,
                        )
                        logger.debug(f"Saved track mapping for {track.video_id}")
                    except Exception as e:
                        logger.warning(f"Failed to save track mapping for {track.video_id}: {e}")

                tracks_with_metadata.append(
                    TrackWithMetadata(
                        url=stream_url,
                        title=track.title,
                        artist=track.artist,
                        video_id=track.video_id,
                        duration_seconds=track.duration_seconds,
                    )
                )
            else:
                logger.debug(
                    f"Skipping unresolved track: {track.title} by {track.artist}"
                )

        # Create MPD playlist with prefix
        mpd_playlist_name = f"{self.prefix}{playlist.name}"
        logger.debug(f"Creating MPD playlist: {mpd_playlist_name}")

        self.mpd.create_or_replace_playlist(
            mpd_playlist_name,
            tracks_with_metadata,
            proxy_config=self.proxy_config,
            playlist_format=self.playlist_format,
            mpd_music_directory=self.mpd_music_directory,
        )

        logger.info(f"Successfully created MPD playlist: {mpd_playlist_name}")

        return {"tracks_added": tracks_added, "tracks_failed": tracks_failed}
