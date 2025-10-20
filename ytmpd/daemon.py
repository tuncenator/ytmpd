"""Sync daemon for ytmpd - periodically syncs YouTube Music playlists to MPD.

This module implements the YTMPDaemon class which coordinates YouTube Music
playlist syncing to MPD, with support for periodic auto-sync and manual triggers.
"""

import asyncio
import json
import logging
import os
import signal
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ytmpd.config import get_config_dir, load_config
from ytmpd.exceptions import MPDConnectionError
from ytmpd.icy_proxy import ICYProxyServer
from ytmpd.mpd_client import MPDClient
from ytmpd.stream_resolver import StreamResolver
from ytmpd.sync_engine import SyncEngine, SyncResult
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
        logger.info(f"Configuration loaded")

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
                playlist_directory=self.config.get("mpd_playlist_directory")
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
                    f"Proxy server initialized at {self.config['proxy_host']}:{self.config['proxy_port']} "
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
                liked_songs_playlist_name=self.config.get("liked_songs_playlist_name", "Liked Songs"),
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
        self._sync_in_progress = False
        self._sync_lock = threading.Lock()

        # Socket for manual triggers
        self.sync_socket_path = get_config_dir() / "sync_socket"

        # Async event loop for proxy server (if enabled)
        self._proxy_loop: asyncio.AbstractEventLoop | None = None
        self._proxy_shutdown_event: asyncio.Event | None = None

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
        self.state["daemon_start_time"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._save_state()

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGHUP, self._signal_handler)

        # Start background threads (daemon=True allows process to exit even if threads are stuck)
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._socket_thread = threading.Thread(
            target=self._listen_for_triggers, daemon=True
        )

        self._sync_thread.start()
        self._socket_thread.start()

        # Start proxy server if enabled
        if self.proxy_server:
            logger.info("Starting ICY proxy server...")
            self._proxy_thread = threading.Thread(
                target=self._run_proxy_server, daemon=True
            )
            self._proxy_thread.start()

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
        logger.debug(f"Threads alive: sync={self._sync_thread.is_alive() if self._sync_thread else None}, socket={self._socket_thread.is_alive() if self._socket_thread else None}, proxy={self._proxy_thread.is_alive() if self._proxy_thread else None}")
        self.stop()

    def stop(self) -> None:
        """Stop the daemon gracefully."""
        if not self._running:
            logger.debug("Stop called but daemon is already stopped")
            return

        logger.info("Stopping ytmpd daemon...")
        self._running = False

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

                # Wait for proxy thread to finish (increased timeout to 10s for HTTP session cleanup)
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
                        self._proxy_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception as e:
                    logger.warning(f"Error cancelling tasks: {e}")

                # Close the loop
                self._proxy_loop.close()
            logger.info("Proxy server thread stopped")

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
                self.state["last_sync"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
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
                # Update state with failure
                self.state["last_sync"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
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
                except socket.timeout:
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
                # Extract search query (rest of command after "search")
                query = parts[1] if len(parts) > 1 else None
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

        except Exception as e:
            logger.error(f"Error handling socket connection: {e}", exc_info=True)
            try:
                error_response = {"success": False, "error": str(e)}
                conn.sendall((json.dumps(error_response) + "\n").encode("utf-8"))
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
        }

    def _cmd_list(self) -> dict[str, Any]:
        """Handle 'list' command - list YouTube playlists."""
        try:
            playlists = self.ytmusic_client.get_user_playlists()
            playlist_data = [
                {"name": p.name, "id": p.id, "track_count": p.track_count}
                for p in playlists
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

    def _cmd_radio(self, video_id: str | None) -> dict[str, Any]:
        """Handle 'radio' command - generate radio playlist (stub).

        Args:
            video_id: YouTube video ID, or None to use current track.

        Returns:
            Response dict with success status.
        """
        logger.info(f"Radio command received: video_id={video_id}")

        # Validate video_id if provided
        if video_id is not None:
            is_valid, error = self._validate_video_id(video_id)
            if not is_valid:
                return {"success": False, "error": error}

        return {
            "success": True,
            "message": "Command received: radio (not yet implemented)",
        }

    def _cmd_search(self, query: str | None) -> dict[str, Any]:
        """Handle 'search' command - search YouTube Music (stub).

        Args:
            query: Search query string.

        Returns:
            Response dict with success status.
        """
        logger.info(f"Search command received: query={query}")

        # Validate query
        if query is None or not query.strip():
            return {"success": False, "error": "Empty search query"}

        return {
            "success": True,
            "message": "Command received: search (not yet implemented)",
        }

    def _cmd_play(self, video_id: str | None) -> dict[str, Any]:
        """Handle 'play' command - play track immediately (stub).

        Args:
            video_id: YouTube video ID.

        Returns:
            Response dict with success status.
        """
        logger.info(f"Play command received: video_id={video_id}")

        # Validate video_id
        is_valid, error = self._validate_video_id(video_id)
        if not is_valid:
            return {"success": False, "error": error}

        return {
            "success": True,
            "message": "Command received: play (not yet implemented)",
        }

    def _cmd_queue(self, video_id: str | None) -> dict[str, Any]:
        """Handle 'queue' command - add track to queue (stub).

        Args:
            video_id: YouTube video ID.

        Returns:
            Response dict with success status.
        """
        logger.info(f"Queue command received: video_id={video_id}")

        # Validate video_id
        is_valid, error = self._validate_video_id(video_id)
        if not is_valid:
            return {"success": False, "error": error}

        return {
            "success": True,
            "message": "Command received: queue (not yet implemented)",
        }

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
        if not self.state_file.exists():
            logger.info("No state file found, starting fresh")
            return {
                "last_sync": None,
                "last_sync_result": {},
                "daemon_start_time": None,
            }

        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
            logger.info(f"State loaded from {self.state_file}")
            return state
        except Exception as e:
            logger.warning(f"Error loading state file: {e}, starting fresh")
            return {
                "last_sync": None,
                "last_sync_result": {},
                "daemon_start_time": None,
            }

    def _save_state(self) -> None:
        """Save state to sync_state.json."""
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2)
            logger.debug(f"State saved to {self.state_file}")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
