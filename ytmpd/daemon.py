"""Sync daemon for ytmpd - periodically syncs YouTube Music playlists to MPD.

This module implements the YTMPDaemon class which coordinates YouTube Music
playlist syncing to MPD, with support for periodic auto-sync and manual triggers.
"""

import asyncio
import json
import logging
import signal
import socket
import threading
import time
from datetime import UTC, datetime
from typing import Any

from ytmpd.config import get_config_dir, load_config
from ytmpd.cookie_extract import FirefoxCookieExtractor
from ytmpd.exceptions import CookieExtractionError, MPDConnectionError
from ytmpd.history_reporter import HistoryReporter
from ytmpd.icy_proxy import ICYProxyServer
from ytmpd.mpd_client import MPDClient
from ytmpd.notify import send_notification
from ytmpd.stream_resolver import StreamResolver
from ytmpd.sync_engine import SyncEngine
from ytmpd.track_store import TrackStore
from ytmpd.ytmusic import YTMusicClient

logger = logging.getLogger(__name__)


class YTMPDaemon:
    """Sync daemon that periodically syncs YouTube Music playlists to MPD.

    The daemon:
    - Initializes sync components (YTMusicClient, MPDClient, StreamResolver, SyncEngine)
    - Runs periodic sync loop in background thread
    - Listens for manual sync triggers via Unix socket
    - Persists sync state between runs
    - Handles signals for graceful shutdown and config reload
    """

    def __init__(self):
        """Initialize the daemon with all sync components."""
        logger.info("Initializing ytmpd sync daemon...")

        # Load configuration
        self.config = load_config()
        logger.info("Configuration loaded")

        # Get auth file path (browser.json or oauth.json)
        config_dir = get_config_dir()
        browser_auth = config_dir / "browser.json"
        oauth_auth = config_dir / "oauth.json"

        # Prefer browser.json if it exists, fall back to oauth.json
        if browser_auth.exists():
            auth_file = browser_auth
            logger.info("Using browser.json for authentication")
        elif oauth_auth.exists():
            auth_file = oauth_auth
            logger.info("Using oauth.json for authentication")
        else:
            raise FileNotFoundError(
                "No authentication file found. Please create either:\n"
                f"  - {browser_auth} (recommended, via ytmusicapi setup_browser)\n"
                f"  - {oauth_auth} (via ytmusicapi setup_oauth)"
            )

        # Initialize components
        try:
            self.ytmusic_client = YTMusicClient(auth_file=auth_file)
            self.mpd_client = MPDClient(
                socket_path=self.config["mpd_socket_path"],
                playlist_directory=self.config.get("mpd_playlist_directory"),
            )
            # Persistent cache file for stream URLs
            cache_file = get_config_dir() / "stream_cache.json"

            self.stream_resolver = StreamResolver(
                cache_hours=self.config["stream_cache_hours"],
                should_stop_callback=lambda: not self._running,
                cache_file=str(cache_file),
            )

            # Initialize proxy components if enabled
            self.track_store: TrackStore | None = None
            self.proxy_server: ICYProxyServer | None = None
            self.proxy_config: dict[str, Any] | None = None

            if self.config.get("proxy_enabled", True):
                logger.info("Initializing ICY proxy server...")
                self.track_store = TrackStore(self.config["proxy_track_mapping_db"])
                self.proxy_server = ICYProxyServer(
                    track_store=self.track_store,
                    stream_resolver=self.stream_resolver,
                    host=self.config["proxy_host"],
                    port=self.config["proxy_port"],
                )
                self.proxy_config = {
                    "enabled": True,
                    "host": self.config["proxy_host"],
                    "port": self.config["proxy_port"],
                }
                logger.info(
                    f"Proxy server initialized at "
                    f"{self.config['proxy_host']}:{self.config['proxy_port']} "
                    f"with URL refresh support and YouTube Premium auth"
                )

            self.sync_engine = SyncEngine(
                ytmusic_client=self.ytmusic_client,
                mpd_client=self.mpd_client,
                stream_resolver=self.stream_resolver,
                playlist_prefix=self.config["playlist_prefix"],
                track_store=self.track_store,
                proxy_config=self.proxy_config,
                should_stop_callback=lambda: not self._running,
                playlist_format=self.config.get("playlist_format", "m3u"),
                mpd_music_directory=self.config.get("mpd_music_directory"),
                sync_liked_songs=self.config.get("sync_liked_songs", True),
                liked_songs_playlist_name=self.config.get(
                    "liked_songs_playlist_name", "Liked Songs"
                ),
                like_indicator=self.config.get(
                    "like_indicator", {"enabled": False, "tag": "+1", "alignment": "right"}
                ),
            )
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise

        # State management
        self.state_file = get_config_dir() / "sync_state.json"
        self.state = self._load_state()

        # Runtime control
        self._running = False
        self._sync_thread: threading.Thread | None = None
        self._socket_thread: threading.Thread | None = None
        self._proxy_thread: threading.Thread | None = None
        self._auto_auth_thread: threading.Thread | None = None
        self._sync_in_progress = False
        self._sync_lock = threading.Lock()

        # Socket for manual triggers
        self.sync_socket_path = get_config_dir() / "sync_socket"

        # Async event loop for proxy server (if enabled)
        self._proxy_loop: asyncio.AbstractEventLoop | None = None
        self._proxy_shutdown_event: asyncio.Event | None = None

        # Auto-auth configuration
        self.auto_auth_config = self.config.get("auto_auth", {})
        self._auto_auth_enabled = self.auto_auth_config.get("enabled", False)
        self._auto_auth_shutdown = threading.Event()
        self._last_reactive_refresh: float = 0.0
        self._reactive_refresh_cooldown: float = 300.0  # 5 minutes

        if self._auto_auth_enabled:
            logger.info("Auto-auth enabled (browser: %s)", self.auto_auth_config.get("browser"))
        else:
            logger.info("Auto-auth disabled")

        # History reporting
        self._history_reporter: HistoryReporter | None = None
        self._history_thread: threading.Thread | None = None
        self._history_shutdown = threading.Event()
        history_config = self.config.get("history_reporting", {})
        if history_config.get("enabled", False) and self.track_store is not None:
            self._history_reporter = HistoryReporter(
                mpd_socket_path=self.config["mpd_socket_path"],
                ytmusic=self.ytmusic_client,
                track_store=self.track_store,
                proxy_config=self.proxy_config or {},
                min_play_seconds=history_config.get("min_play_seconds", 30),
            )
            logger.info(
                "History reporting enabled (min_play_seconds=%d)",
                history_config.get("min_play_seconds", 30),
            )
        else:
            logger.info("History reporting disabled")

        logger.info("Daemon components initialized")

    def run(self) -> None:
        """Main daemon loop - starts all background tasks and blocks until shutdown."""
        logger.info("Starting ytmpd sync daemon...")

        # Connect to MPD
        try:
            self.mpd_client.connect()
            logger.info("Connected to MPD")
        except MPDConnectionError as e:
            logger.error(f"Failed to connect to MPD: {e}")
            raise

        self._running = True
        self.state["daemon_start_time"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self._save_state()

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGHUP, self._signal_handler)

        # Start background threads (daemon=True allows process to exit even if threads are stuck)
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._socket_thread = threading.Thread(target=self._listen_for_triggers, daemon=True)

        self._sync_thread.start()
        self._socket_thread.start()

        # Start proxy server if enabled
        if self.proxy_server:
            logger.info("Starting ICY proxy server...")
            self._proxy_thread = threading.Thread(target=self._run_proxy_server, daemon=True)
            self._proxy_thread.start()

        # Start auto-auth refresh thread if enabled
        if self._auto_auth_enabled:
            logger.info("Starting auto-auth refresh thread...")
            self._auto_auth_thread = threading.Thread(target=self._auto_auth_loop, daemon=True)
            self._auto_auth_thread.start()

        # Start history reporting thread if enabled (after proxy so URLs resolve)
        if self._history_reporter is not None:
            self._history_thread = threading.Thread(
                target=self._history_loop,
                name="history-reporter",
                daemon=True,
            )
            self._history_thread.start()
            logger.info("History reporting thread started")

        logger.info("ytmpd daemon started successfully")

        # Perform initial sync immediately
        if self.config.get("enable_auto_sync", True):
            logger.info("Triggering initial sync...")
            self._perform_sync()

        # Keep main thread alive
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
            self._running = False

        # Cleanup after main loop exits
        logger.info("Main loop exited, cleaning up...")
        sync_alive = self._sync_thread.is_alive() if self._sync_thread else None
        socket_alive = self._socket_thread.is_alive() if self._socket_thread else None
        proxy_alive = self._proxy_thread.is_alive() if self._proxy_thread else None
        logger.debug(
            f"Threads alive: sync={sync_alive}, socket={socket_alive}, proxy={proxy_alive}"
        )
        self.stop()

    def stop(self) -> None:
        """Stop the daemon gracefully."""
        if not self._running:
            logger.debug("Stop called but daemon is already stopped")
            return

        logger.info("Stopping ytmpd daemon...")
        self._running = False

        # Signal history reporter to stop
        if self._history_thread is not None:
            logger.info("Stopping history reporter...")
            self._history_shutdown.set()
            self._history_thread.join(timeout=5)
            if self._history_thread.is_alive():
                logger.warning("History reporter thread did not stop in time")

        # Signal auto-auth thread to stop
        self._auto_auth_shutdown.set()

        # Note: Sync will detect _running=False and cancel itself gracefully
        if self._sync_in_progress:
            logger.info("Sync in progress will be cancelled...")

        # Cleanup socket
        if self.sync_socket_path.exists():
            try:
                self.sync_socket_path.unlink()
            except Exception as e:
                logger.warning(f"Error removing socket file: {e}")

        # Disconnect from MPD
        try:
            self.mpd_client.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting from MPD: {e}")

        # Stop proxy server if enabled
        if self.proxy_server and self._proxy_loop:
            logger.info("Stopping ICY proxy server...")
            try:
                # Signal the proxy server to shut down
                if self._proxy_shutdown_event:

                    def set_shutdown_event():
                        if self._proxy_shutdown_event:
                            self._proxy_shutdown_event.set()

                    self._proxy_loop.call_soon_threadsafe(set_shutdown_event)

                # Wait for proxy thread to finish (10s timeout for HTTP cleanup)
                if self._proxy_thread and self._proxy_thread.is_alive():
                    logger.debug("Waiting for proxy thread to stop...")
                    self._proxy_thread.join(timeout=10)
                    if self._proxy_thread.is_alive():
                        logger.warning("Proxy thread did not stop within 10s timeout")
                    else:
                        logger.info("Proxy thread stopped successfully")
            except Exception as e:
                logger.warning(f"Error stopping proxy server: {e}")

        # Close TrackStore database connection
        if self.track_store:
            try:
                self.track_store.close()
                logger.info("TrackStore closed")
            except Exception as e:
                logger.warning(f"Error closing TrackStore: {e}")

        # Wait for threads to finish
        if self._sync_thread and self._sync_thread.is_alive():
            logger.debug("Waiting for sync thread to stop...")
            self._sync_thread.join(timeout=5)
            if self._sync_thread.is_alive():
                logger.warning("Sync thread did not stop within timeout")

        if self._socket_thread and self._socket_thread.is_alive():
            logger.debug("Waiting for socket thread to stop...")
            self._socket_thread.join(timeout=2)
            if self._socket_thread.is_alive():
                logger.warning("Socket thread did not stop within timeout")

        # Final check - log any threads still alive
        threads_alive = []
        if self._sync_thread and self._sync_thread.is_alive():
            threads_alive.append("sync")
        if self._socket_thread and self._socket_thread.is_alive():
            threads_alive.append("socket")
        if self._proxy_thread and self._proxy_thread.is_alive():
            threads_alive.append("proxy")
        if self._auto_auth_thread and self._auto_auth_thread.is_alive():
            threads_alive.append("auto_auth")
        if self._history_thread and self._history_thread.is_alive():
            threads_alive.append("history")

        if threads_alive:
            logger.warning(f"Daemon stopping with threads still alive: {', '.join(threads_alive)}")
            logger.warning("Process will exit (threads are daemon threads)")
        else:
            logger.info("All threads stopped cleanly")

        logger.info("ytmpd daemon stopped")

    def _sync_loop(self) -> None:
        """Background thread for periodic sync."""
        logger.info("Starting periodic sync loop")

        if not self.config.get("enable_auto_sync", True):
            logger.info("Auto-sync disabled, periodic sync loop inactive")
            return

        interval_minutes = self.config["sync_interval_minutes"]
        interval_seconds = interval_minutes * 60

        try:
            while self._running:
                # Sleep in small intervals to allow quick shutdown
                for _ in range(int(interval_seconds)):
                    if not self._running:
                        break
                    time.sleep(1)

                if self._running:
                    self._perform_sync()

        except Exception as e:
            logger.error(f"Error in sync loop: {e}", exc_info=True)

        logger.info("Periodic sync loop stopped")

    def _run_proxy_server(self) -> None:
        """Background thread for running the async proxy server."""
        logger.info("Starting proxy server thread")

        try:
            # Create new event loop for this thread
            self._proxy_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._proxy_loop)

            # Run proxy server in this loop
            async def run_server():
                """Async wrapper to run the proxy server."""
                # Create shutdown event in the async context
                self._proxy_shutdown_event = asyncio.Event()

                async with self.proxy_server:
                    logger.info(
                        f"Proxy server running at http://{self.config['proxy_host']}:{self.config['proxy_port']}"
                    )
                    # Keep server running until shutdown event is set
                    await self._proxy_shutdown_event.wait()

            self._proxy_loop.run_until_complete(run_server())

        except Exception as e:
            logger.error(f"Error in proxy server thread: {e}", exc_info=True)

        finally:
            if self._proxy_loop:
                # Cancel all pending tasks
                try:
                    pending = asyncio.all_tasks(self._proxy_loop)
                    for task in pending:
                        task.cancel()
                    # Wait for all tasks to be cancelled
                    if pending:
                        self._proxy_loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                except Exception as e:
                    logger.warning(f"Error cancelling tasks: {e}")

                # Close the loop
                self._proxy_loop.close()
            logger.info("Proxy server thread stopped")

    def _auto_auth_loop(self) -> None:
        """Background thread for periodic auto-auth refresh."""
        logger.info("Starting auto-auth refresh loop")

        interval_hours = self.auto_auth_config.get("refresh_interval_hours", 12)
        interval_seconds = interval_hours * 3600

        try:
            while self._running:
                # Wait for the configured interval (or shutdown signal)
                if self._auto_auth_shutdown.wait(timeout=interval_seconds):
                    # Shutdown was signalled
                    break

                if not self._running:
                    break

                logger.info("Proactive auto-auth refresh triggered")
                success = self._attempt_auto_refresh()
                if success:
                    logger.info("Proactive auto-auth refresh succeeded")
                else:
                    logger.warning("Proactive auto-auth refresh failed")
                    send_notification(
                        "ytmpd: Auth Refresh Failed",
                        "Proactive cookie refresh failed. "
                        "Open YouTube Music in Firefox to refresh cookies.",
                        urgency="normal",
                    )

        except Exception as e:
            logger.error(f"Error in auto-auth loop: {e}", exc_info=True)

        logger.info("Auto-auth refresh loop stopped")

    def _history_loop(self) -> None:
        """Run history reporter in background thread."""
        try:
            assert self._history_reporter is not None
            logger.info(
                "History reporting started (min_play_seconds=%d)",
                self.config["history_reporting"]["min_play_seconds"],
            )
            self._history_reporter.run(self._history_shutdown)
        except Exception as e:
            logger.error("History reporter crashed: %s", e, exc_info=True)
        finally:
            logger.info("History reporting stopped")

    def _attempt_auto_refresh(self) -> bool:
        """Attempt to refresh authentication via cookie extraction.

        Returns:
            True if refresh succeeded, False otherwise.
        """
        config_dir = get_config_dir()
        browser_json = config_dir / "browser.json"

        try:
            extractor = FirefoxCookieExtractor(
                browser=self.auto_auth_config.get("browser", "firefox-dev"),
                profile=self.auto_auth_config.get("profile"),
                container=self.auto_auth_config.get("container"),
            )

            # Write to a temp file first, then rename for atomicity
            tmp_path = browser_json.with_suffix(".json.tmp")
            extractor.build_browser_json(tmp_path)
            tmp_path.rename(browser_json)

            # Reinitialize the ytmusicapi client
            if not self.ytmusic_client.refresh_auth(browser_json):
                self.state["auto_refresh_failures"] = self.state.get("auto_refresh_failures", 0) + 1
                self._save_state()
                return False

            # Update state on success
            self.state["last_auto_refresh"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            self.state["auto_refresh_failures"] = 0
            self._save_state()
            return True

        except CookieExtractionError as e:
            logger.error(f"Cookie extraction failed: {e}")
            self.state["auto_refresh_failures"] = self.state.get("auto_refresh_failures", 0) + 1
            self._save_state()
            return False
        except Exception as e:
            logger.error(f"Auto-auth refresh failed: {e}", exc_info=True)
            self.state["auto_refresh_failures"] = self.state.get("auto_refresh_failures", 0) + 1
            self._save_state()
            return False

    def _perform_sync(self) -> None:
        """Execute sync and update state."""
        # Skip if sync already in progress
        if self._sync_in_progress:
            logger.warning("Sync already in progress, skipping")
            return

        with self._sync_lock:
            self._sync_in_progress = True
            logger.info("Starting sync...")
            start_time = time.time()

            try:
                # Perform sync
                result = self.sync_engine.sync_all_playlists()

                # Update state
                self.state["last_sync"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
                self.state["last_sync_result"] = {
                    "success": result.success,
                    "playlists_synced": result.playlists_synced,
                    "playlists_failed": result.playlists_failed,
                    "tracks_added": result.tracks_added,
                    "tracks_failed": result.tracks_failed,
                    "duration_seconds": result.duration_seconds,
                    "errors": result.errors,
                }
                self._save_state()

                # Log result
                if result.success:
                    logger.info(
                        f"Sync completed successfully: "
                        f"{result.playlists_synced} playlists, "
                        f"{result.tracks_added} tracks, "
                        f"{result.duration_seconds:.1f}s"
                    )
                else:
                    logger.warning(
                        f"Sync completed with errors: "
                        f"{result.playlists_synced} playlists synced, "
                        f"{result.playlists_failed} playlists failed, "
                        f"{len(result.errors)} errors"
                    )
                    for error in result.errors:
                        logger.error(f"  - {error}")

            except Exception as e:
                logger.error(f"Sync failed with exception: {e}", exc_info=True)

                # Attempt reactive auto-refresh on auth-related failures
                is_auth_error = any(
                    kw in str(e).lower()
                    for kw in ("auth", "credential", "unauthorized", "forbidden")
                )
                if is_auth_error and self._auto_auth_enabled:
                    now = time.time()
                    if now - self._last_reactive_refresh >= self._reactive_refresh_cooldown:
                        logger.info("Attempting reactive auto-auth refresh after auth failure")
                        self._last_reactive_refresh = now
                        if self._attempt_auto_refresh():
                            logger.info("Reactive refresh succeeded, retrying sync")
                            try:
                                result = self.sync_engine.sync_all_playlists()
                                self.state["last_sync"] = (
                                    datetime.now(UTC).isoformat().replace("+00:00", "Z")
                                )
                                self.state["last_sync_result"] = {
                                    "success": result.success,
                                    "playlists_synced": result.playlists_synced,
                                    "playlists_failed": result.playlists_failed,
                                    "tracks_added": result.tracks_added,
                                    "tracks_failed": result.tracks_failed,
                                    "duration_seconds": result.duration_seconds,
                                    "errors": result.errors,
                                }
                                self._save_state()
                                return
                            except Exception as retry_e:
                                logger.error(f"Sync retry after refresh also failed: {retry_e}")
                                e = retry_e  # Use the retry error for state
                        else:
                            logger.error("Reactive auto-auth refresh failed")
                            send_notification(
                                "ytmpd: Authentication Failed",
                                "Auto-refresh failed. "
                                "Open YouTube Music in Firefox to refresh cookies.",
                                urgency="critical",
                            )
                    else:
                        logger.info("Skipping reactive refresh (cooldown active)")

                # Update state with failure
                self.state["last_sync"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
                self.state["last_sync_result"] = {
                    "success": False,
                    "playlists_synced": 0,
                    "playlists_failed": 0,
                    "tracks_added": 0,
                    "tracks_failed": 0,
                    "duration_seconds": time.time() - start_time,
                    "errors": [str(e)],
                }
                self._save_state()

            finally:
                self._sync_in_progress = False

    def _listen_for_triggers(self) -> None:
        """Listen for manual sync commands via Unix socket."""
        logger.info(f"Starting socket listener on {self.sync_socket_path}")

        # Remove old socket if it exists
        if self.sync_socket_path.exists():
            try:
                self.sync_socket_path.unlink()
            except Exception as e:
                logger.error(f"Error removing old socket: {e}")
                return

        # Create socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(str(self.sync_socket_path))
            sock.listen(5)
            sock.settimeout(1.0)  # Allow checking _running flag periodically
        except Exception as e:
            logger.error(f"Error creating socket: {e}")
            return

        logger.info("Socket listener started")

        try:
            while self._running:
                try:
                    conn, _ = sock.accept()
                except TimeoutError:
                    continue
                except Exception as e:
                    if self._running:
                        logger.error(f"Socket accept error: {e}")
                    continue

                # Handle connection in separate thread
                threading.Thread(
                    target=self._handle_socket_connection, args=(conn,), daemon=True
                ).start()

        finally:
            sock.close()
            if self.sync_socket_path.exists():
                try:
                    self.sync_socket_path.unlink()
                except Exception:
                    pass

        logger.info("Socket listener stopped")

    def _handle_socket_connection(self, conn: socket.socket) -> None:
        """Handle a single socket connection.

        Args:
            conn: Socket connection to handle.
        """
        try:
            # Set timeout to prevent indefinite blocking (5 seconds)
            conn.settimeout(5.0)

            # Read command (up to 1KB)
            data = conn.recv(1024).decode("utf-8").strip()
            if not data:
                return

            logger.debug(f"Received command: {data}")

            # Parse command
            parts = data.split()
            cmd = parts[0] if parts else ""

            # Handle commands
            if cmd == "sync":
                response = self._cmd_sync()
            elif cmd == "status":
                response = self._cmd_status()
            elif cmd == "list":
                response = self._cmd_list()
            elif cmd == "quit":
                response = self._cmd_quit()
            elif cmd == "radio":
                # Extract video_id argument if provided
                video_id = parts[1] if len(parts) > 1 else None
                response = self._cmd_radio(video_id)
            elif cmd == "search":
                # Extract search query (everything after "search")
                query = " ".join(parts[1:]) if len(parts) > 1 else None
                response = self._cmd_search(query)
            elif cmd == "play":
                # Extract video_id argument
                video_id = parts[1] if len(parts) > 1 else None
                response = self._cmd_play(video_id)
            elif cmd == "queue":
                # Extract video_id argument
                video_id = parts[1] if len(parts) > 1 else None
                response = self._cmd_queue(video_id)
            else:
                response = {"success": False, "error": f"Unknown command: {cmd}"}

            # Send response
            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

        except TimeoutError:
            logger.warning("Socket connection timed out waiting for command")
            try:
                error_response = {"success": False, "error": "Connection timeout"}
                conn.sendall((json.dumps(error_response) + "\n").encode("utf-8"))
            except Exception:
                pass
        except BrokenPipeError:
            # Client disconnected before we could send response - this is fine
            logger.debug("Client disconnected before response could be sent (broken pipe)")
        except Exception as e:
            logger.error(f"Error handling socket connection: {e}", exc_info=True)
            try:
                error_response = {"success": False, "error": str(e)}
                conn.sendall((json.dumps(error_response) + "\n").encode("utf-8"))
            except (BrokenPipeError, ConnectionResetError):
                # Client already gone, can't send error response
                pass
            except Exception:
                pass

        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _cmd_sync(self) -> dict[str, Any]:
        """Handle 'sync' command - trigger immediate sync."""
        logger.info("Manual sync triggered via socket")

        # Trigger sync in background
        threading.Thread(target=self._perform_sync, daemon=True).start()

        return {
            "success": True,
            "message": "Sync triggered",
        }

    def _cmd_status(self) -> dict[str, Any]:
        """Handle 'status' command - return sync status."""
        last_sync_result = self.state.get("last_sync_result", {})

        # Check authentication status
        auth_valid, auth_error = self.ytmusic_client.is_authenticated()

        return {
            "success": True,
            "last_sync": self.state.get("last_sync"),
            "daemon_start_time": self.state.get("daemon_start_time"),
            "sync_in_progress": self._sync_in_progress,
            "playlists_synced": last_sync_result.get("playlists_synced", 0),
            "playlists_failed": last_sync_result.get("playlists_failed", 0),
            "tracks_added": last_sync_result.get("tracks_added", 0),
            "tracks_failed": last_sync_result.get("tracks_failed", 0),
            "errors": last_sync_result.get("errors", []),
            "last_sync_success": last_sync_result.get("success", False),
            "auth_valid": auth_valid,
            "auth_error": auth_error,
            "auto_auth_enabled": self._auto_auth_enabled,
            "last_auto_refresh": self.state.get("last_auto_refresh"),
            "auto_refresh_failures": self.state.get("auto_refresh_failures", 0),
        }

    def _cmd_list(self) -> dict[str, Any]:
        """Handle 'list' command - list YouTube playlists."""
        try:
            playlists = self.ytmusic_client.get_user_playlists()
            playlist_data = [
                {"name": p.name, "id": p.id, "track_count": p.track_count} for p in playlists
            ]
            return {"success": True, "playlists": playlist_data}
        except Exception as e:
            logger.error(f"Error listing playlists: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _cmd_quit(self) -> dict[str, Any]:
        """Handle 'quit' command - shutdown daemon."""
        logger.info("Shutdown requested via socket")
        threading.Thread(target=self.stop, daemon=True).start()
        return {"success": True, "message": "Shutting down"}

    def _validate_video_id(self, video_id: str | None) -> tuple[bool, str | None]:
        """Validate YouTube video ID format.

        Args:
            video_id: Video ID to validate.

        Returns:
            Tuple of (is_valid, error_message).
            If valid, error_message is None.
        """
        if video_id is None:
            return False, "Missing video ID"

        if len(video_id) != 11:
            return False, "Invalid video ID format (must be 11 characters)"

        # YouTube video IDs are alphanumeric plus - and _
        if not all(c.isalnum() or c in "-_" for c in video_id):
            return False, "Invalid video ID format (invalid characters)"

        return True, None

    def _extract_video_id_from_url(self, url: str) -> str | None:
        """Extract YouTube video ID from proxy URL.

        Proxy URLs follow pattern: http://localhost:PORT/proxy/VIDEO_ID

        Args:
            url: URL to extract video ID from.

        Returns:
            11-character video ID or None if not a proxy URL.
        """
        if not url:
            return None

        # Match pattern: */proxy/{video_id}
        import re

        match = re.search(r"/proxy/([A-Za-z0-9_-]{11})$", url)
        return match.group(1) if match else None

    def _cmd_radio(self, video_id: str | None) -> dict[str, Any]:
        """Handle 'radio' command - generate radio playlist.

        Args:
            video_id: YouTube video ID, or None to use current track.

        Returns:
            Response dict with success status and track count.
        """
        logger.info(f"Radio command received: video_id={video_id}")

        try:
            # If no video_id provided, extract from current MPD track
            if video_id is None:
                try:
                    current = self.mpd_client.currentsong()
                except Exception as e:
                    logger.error(f"Failed to get current song from MPD: {e}")
                    return {"success": False, "error": "Failed to get current track"}

                if not current:
                    return {"success": False, "error": "No track currently playing"}

                # Extract video ID from proxy URL
                file_url = current.get("file", "")
                video_id = self._extract_video_id_from_url(file_url)

                if not video_id:
                    return {"success": False, "error": "Current track is not a YouTube track"}

                logger.info(f"Extracted video ID from current track: {video_id}")
            else:
                # Validate provided video_id
                is_valid, error = self._validate_video_id(video_id)
                if not is_valid:
                    return {"success": False, "error": error}

            # Get radio playlist from YouTube Music
            logger.info(f"Fetching radio playlist for video ID: {video_id}")
            radio_tracks = self.ytmusic_client._client.get_watch_playlist(
                videoId=video_id, radio=True, limit=self.config.get("radio_playlist_limit", 25)
            )

            if not radio_tracks:
                return {"success": False, "error": "Failed to generate radio playlist"}

            # Extract video IDs from radio tracks
            # get_watch_playlist returns a dict with "tracks" key
            tracks = (
                radio_tracks.get("tracks", []) if isinstance(radio_tracks, dict) else radio_tracks
            )
            video_ids = []
            for track in tracks:
                if isinstance(track, dict) and "videoId" in track:
                    video_ids.append(track["videoId"])

            if not video_ids:
                return {"success": False, "error": "No tracks found in radio playlist"}

            logger.info(f"Fetched {len(video_ids)} tracks from radio playlist")

            # Build TrackWithMetadata objects for playlist creation
            from ytmpd.mpd_client import TrackWithMetadata

            track_objects = []

            # Check if proxy is enabled for on-demand resolution
            lazy_resolution = self.proxy_config and self.proxy_config.get("enabled", False)

            if lazy_resolution:
                logger.info(
                    f"Proxy enabled - skipping URL resolution for {len(video_ids)} tracks "
                    f"(will resolve on-demand when played)"
                )

            for track in tracks:
                if isinstance(track, dict):
                    vid = track.get("videoId")
                    if vid and vid in video_ids:
                        # Extract artist info
                        artists = track.get("artists", [])
                        if isinstance(artists, list) and artists:
                            artist = ", ".join(
                                [
                                    a.get("name", "")
                                    for a in artists
                                    if isinstance(a, dict) and a.get("name")
                                ]
                            )
                        else:
                            artist = "Unknown Artist"

                        title = track.get("title", "Unknown Title")
                        duration_seconds = track.get("duration_seconds")

                        # Save track metadata to TrackStore for on-demand resolution
                        if lazy_resolution and self.track_store:
                            try:
                                self.track_store.add_track(
                                    video_id=vid,
                                    stream_url=None,  # Will be resolved on-demand by proxy
                                    title=title,
                                    artist=artist,
                                )
                                logger.debug(f"Saved track metadata for lazy resolution: {vid}")
                            except Exception as e:
                                logger.warning(f"Failed to save track metadata for {vid}: {e}")

                        track_objects.append(
                            TrackWithMetadata(
                                url="",  # Proxy will generate URL on-demand
                                title=title,
                                artist=artist,
                                video_id=vid,
                                duration_seconds=duration_seconds,
                            )
                        )

            if not track_objects:
                return {"success": False, "error": "No valid tracks to add to playlist"}

            # Build liked video ID set for like indicator
            like_indicator = self.config.get(
                "like_indicator", {"enabled": False, "tag": "+1", "alignment": "right"}
            )
            liked_video_ids: set[str] = set()
            if like_indicator.get("enabled", False):
                try:
                    liked_tracks = self.ytmusic_client.get_liked_songs()
                    if liked_tracks:
                        liked_video_ids = {t.video_id for t in liked_tracks}
                except Exception as e:
                    logger.warning(f"Failed to fetch liked songs for like indicator: {e}")

            # Create MPD playlist
            playlist_name = "YT: Radio"
            logger.info(f"Creating playlist '{playlist_name}' with {len(track_objects)} tracks")
            self.mpd_client.create_or_replace_playlist(
                name=playlist_name,
                tracks=track_objects,
                proxy_config=self.proxy_config,
                playlist_format=self.config.get("playlist_format", "m3u"),
                mpd_music_directory=self.config.get("mpd_music_directory"),
                liked_video_ids=liked_video_ids,
                like_indicator=like_indicator,
            )

            logger.info(f"Radio playlist created successfully: {len(track_objects)} tracks")
            return {
                "success": True,
                "message": f"Radio playlist created: {len(track_objects)} tracks",
                "tracks": len(track_objects),
                "playlist": playlist_name,
            }

        except Exception as e:
            logger.error(f"Radio generation failed: {e}")
            return {"success": False, "error": f"Radio generation failed: {str(e)}"}

    def _cmd_search(self, query: str | None) -> dict[str, Any]:
        """Handle 'search' command - search YouTube Music.

        Args:
            query: Search query string.

        Returns:
            Response dict with success status and search results.
        """
        logger.info(f"Search command received: query={query}")

        try:
            # Validate query
            if query is None or not query.strip():
                return {"success": False, "error": "Empty search query"}

            # Search YouTube Music (limit to 10 results)
            logger.info(f"Searching YouTube Music for: {query}")
            results = self.ytmusic_client.search(query, limit=10)

            if not results:
                return {"success": True, "results": [], "count": 0}

            # Format results
            formatted = []
            for idx, track in enumerate(results, 1):
                formatted.append(
                    {
                        "number": idx,
                        "video_id": track.get("video_id", ""),
                        "title": track.get("title", "Unknown"),
                        "artist": track.get("artist", "Unknown Artist"),
                        "duration": self._format_duration(track.get("duration", 0)),
                    }
                )

            logger.info(f"Found {len(formatted)} results for: {query}")
            return {"success": True, "results": formatted, "count": len(formatted)}

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return {"success": False, "error": f"Search failed: {str(e)}"}

    def _cmd_play(self, video_id: str | None) -> dict[str, Any]:
        """Handle 'play' command - play track immediately.

        Clears the current queue, adds the track, and starts playback.

        Args:
            video_id: YouTube video ID.

        Returns:
            Response dict with success status and track info.
        """
        logger.info(f"Play command received: video_id={video_id}")

        try:
            # Validate video_id
            is_valid, error = self._validate_video_id(video_id)
            if not is_valid:
                return {"success": False, "error": error}

            # Get track metadata
            track_info = self._get_track_info(video_id)

            # Check if proxy is enabled for on-demand resolution
            lazy_resolution = self.proxy_config and self.proxy_config.get("enabled", False)

            if lazy_resolution:
                # Use proxy URL directly (stream will be resolved on-demand)
                proxy_port = self.proxy_config.get("port", 6602)
                proxy_url = f"http://localhost:{proxy_port}/proxy/{video_id}"
                logger.info(f"Using proxy URL for on-demand resolution: {proxy_url}")
            else:
                # Resolve stream URL now
                logger.info(f"Resolving stream URL for video ID: {video_id}")
                proxy_url = self.stream_resolver.resolve_video_id(video_id)
                if not proxy_url:
                    return {"success": False, "error": "Failed to resolve stream URL"}

            # Clear queue, add track, start playback
            logger.info(f"Playing track: {track_info['title']} - {track_info['artist']}")
            self.mpd_client._client.clear()
            self.mpd_client._client.add(proxy_url)
            self.mpd_client._client.play()

            return {
                "success": True,
                "message": f"Now playing: {track_info['title']} - {track_info['artist']}",
                "title": track_info["title"],
                "artist": track_info["artist"],
            }

        except Exception as e:
            logger.error(f"Play command failed: {e}")
            return {"success": False, "error": f"Play failed: {str(e)}"}

    def _cmd_queue(self, video_id: str | None) -> dict[str, Any]:
        """Handle 'queue' command - add track to queue.

        Adds track to MPD queue without interrupting current playback.

        Args:
            video_id: YouTube video ID.

        Returns:
            Response dict with success status and track info.
        """
        logger.info(f"Queue command received: video_id={video_id}")

        try:
            # Validate video_id
            is_valid, error = self._validate_video_id(video_id)
            if not is_valid:
                return {"success": False, "error": error}

            # Get track metadata
            track_info = self._get_track_info(video_id)

            # Check if proxy is enabled for on-demand resolution
            lazy_resolution = self.proxy_config and self.proxy_config.get("enabled", False)

            if lazy_resolution:
                # Use proxy URL directly (stream will be resolved on-demand)
                proxy_port = self.proxy_config.get("port", 6602)
                proxy_url = f"http://localhost:{proxy_port}/proxy/{video_id}"
                logger.info(f"Using proxy URL for on-demand resolution: {proxy_url}")
            else:
                # Resolve stream URL now
                logger.info(f"Resolving stream URL for video ID: {video_id}")
                proxy_url = self.stream_resolver.resolve_video_id(video_id)
                if not proxy_url:
                    return {"success": False, "error": "Failed to resolve stream URL"}

            # Add to queue (doesn't interrupt current playback)
            logger.info(f"Adding to queue: {track_info['title']} - {track_info['artist']}")
            self.mpd_client._client.add(proxy_url)

            return {
                "success": True,
                "message": f"Added to queue: {track_info['title']} - {track_info['artist']}",
                "title": track_info["title"],
                "artist": track_info["artist"],
            }

        except Exception as e:
            logger.error(f"Queue command failed: {e}")
            return {"success": False, "error": f"Queue failed: {str(e)}"}

    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds as MM:SS.

        Args:
            seconds: Duration in seconds.

        Returns:
            Formatted duration string (e.g., "3:45").
        """
        if not seconds or seconds <= 0:
            return "Unknown"
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}:{secs:02d}"

    def _get_track_info(self, video_id: str) -> dict[str, str]:
        """Get track metadata from YouTube Music.

        Args:
            video_id: YouTube video ID.

        Returns:
            Dictionary with 'title' and 'artist' keys.
        """
        try:
            # Use YTMusicClient to search for track info by video ID
            # The search API doesn't support direct video ID lookup, so we use a workaround
            # by searching for the video ID itself (which often returns the track)
            results = self.ytmusic_client.search(video_id, limit=1)
            if results and len(results) > 0:
                track = results[0]
                return {
                    "title": track.get("title", "Unknown"),
                    "artist": track.get("artist", "Unknown Artist"),
                }
        except Exception as e:
            logger.warning(f"Failed to get track info for {video_id}: {e}")

        # Fallback to unknown metadata
        return {"title": "Unknown", "artist": "Unknown Artist"}

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle signals.

        Args:
            signum: Signal number.
            frame: Current stack frame.
        """
        sig_name = signal.Signals(signum).name
        logger.info(f"Received signal: {sig_name}")

        if signum in (signal.SIGTERM, signal.SIGINT):
            # Signal shutdown - just set the flag and let main loop handle cleanup
            self._running = False
        elif signum == signal.SIGHUP:
            # Reload config and trigger sync
            logger.info("Reloading configuration...")
            try:
                self.config = load_config()
                logger.info("Configuration reloaded")
                # Trigger immediate sync
                threading.Thread(target=self._perform_sync, daemon=True).start()
            except Exception as e:
                logger.error(f"Error reloading config: {e}", exc_info=True)

    def _load_state(self) -> dict[str, Any]:
        """Load persisted state from sync_state.json.

        Returns:
            State dictionary.
        """
        default_state = {
            "last_sync": None,
            "last_sync_result": {},
            "daemon_start_time": None,
            "last_auto_refresh": None,
            "auto_refresh_failures": 0,
        }

        if not self.state_file.exists():
            logger.info("No state file found, starting fresh")
            return dict(default_state)

        try:
            with open(self.state_file) as f:
                state = json.load(f)
            # Ensure all default keys exist (for upgrades from older state files)
            for key, value in default_state.items():
                state.setdefault(key, value)
            logger.info(f"State loaded from {self.state_file}")
            return state
        except Exception as e:
            logger.warning(f"Error loading state file: {e}, starting fresh")
            return dict(default_state)

    def _save_state(self) -> None:
        """Save state to sync_state.json."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2)
            logger.debug(f"State saved to {self.state_file}")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
