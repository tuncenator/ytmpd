"""URL resolution proxy server for MPD clients.

This module implements an HTTP redirect proxy that handles lazy URL resolution
and automatic refresh of expired YouTube stream URLs. When MPD requests a track,
the proxy resolves the YouTube URL (if needed) and returns an HTTP 307 redirect,
allowing MPD to stream directly from YouTube.

This approach provides:
- Lazy loading: URLs are only resolved when tracks are actually played
- Auto-refresh: Expired URLs are automatically refreshed on-demand
- No timeouts: MPD streams directly from YouTube, avoiding proxy bottlenecks

Example:
    >>> store = TrackStore("~/.config/ytmpd/track_mapping.db")
    >>> proxy = ICYProxyServer(store, host="localhost", port=8080)
    >>> await proxy.start()
    # MPD requests: http://localhost:8080/proxy/dQw4w9WgXcQ
    # Proxy returns: HTTP 307 -> direct YouTube URL
"""

import asyncio
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

from aiohttp import web

from ytmpd.exceptions import URLRefreshError
from ytmpd.track_store import TrackStore

logger = logging.getLogger(__name__)

# URL expiry time in hours (YouTube URLs expire after ~6 hours)
URL_EXPIRY_HOURS = 5

# Maximum number of concurrent resolution requests
MAX_CONCURRENT_STREAMS = 10

# Valid video_id pattern (YouTube video IDs are 11 characters: alphanumeric, -, _)
VIDEO_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{11}$")


class ICYProxyServer:
    """HTTP redirect proxy for lazy YouTube URL resolution.

    The server handles requests in the format: http://host:port/proxy/{video_id}
    It resolves the YouTube stream URL (with caching and auto-refresh) and returns
    an HTTP 307 redirect, allowing MPD to stream directly from YouTube.

    Attributes:
        track_store: TrackStore instance for metadata lookup
        stream_resolver: StreamResolver instance for URL resolution
        host: Server bind address
        port: Server bind port
        app: aiohttp.web.Application instance
        runner: aiohttp.web.AppRunner instance
        site: aiohttp.web.TCPSite instance

    Example:
        >>> store = TrackStore(":memory:")
        >>> store.add_track("test123", None, "Title", "Artist", "video_id123")
        >>> proxy = ICYProxyServer(store, stream_resolver=resolver)
        >>> await proxy.start()
        >>> # Server now listening on http://localhost:8080
        >>> # Request: http://localhost:8080/proxy/test123 -> HTTP 307 to YouTube
        >>> await proxy.stop()
    """

    def __init__(
        self,
        track_store: TrackStore,
        stream_resolver: Optional[Any] = None,
        host: str = "localhost",
        port: int = 8080,
        max_concurrent_streams: int = MAX_CONCURRENT_STREAMS,
    ) -> None:
        """Initialize proxy server.

        Args:
            track_store: TrackStore instance for looking up video metadata
            stream_resolver: Optional StreamResolver for URL refresh (imported at runtime to avoid circular deps)
            host: Server bind address (default: "localhost")
            port: Server bind port (default: 8080)
            max_concurrent_streams: Maximum number of concurrent resolution requests (default: 10)
        """
        self.track_store = track_store
        self.stream_resolver = stream_resolver
        self.host = host
        self.port = port
        self.max_concurrent_streams = max_concurrent_streams
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

        # Connection tracking (tracks concurrent resolution requests)
        self._active_connections = 0
        self._connection_lock = asyncio.Lock()

        # Setup routes
        self.app.router.add_get("/proxy/{video_id}", self._handle_proxy_request)
        self.app.router.add_get("/health", self._handle_health_check)

    async def start(self) -> None:
        """Start the aiohttp server.

        Raises:
            OSError: If the port is already in use or binding fails
        """
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

        logger.info(
            f"[PROXY] Starting redirect proxy on {self.host}:{self.port} "
            f"(max concurrent requests: {self.max_concurrent_streams}, "
            f"URL refresh: {'enabled' if self.stream_resolver else 'disabled'})"
        )

    async def stop(self) -> None:
        """Stop the aiohttp server gracefully.

        Cleans up server resources.
        """
        if self.site:
            await self.site.stop()
            logger.info("[PROXY] Server site stopped")

        if self.runner:
            await self.runner.cleanup()
            logger.info("[PROXY] Server runner cleaned up")

    def _is_url_expired(self, updated_at: float, expiry_hours: int = URL_EXPIRY_HOURS) -> bool:
        """Check if a stream URL has expired based on its updated timestamp.

        Args:
            updated_at: Unix timestamp when URL was last updated
            expiry_hours: Maximum age in hours before URL is considered expired

        Returns:
            True if URL is expired, False otherwise
        """
        age_seconds = time.time() - updated_at
        age_hours = age_seconds / 3600
        is_expired = age_hours > expiry_hours

        if is_expired:
            logger.debug(f"URL expired (age: {age_hours:.1f}h > {expiry_hours}h)")

        return is_expired

    async def _refresh_stream_url(self, video_id: str) -> str:
        """Refresh an expired stream URL using StreamResolver.

        Args:
            video_id: YouTube video ID to refresh

        Returns:
            New stream URL

        Raises:
            URLRefreshError: If refresh fails or StreamResolver not available
        """
        if not self.stream_resolver:
            raise URLRefreshError("StreamResolver not configured - cannot refresh URLs")

        logger.info(f"[PROXY] Refreshing expired URL for {video_id}")

        try:
            # StreamResolver.resolve_video_id is synchronous, run in thread pool
            loop = asyncio.get_event_loop()
            new_url = await loop.run_in_executor(
                None,
                self.stream_resolver.resolve_video_id,
                video_id
            )

            if not new_url:
                raise URLRefreshError(f"Failed to resolve new URL for {video_id}")

            logger.info(f"[PROXY] Successfully refreshed URL for {video_id}")
            return new_url

        except Exception as e:
            logger.error(f"[PROXY] Failed to refresh URL for {video_id}: {e}")
            raise URLRefreshError(f"URL refresh failed for {video_id}: {e}") from e

    async def _handle_health_check(self, request: web.Request) -> web.Response:
        """Handle health check requests.

        Args:
            request: aiohttp request object

        Returns:
            JSON response with server status
        """
        return web.json_response({"status": "ok", "service": "icy-proxy"})

    async def _handle_proxy_request(self, request: web.Request) -> web.Response:
        """Handle proxy requests for video streams with URL refresh and connection limiting.

        URL format: /proxy/{video_id}

        Process:
            1. Check concurrent connection limit
            2. Extract and validate video_id from path
            3. Lookup track metadata in TrackStore
            4. Check if URL is expired and refresh if needed
            5. Return HTTP 307 redirect to direct YouTube URL

        This allows MPD to stream directly from YouTube while the proxy handles
        lazy URL resolution and automatic refresh of expired URLs.

        Args:
            request: aiohttp request object containing video_id in path

        Returns:
            HTTP 307 Temporary Redirect to YouTube stream URL

        Raises:
            HTTPServiceUnavailable: If too many concurrent connections
            HTTPBadRequest: If video_id format is invalid
            HTTPNotFound: If video_id not found in TrackStore
            HTTPBadGateway: If URL resolution/refresh fails
        """
        video_id = request.match_info["video_id"]
        client_ip = request.remote or "unknown"

        # Validate video_id format
        if not VIDEO_ID_PATTERN.match(video_id):
            logger.warning(f"[PROXY] Invalid video_id format from {client_ip}: {video_id}")
            raise web.HTTPBadRequest(
                text=f"Invalid video_id format: {video_id}"
            )

        # Check connection limit
        async with self._connection_lock:
            if self._active_connections >= self.max_concurrent_streams:
                logger.warning(
                    f"[PROXY] Connection limit reached ({self._active_connections}/{self.max_concurrent_streams}), "
                    f"rejecting request for {video_id} from {client_ip}"
                )
                raise web.HTTPServiceUnavailable(
                    text=f"Too many concurrent streams ({self._active_connections}/{self.max_concurrent_streams})"
                )

            self._active_connections += 1
            logger.debug(
                f"[PROXY] Connection accepted for {video_id} "
                f"({self._active_connections}/{self.max_concurrent_streams} active)"
            )

        try:
            # Lookup track in store
            track = self.track_store.get_track(video_id)
            if not track:
                logger.warning(f"[PROXY] Track not found: {video_id}")
                raise web.HTTPNotFound(
                    text=f"Track not found: {video_id}"
                )

            stream_url = track["stream_url"]
            updated_at = track["updated_at"]
            artist = track["artist"] or "Unknown Artist"
            title = track["title"]
            icy_name = f"{artist} - {title}"

            # Lazy resolution: If stream_url is None, resolve it on-demand
            if stream_url is None:
                logger.info(f"[PROXY] Stream URL not resolved yet for {video_id}, resolving on-demand")
                try:
                    stream_url = await self._refresh_stream_url(video_id)
                    # Save resolved URL to TrackStore
                    self.track_store.update_stream_url(video_id, stream_url)
                    logger.info(f"[PROXY] On-demand resolution successful for {video_id}")
                except URLRefreshError as e:
                    logger.error(f"[PROXY] On-demand resolution failed for {video_id}: {e}")
                    raise web.HTTPBadGateway(
                        text=f"Failed to resolve stream URL for video_id: {video_id}"
                    )

            # Check if URL needs refresh
            elif self._is_url_expired(updated_at):
                logger.info(f"[PROXY] URL expired for {video_id}, attempting refresh")
                try:
                    stream_url = await self._refresh_stream_url(video_id)
                    # Update TrackStore with new URL
                    self.track_store.update_stream_url(video_id, stream_url)
                    logger.info(f"[PROXY] URL refresh successful for {video_id}")
                except URLRefreshError as e:
                    logger.error(f"[PROXY] URL refresh failed for {video_id}: {e}")
                    # Continue with old URL - it might still work
                    logger.warning(f"[PROXY] Attempting to use potentially expired URL for {video_id}")

            logger.info(
                f"[PROXY] Stream request: video_id={video_id}, client={client_ip}, "
                f"track={icy_name}"
            )

            # Return HTTP 307 redirect to direct YouTube URL
            # This allows MPD to stream directly from YouTube while we handle URL resolution/refresh
            logger.debug(f"[PROXY] Redirecting to YouTube URL for {video_id}")
            return web.HTTPTemporaryRedirect(stream_url)

        except web.HTTPException:
            # Re-raise HTTP exceptions (they're already properly formatted)
            raise
        except Exception as e:
            logger.exception(f"[PROXY] Unexpected error handling proxy request for {video_id}: {e}")
            raise web.HTTPInternalServerError(
                text=f"Unexpected error handling proxy request"
            )
        finally:
            # Decrement connection counter
            async with self._connection_lock:
                self._active_connections -= 1
                logger.debug(
                    f"[PROXY] Connection closed for {video_id} "
                    f"({self._active_connections}/{self.max_concurrent_streams} active)"
                )


    async def __aenter__(self) -> "ICYProxyServer":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.stop()
