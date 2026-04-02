"""History reporting module for ytmpd.

Monitors MPD playback and reports completed plays to YouTube Music
via ytmusicapi's add_history_item(), keeping the recommendation engine
fed with listening data.
"""

import logging
import re
import threading
import time
from typing import Any

from mpd import MPDClient as MPDClientBase

from ytmpd.exceptions import MPDConnectionError
from ytmpd.track_store import TrackStore
from ytmpd.ytmusic import YTMusicClient

logger = logging.getLogger(__name__)

VIDEO_ID_RE = re.compile(r"/proxy/([A-Za-z0-9_-]{11})$")


class HistoryReporter:
    """Reports completed MPD plays back to YouTube Music.

    Maintains its own MPD connection (separate from the daemon's) because
    ``idle()`` monopolises the connection. Listens for player state changes,
    tracks playback duration (excluding pauses), and reports plays that
    exceed *min_play_seconds* to YouTube Music.

    Args:
        mpd_socket_path: Path to the MPD Unix socket (or host:port).
        ytmusic: Authenticated YTMusicClient instance.
        track_store: TrackStore for video-ID lookups.
        proxy_config: Dict with ``host``, ``port``, ``enabled`` keys.
        min_play_seconds: Minimum seconds of actual play time before a
            track is reported.  Defaults to 30.
    """

    def __init__(
        self,
        mpd_socket_path: str,
        ytmusic: YTMusicClient,
        track_store: TrackStore,
        proxy_config: dict[str, Any],
        min_play_seconds: int = 30,
    ) -> None:
        self._mpd_socket_path = mpd_socket_path
        self._ytmusic = ytmusic
        self._track_store = track_store
        self._proxy_config = proxy_config
        self._min_play_seconds = min_play_seconds

        self._mpd: MPDClientBase | None = None

        # Playback tracking state
        self._current_track_url: str | None = None
        self._current_track_start: float | None = None
        self._accumulated_play: float = 0.0
        self._pause_start: float | None = None
        self._last_state: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, shutdown_event: threading.Event) -> None:
        """Main idle loop.  Blocks until *shutdown_event* is set."""
        while not shutdown_event.is_set():
            try:
                self._connect()
                self._idle_loop(shutdown_event)
            except Exception as e:
                logger.error("History reporter error: %s", e, exc_info=True)
                self._disconnect()
                if shutdown_event.wait(timeout=5):
                    break
        self._disconnect()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        self._disconnect()
        client = MPDClientBase()
        client.timeout = 30
        try:
            if ":" in self._mpd_socket_path:
                host, port_str = self._mpd_socket_path.split(":", 1)
                client.connect(host, int(port_str))
            else:
                client.connect(self._mpd_socket_path)
            self._mpd = client
            logger.info("History reporter connected to MPD")
        except Exception as e:
            raise MPDConnectionError(f"History reporter MPD connect failed: {e}") from e

    def _disconnect(self) -> None:
        if self._mpd is not None:
            try:
                self._mpd.close()
                self._mpd.disconnect()
            except Exception:
                pass
            self._mpd = None

    # ------------------------------------------------------------------
    # Idle loop
    # ------------------------------------------------------------------

    def _idle_loop(self, shutdown_event: threading.Event) -> None:
        """Process idle events until shutdown or connection error."""
        assert self._mpd is not None

        # Snapshot current state so we have a baseline.
        self._snapshot_current_state()

        while not shutdown_event.is_set():
            try:
                self._mpd.idle("player")
            except Exception as e:
                logger.warning("MPD idle interrupted: %s", e)
                return  # outer loop will reconnect

            if shutdown_event.is_set():
                break

            try:
                self._handle_player_event()
            except Exception as e:
                logger.error("Error handling player event: %s", e, exc_info=True)

    def _snapshot_current_state(self) -> None:
        """Initialise tracking from current MPD state."""
        assert self._mpd is not None
        status = self._mpd.status()
        state = status.get("state", "stop")
        song = self._mpd.currentsong()
        file_url = song.get("file") if song else None

        self._last_state = state
        if state == "play" and file_url:
            self._current_track_url = file_url
            self._current_track_start = time.monotonic()
            self._accumulated_play = 0.0
            self._pause_start = None
        else:
            self._reset_tracking()

    def _handle_player_event(self) -> None:
        """Process a single player-state change from MPD."""
        assert self._mpd is not None
        status = self._mpd.status()
        new_state = status.get("state", "stop")
        song = self._mpd.currentsong()
        new_url = song.get("file") if song else None

        prev_state = self._last_state
        prev_url = self._current_track_url
        self._last_state = new_state

        # ---- play -> pause (same track) ----
        if prev_state == "play" and new_state == "pause" and new_url == prev_url:
            self._pause_start = time.monotonic()
            return

        # ---- pause -> play (same track = resume) ----
        if prev_state == "pause" and new_state == "play" and new_url == prev_url:
            if self._pause_start is not None and self._current_track_start is not None:
                play_before_pause = self._pause_start - self._current_track_start
                self._accumulated_play += play_before_pause
                self._current_track_start = time.monotonic()
            self._pause_start = None
            return

        # ---- track changed or stopped: finalise previous track ----
        if prev_url is not None and prev_state in ("play", "pause"):
            elapsed = self._compute_elapsed()
            if elapsed >= self._min_play_seconds:
                self._report_track(prev_url)

        # ---- start tracking new track if playing ----
        if new_state == "play" and new_url:
            self._current_track_url = new_url
            self._current_track_start = time.monotonic()
            self._accumulated_play = 0.0
            self._pause_start = None
        else:
            self._reset_tracking()

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------

    def _compute_elapsed(self) -> float:
        """Return total *play* seconds for the current/previous track."""
        if self._current_track_start is None:
            return self._accumulated_play

        now = time.monotonic()

        if self._pause_start is not None:
            # Currently paused -- only count up to pause start
            segment = self._pause_start - self._current_track_start
        else:
            segment = now - self._current_track_start

        return self._accumulated_play + segment

    def _reset_tracking(self) -> None:
        self._current_track_url = None
        self._current_track_start = None
        self._accumulated_play = 0.0
        self._pause_start = None

    # ------------------------------------------------------------------
    # Video-ID extraction & reporting
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_video_id(url: str) -> str | None:
        """Extract video_id from a proxy URL like ``/proxy/dQw4w9WgXcQ``."""
        if not url:
            return None
        match = VIDEO_ID_RE.search(url)
        return match.group(1) if match else None

    def _report_track(self, url: str) -> None:
        """Look up *url*, fetch song metadata, and report to YouTube Music."""
        video_id = self._extract_video_id(url)
        if video_id is None:
            logger.debug("Skipping non-proxy URL: %s", url)
            return

        try:
            song = self._ytmusic.get_song(video_id)
            ok = self._ytmusic.report_history(song)
            if ok:
                logger.info("Reported history for %s", video_id)
            else:
                logger.warning("History report returned False for %s", video_id)
        except Exception as e:
            logger.warning("Failed to report history for %s: %s", video_id, e)
