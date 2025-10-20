"""
Stream URL resolver using yt-dlp to extract direct audio URLs from YouTube video IDs.

This module provides functionality to resolve YouTube video IDs to streamable audio URLs
using yt-dlp, with in-memory caching to avoid repeated extractions. Stream URLs expire
after approximately 6 hours, so caching is limited to 5 hours by default.
"""

import concurrent.futures
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yt_dlp

logger = logging.getLogger(__name__)


@dataclass
class CachedURL:
    """Cached stream URL with expiration tracking.

    Attributes:
        url: The direct audio stream URL
        cached_at: When this URL was cached
        video_id: The YouTube video ID this URL corresponds to
    """
    url: str
    cached_at: datetime
    video_id: str


class StreamResolver:
    """Resolves YouTube video IDs to streamable audio URLs using yt-dlp.

    Features:
    - In-memory caching with configurable expiration
    - Graceful error handling for unavailable videos
    - Batch resolution with parallel processing
    - Automatic retry on network errors

    Example:
        resolver = StreamResolver(cache_hours=5)
        url = resolver.resolve_video_id("dQw4w9WgXcQ")
        if url:
            print(f"Stream URL: {url}")
    """

    def __init__(self, cache_hours: int = 5, should_stop_callback: Optional[callable] = None, cache_file: Optional[str] = None):
        """Initialize resolver with cache duration.

        Args:
            cache_hours: How long to cache URLs before re-extraction (default: 5 hours)
            should_stop_callback: Optional callback that returns True when resolution should be cancelled.
            cache_file: Optional path to JSON file for persistent cache storage.
        """
        self._cache: dict[str, CachedURL] = {}
        self._cache_hours = cache_hours
        self._cache_file = Path(cache_file).expanduser() if cache_file else None
        self.should_stop = should_stop_callback or (lambda: False)

        # Load persistent cache if enabled
        if self._cache_file:
            self._load_cache()

        logger.info(f"StreamResolver initialized with {cache_hours}h cache" +
                   (f", persistent cache at {self._cache_file}" if self._cache_file else ""))

    def resolve_video_id(self, video_id: str) -> Optional[str]:
        """Get streamable audio URL for a YouTube video ID.

        This method first checks the cache for a valid (non-expired) URL. If not found
        or expired, it uses yt-dlp to extract the stream URL from YouTube.

        Args:
            video_id: YouTube video ID (e.g., "dQw4w9WgXcQ")

        Returns:
            Stream URL string if successful, None if video unavailable or extraction fails
        """
        # Check cache first
        if self._is_cache_valid(video_id):
            cached = self._cache[video_id]
            logger.debug(f"Cache hit for {video_id}")
            return cached.url

        logger.debug(f"Cache miss for {video_id}, extracting URL")

        # Extract URL with yt-dlp
        url = self._extract_url(video_id)

        if url:
            # Cache the result
            self._cache[video_id] = CachedURL(
                url=url,
                cached_at=datetime.now(),
                video_id=video_id
            )
            logger.debug(f"Cached URL for {video_id}")

            # Persist cache if enabled
            if self._cache_file:
                self._save_cache()

        return url

    def resolve_batch(self, video_ids: list[str]) -> dict[str, str]:
        """Resolve multiple video IDs efficiently with parallel processing.

        This method processes video IDs in parallel with limited concurrency to avoid
        rate limiting. It returns only successful resolutions, logging failures.

        Args:
            video_ids: List of YouTube video IDs to resolve

        Returns:
            Dict mapping video_id -> stream URL for successful resolutions only
        """
        if not video_ids:
            return {}

        logger.info(f"Resolving batch of {len(video_ids)} video IDs")
        results: dict[str, str] = {}

        # Use ThreadPoolExecutor for parallel processing (max 10 concurrent)
        max_workers = min(10, len(video_ids))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_video_id = {
                executor.submit(self.resolve_video_id, video_id): video_id
                for video_id in video_ids
            }

            # Collect results as they complete
            completed = 0
            pending_futures = list(future_to_video_id.keys())

            while pending_futures:
                # Check if we should stop (e.g., daemon shutting down)
                if self.should_stop():
                    logger.info(f"Stream resolution cancelled after {completed}/{len(video_ids)} videos")
                    # Cancel all remaining futures
                    for f in pending_futures:
                        f.cancel()
                    break

                # Use timeout so we can check should_stop() regularly
                done, pending_futures = concurrent.futures.wait(
                    pending_futures, timeout=0.5, return_when=concurrent.futures.FIRST_COMPLETED
                )

                for future in done:
                    video_id = future_to_video_id[future]
                    completed += 1

                    try:
                        url = future.result()
                        if url:
                            results[video_id] = url
                        else:
                            logger.warning(f"Failed to resolve {video_id}")
                    except Exception as e:
                        logger.error(f"Exception resolving {video_id}: {e}")

                    # Log progress every 10 videos
                    if completed % 10 == 0:
                        logger.info(f"Progress: {completed}/{len(video_ids)} videos processed")

        success_rate = len(results) / len(video_ids) * 100 if video_ids else 0
        logger.info(
            f"Batch complete: {len(results)}/{len(video_ids)} successful ({success_rate:.1f}%)"
        )

        # Persist cache after batch resolution
        if self._cache_file and results:
            self._save_cache()

        return results

    def _extract_url(self, video_id: str) -> Optional[str]:
        """Extract stream URL using yt-dlp.

        This method uses yt-dlp to fetch video information and extract the direct
        audio stream URL. It handles various failure modes gracefully.

        Args:
            video_id: YouTube video ID

        Returns:
            Stream URL if successful, None if extraction fails
        """
        ydl_opts = {
            # Prefer direct HTTPS URLs over HLS/DASH for proxy compatibility
            # Format priority: opus in webm (251) > m4a audio (140) > any audio
            'format': 'bestaudio[protocol^=https][ext=webm]/bestaudio[protocol^=https]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'nocheckcertificate': True,
            # Don't download, just extract info
            'skip_download': True,
            # Prefer non-HLS formats for direct streaming
            'prefer_free_formats': True,
        }

        video_url = f'https://youtube.com/watch?v={video_id}'

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

                if not info:
                    logger.info(f"No info extracted for {video_id}")
                    return None

                # Get the direct URL
                url = info.get('url')
                if not url:
                    logger.warning(f"No URL in extracted info for {video_id}")
                    return None

                logger.debug(f"Extracted URL for {video_id}")
                return url

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e).lower()

            # Handle specific error cases with appropriate log levels
            if 'private video' in error_msg or 'this video is private' in error_msg:
                logger.info(f"Video {video_id} is private")
            elif 'video unavailable' in error_msg or 'not available' in error_msg:
                logger.info(f"Video {video_id} is unavailable")
            elif 'region' in error_msg or 'blocked' in error_msg:
                logger.info(f"Video {video_id} is region locked")
            elif 'removed' in error_msg or 'deleted' in error_msg:
                logger.info(f"Video {video_id} has been removed")
            else:
                # Unknown download error
                logger.warning(f"Download error for {video_id}: {e}")

            return None

        except yt_dlp.utils.ExtractorError as e:
            logger.warning(f"Extractor error for {video_id}: {e}")
            return None

        except Exception as e:
            # Network errors or unexpected issues
            # Retry once for network errors
            if 'network' in str(e).lower() or 'timeout' in str(e).lower():
                logger.debug(f"Network error for {video_id}, retrying once")
                time.sleep(1)

                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(video_url, download=False)
                        if info and info.get('url'):
                            logger.debug(f"Retry successful for {video_id}")
                            return info['url']
                except Exception as retry_error:
                    logger.warning(f"Retry failed for {video_id}: {retry_error}")
                    return None

            logger.error(f"Unexpected error extracting {video_id}: {e}")
            return None

    def _is_cache_valid(self, video_id: str) -> bool:
        """Check if cached URL is still valid (not expired).

        Args:
            video_id: YouTube video ID to check

        Returns:
            True if cache hit and not expired, False otherwise
        """
        if video_id not in self._cache:
            return False

        cached = self._cache[video_id]
        age = datetime.now() - cached.cached_at
        max_age = timedelta(hours=self._cache_hours)

        if age > max_age:
            logger.debug(f"Cache expired for {video_id} (age: {age.total_seconds()/3600:.1f}h)")
            # Remove expired entry
            del self._cache[video_id]
            return False

        return True

    def clear_cache(self) -> None:
        """Clear all cached URLs.

        This can be useful for testing or to force re-extraction of all URLs.
        """
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cleared cache ({count} entries)")

    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dict with cache_size and expired_count
        """
        total = len(self._cache)
        expired = sum(1 for video_id in list(self._cache.keys()) if not self._is_cache_valid(video_id))

        return {
            'cache_size': total,
            'expired_count': expired,
            'valid_count': total - expired
        }

    def _load_cache(self) -> None:
        """Load cache from JSON file.

        Loads previously cached URLs from disk. Expired entries are discarded.
        """
        if not self._cache_file or not self._cache_file.exists():
            logger.debug("No cache file to load")
            return

        try:
            with open(self._cache_file, 'r') as f:
                cache_data = json.load(f)

            loaded = 0
            expired = 0
            for video_id, entry in cache_data.items():
                # Parse datetime from ISO format
                cached_at = datetime.fromisoformat(entry['cached_at'])

                # Check if expired
                age = datetime.now() - cached_at
                if age > timedelta(hours=self._cache_hours):
                    expired += 1
                    continue

                self._cache[video_id] = CachedURL(
                    url=entry['url'],
                    cached_at=cached_at,
                    video_id=video_id
                )
                loaded += 1

            logger.info(f"Loaded {loaded} cached URLs from {self._cache_file} ({expired} expired entries discarded)")

        except Exception as e:
            logger.warning(f"Failed to load cache from {self._cache_file}: {e}")

    def _save_cache(self) -> None:
        """Save cache to JSON file.

        Saves current cache state to disk for persistence across restarts.
        Only saves valid (non-expired) entries.
        """
        if not self._cache_file:
            return

        try:
            # Ensure directory exists
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)

            # Convert cache to JSON-serializable format
            cache_data = {}
            for video_id, cached_url in self._cache.items():
                # Only save non-expired entries
                if self._is_cache_valid(video_id):
                    cache_data[video_id] = {
                        'url': cached_url.url,
                        'cached_at': cached_url.cached_at.isoformat(),
                        'video_id': cached_url.video_id
                    }

            # Write to file
            with open(self._cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

            logger.debug(f"Saved {len(cache_data)} cached URLs to {self._cache_file}")

        except Exception as e:
            logger.warning(f"Failed to save cache to {self._cache_file}: {e}")
