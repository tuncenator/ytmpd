"""Tests for like indicator feature.

Covers config validation, title formatting, M3U/XSPF playlist generation,
and SyncEngine integration for the like indicator.
"""

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

from ytmpd.config import _validate_config, load_config
from ytmpd.mpd_client import MPDClient, TrackWithMetadata
from ytmpd.sync_engine import SyncEngine
from ytmpd.ytmusic import Playlist, Track

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config_dir(tmpdir, user_config=None):
    """Create a temp config dir with optional user config."""
    mock_config_dir = Path(tmpdir) / "ytmpd"
    mock_config_dir.mkdir(parents=True)
    if user_config is not None:
        config_file = mock_config_dir / "config.yaml"
        with open(config_file, "w") as f:
            yaml.safe_dump(user_config, f)
    return mock_config_dir


def _make_mpd_client():
    """Create a bare MPDClient instance (no real MPD connection)."""
    client = MPDClient("/dev/null")
    return client


# ===========================================================================
# 1. Config validation tests
# ===========================================================================


class TestLikeIndicatorConfigDefaults:
    """Tests for like_indicator default config values."""

    def test_default_config_includes_like_indicator(self):
        """Default config should include like_indicator section with correct defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = Path(tmpdir) / "ytmpd"
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

                assert "like_indicator" in config
                li = config["like_indicator"]
                assert li["enabled"] is False
                assert li["tag"] == "+1"
                assert li["alignment"] == "right"

    def test_valid_config_passes_validation(self):
        """A fully valid like_indicator config should pass validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = _make_config_dir(
                tmpdir,
                {
                    "like_indicator": {
                        "enabled": True,
                        "tag": "*",
                        "alignment": "left",
                    },
                },
            )
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

                li = config["like_indicator"]
                assert li["enabled"] is True
                assert li["tag"] == "*"
                assert li["alignment"] == "left"

    def test_deep_merge_partial_config(self):
        """User partial like_indicator config should merge with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = _make_config_dir(
                tmpdir,
                {
                    "like_indicator": {
                        "enabled": True,
                        # tag and alignment omitted -- should use defaults
                    },
                },
            )
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                config = load_config()

                li = config["like_indicator"]
                assert li["enabled"] is True
                assert li["tag"] == "+1"  # default
                assert li["alignment"] == "right"  # default


class TestLikeIndicatorConfigValidation:
    """Tests for like_indicator config validation errors."""

    def test_enabled_must_be_bool(self):
        """like_indicator.enabled must be a boolean."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = _make_config_dir(
                tmpdir,
                {
                    "like_indicator": {"enabled": 1},
                },
            )
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                with pytest.raises(ValueError, match="like_indicator.enabled must be a boolean"):
                    load_config()

    def test_enabled_rejects_string(self):
        """like_indicator.enabled rejects string values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = _make_config_dir(
                tmpdir,
                {
                    "like_indicator": {"enabled": "yes"},
                },
            )
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                with pytest.raises(ValueError, match="like_indicator.enabled must be a boolean"):
                    load_config()

    def test_tag_must_be_nonempty_string(self):
        """like_indicator.tag must be a non-empty string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = _make_config_dir(
                tmpdir,
                {
                    "like_indicator": {"tag": ""},
                },
            )
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                with pytest.raises(
                    ValueError, match="like_indicator.tag must be a non-empty string"
                ):
                    load_config()

    def test_tag_rejects_int(self):
        """like_indicator.tag rejects integer values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = _make_config_dir(
                tmpdir,
                {
                    "like_indicator": {"tag": 42},
                },
            )
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                with pytest.raises(
                    ValueError, match="like_indicator.tag must be a non-empty string"
                ):
                    load_config()

    def test_tag_rejects_none(self):
        """like_indicator.tag rejects None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = _make_config_dir(
                tmpdir,
                {
                    "like_indicator": {"tag": None},
                },
            )
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                with pytest.raises(
                    ValueError, match="like_indicator.tag must be a non-empty string"
                ):
                    load_config()

    def test_alignment_must_be_left_or_right(self):
        """like_indicator.alignment must be 'left' or 'right'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = _make_config_dir(
                tmpdir,
                {
                    "like_indicator": {"alignment": "center"},
                },
            )
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                with pytest.raises(
                    ValueError, match="like_indicator.alignment must be 'left' or 'right'"
                ):
                    load_config()

    def test_alignment_rejects_top(self):
        """like_indicator.alignment rejects arbitrary string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_config_dir = _make_config_dir(
                tmpdir,
                {
                    "like_indicator": {"alignment": "top"},
                },
            )
            with patch("ytmpd.config.get_config_dir", return_value=mock_config_dir):
                with pytest.raises(
                    ValueError, match="like_indicator.alignment must be 'left' or 'right'"
                ):
                    load_config()

    def test_like_indicator_must_be_dict(self):
        """like_indicator must be a dict/mapping."""
        # Use _validate_config directly because load_config's deep-merge
        # catches the error before validation runs.
        config = {"like_indicator": "invalid"}
        with pytest.raises(ValueError, match="like_indicator must be a mapping"):
            _validate_config(config)


# ===========================================================================
# 2. Title formatting tests (_apply_like_indicator)
# ===========================================================================


class TestApplyLikeIndicator:
    """Tests for MPDClient._apply_like_indicator title formatting."""

    def setup_method(self):
        self.client = _make_mpd_client()
        self.liked_ids = {"vid1", "vid2"}
        self.indicator_right = {"enabled": True, "tag": "+1", "alignment": "right"}
        self.indicator_left = {"enabled": True, "tag": "+1", "alignment": "left"}

    def test_right_alignment(self):
        """Liked track with right alignment appends indicator."""
        result = self.client._apply_like_indicator(
            "Song Title", "vid1", self.liked_ids, self.indicator_right, False
        )
        assert result == "Song Title [+1]"

    def test_left_alignment(self):
        """Liked track with left alignment prepends indicator."""
        result = self.client._apply_like_indicator(
            "Song Title", "vid1", self.liked_ids, self.indicator_left, False
        )
        assert result == "[+1] Song Title"

    def test_custom_tag_star(self):
        """Custom tag='*' produces [*]."""
        indicator = {"enabled": True, "tag": "*", "alignment": "right"}
        result = self.client._apply_like_indicator(
            "Song Title", "vid1", self.liked_ids, indicator, False
        )
        assert result == "Song Title [*]"

    def test_custom_tag_liked(self):
        """Custom tag='LIKED' produces [LIKED]."""
        indicator = {"enabled": True, "tag": "LIKED", "alignment": "right"}
        result = self.client._apply_like_indicator(
            "Song Title", "vid1", self.liked_ids, indicator, False
        )
        assert result == "Song Title [LIKED]"

    def test_not_liked_unchanged(self):
        """Non-liked track title is unchanged."""
        result = self.client._apply_like_indicator(
            "Song Title", "vid_other", self.liked_ids, self.indicator_right, False
        )
        assert result == "Song Title"

    def test_liked_playlist_skipped(self):
        """Liked track in liked playlist should not get indicator."""
        result = self.client._apply_like_indicator(
            "Song Title", "vid1", self.liked_ids, self.indicator_right, True
        )
        assert result == "Song Title"

    def test_disabled_indicator_unchanged(self):
        """Disabled like_indicator leaves title unchanged."""
        indicator = {"enabled": False, "tag": "+1", "alignment": "right"}
        result = self.client._apply_like_indicator(
            "Song Title", "vid1", self.liked_ids, indicator, False
        )
        assert result == "Song Title"

    def test_none_indicator_unchanged(self):
        """like_indicator=None leaves title unchanged."""
        result = self.client._apply_like_indicator(
            "Song Title", "vid1", self.liked_ids, None, False
        )
        assert result == "Song Title"

    def test_empty_liked_set_unchanged(self):
        """Empty liked_video_ids set leaves title unchanged."""
        result = self.client._apply_like_indicator(
            "Song Title", "vid1", set(), self.indicator_right, False
        )
        assert result == "Song Title"

    def test_none_liked_set_unchanged(self):
        """liked_video_ids=None leaves title unchanged."""
        result = self.client._apply_like_indicator(
            "Song Title", "vid1", None, self.indicator_right, False
        )
        assert result == "Song Title"


# ===========================================================================
# 3. M3U playlist generation with like indicator
# ===========================================================================


class TestM3ULikeIndicator:
    """Tests for M3U playlist generation with like indicator."""

    def _make_tracks(self):
        return [
            TrackWithMetadata(
                url="http://example.com/1.m4a",
                title="Liked Song",
                artist="Artist A",
                video_id="vid1",
            ),
            TrackWithMetadata(
                url="http://example.com/2.m4a",
                title="Other Song",
                artist="Artist B",
                video_id="vid_other",
            ),
        ]

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_m3u_liked_track_has_indicator(self, mock_path, mock_mpd_base):
        """EXTINF line for liked track should contain [+1]."""
        mock_path.return_value.expanduser.return_value.exists.return_value = True
        mock_client = Mock()
        mock_client.listplaylists.return_value = []
        mock_mpd_base.return_value = mock_client

        mock_playlist_dir = Mock()
        mock_playlist_file = Mock()
        mock_playlist_dir.__truediv__ = Mock(return_value=mock_playlist_file)

        client = MPDClient("/path/to/socket")
        client.connect()
        client.playlist_directory = mock_playlist_dir

        tracks = self._make_tracks()
        liked_ids = {"vid1"}
        indicator = {"enabled": True, "tag": "+1", "alignment": "right"}

        client.create_or_replace_playlist(
            "Test",
            tracks,
            liked_video_ids=liked_ids,
            like_indicator=indicator,
        )

        written = mock_playlist_file.write_text.call_args[0][0]
        assert "#EXTINF:-1,Artist A - Liked Song [+1]" in written

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_m3u_non_liked_track_no_indicator(self, mock_path, mock_mpd_base):
        """EXTINF line for non-liked track should NOT contain indicator."""
        mock_path.return_value.expanduser.return_value.exists.return_value = True
        mock_client = Mock()
        mock_client.listplaylists.return_value = []
        mock_mpd_base.return_value = mock_client

        mock_playlist_dir = Mock()
        mock_playlist_file = Mock()
        mock_playlist_dir.__truediv__ = Mock(return_value=mock_playlist_file)

        client = MPDClient("/path/to/socket")
        client.connect()
        client.playlist_directory = mock_playlist_dir

        tracks = self._make_tracks()
        liked_ids = {"vid1"}
        indicator = {"enabled": True, "tag": "+1", "alignment": "right"}

        client.create_or_replace_playlist(
            "Test",
            tracks,
            liked_video_ids=liked_ids,
            like_indicator=indicator,
        )

        written = mock_playlist_file.write_text.call_args[0][0]
        assert "#EXTINF:-1,Artist B - Other Song\n" in written
        assert "Other Song [+1]" not in written

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_m3u_left_alignment(self, mock_path, mock_mpd_base):
        """Left-aligned indicator should appear before artist-title."""
        mock_path.return_value.expanduser.return_value.exists.return_value = True
        mock_client = Mock()
        mock_client.listplaylists.return_value = []
        mock_mpd_base.return_value = mock_client

        mock_playlist_dir = Mock()
        mock_playlist_file = Mock()
        mock_playlist_dir.__truediv__ = Mock(return_value=mock_playlist_file)

        client = MPDClient("/path/to/socket")
        client.connect()
        client.playlist_directory = mock_playlist_dir

        tracks = [self._make_tracks()[0]]  # liked track only
        liked_ids = {"vid1"}
        indicator = {"enabled": True, "tag": "+1", "alignment": "left"}

        client.create_or_replace_playlist(
            "Test",
            tracks,
            liked_video_ids=liked_ids,
            like_indicator=indicator,
        )

        written = mock_playlist_file.write_text.call_args[0][0]
        assert "#EXTINF:-1,[+1] Artist A - Liked Song" in written

    @patch("ytmpd.mpd_client.MPDClientBase")
    @patch("ytmpd.mpd_client.Path")
    def test_m3u_indicator_disabled(self, mock_path, mock_mpd_base):
        """Disabled indicator should not modify EXTINF lines."""
        mock_path.return_value.expanduser.return_value.exists.return_value = True
        mock_client = Mock()
        mock_client.listplaylists.return_value = []
        mock_mpd_base.return_value = mock_client

        mock_playlist_dir = Mock()
        mock_playlist_file = Mock()
        mock_playlist_dir.__truediv__ = Mock(return_value=mock_playlist_file)

        client = MPDClient("/path/to/socket")
        client.connect()
        client.playlist_directory = mock_playlist_dir

        tracks = [self._make_tracks()[0]]
        liked_ids = {"vid1"}
        indicator = {"enabled": False, "tag": "+1", "alignment": "right"}

        client.create_or_replace_playlist(
            "Test",
            tracks,
            liked_video_ids=liked_ids,
            like_indicator=indicator,
        )

        written = mock_playlist_file.write_text.call_args[0][0]
        assert "#EXTINF:-1,Artist A - Liked Song\n" in written
        assert "[+1]" not in written


# ===========================================================================
# 4. XSPF playlist generation with like indicator
# ===========================================================================


class TestXSPFLikeIndicator:
    """Tests for XSPF playlist generation with like indicator."""

    def _make_tracks(self):
        return [
            TrackWithMetadata(
                url="http://example.com/1.m4a",
                title="Liked Song",
                artist="Artist A",
                video_id="vid1",
                duration_seconds=180.0,
            ),
            TrackWithMetadata(
                url="http://example.com/2.m4a",
                title="Other Song",
                artist="Artist B",
                video_id="vid_other",
                duration_seconds=200.0,
            ),
        ]

    def _create_xspf(self, tmp_path, tracks, liked_ids, indicator):
        """Helper: create an XSPF playlist and return the parsed XML tree."""
        music_dir = tmp_path / "Music"
        music_dir.mkdir(exist_ok=True)

        client = MPDClient("/dev/null")

        with patch.object(client, "_ensure_connected"):
            client.create_or_replace_playlist(
                "Test",
                tracks,
                playlist_format="xspf",
                mpd_music_directory=str(music_dir),
                liked_video_ids=liked_ids,
                like_indicator=indicator,
            )

        xspf_file = music_dir / "_youtube" / "Test.xspf"
        assert xspf_file.exists()
        return ET.parse(xspf_file)

    def test_xspf_liked_track_title_has_indicator(self, tmp_path):
        """XSPF <title> for liked track should contain indicator."""
        tree = self._create_xspf(
            tmp_path,
            self._make_tracks(),
            {"vid1"},
            {"enabled": True, "tag": "+1", "alignment": "right"},
        )
        ns = {"xspf": "http://xspf.org/ns/0/"}
        titles = [t.text for t in tree.findall(".//xspf:track/xspf:title", ns)]
        assert "Liked Song [+1]" in titles

    def test_xspf_creator_stays_clean(self, tmp_path):
        """XSPF <creator> (artist) should NOT contain indicator."""
        tree = self._create_xspf(
            tmp_path,
            self._make_tracks(),
            {"vid1"},
            {"enabled": True, "tag": "+1", "alignment": "right"},
        )
        ns = {"xspf": "http://xspf.org/ns/0/"}
        creators = [c.text for c in tree.findall(".//xspf:track/xspf:creator", ns)]
        for creator in creators:
            assert "[+1]" not in creator

    def test_xspf_non_liked_title_unchanged(self, tmp_path):
        """XSPF <title> for non-liked track should not have indicator."""
        tree = self._create_xspf(
            tmp_path,
            self._make_tracks(),
            {"vid1"},
            {"enabled": True, "tag": "+1", "alignment": "right"},
        )
        ns = {"xspf": "http://xspf.org/ns/0/"}
        titles = [t.text for t in tree.findall(".//xspf:track/xspf:title", ns)]
        assert "Other Song" in titles
        assert "Other Song [+1]" not in titles

    def test_xspf_left_alignment(self, tmp_path):
        """XSPF <title> with left alignment should prepend indicator."""
        tree = self._create_xspf(
            tmp_path,
            [self._make_tracks()[0]],
            {"vid1"},
            {"enabled": True, "tag": "+1", "alignment": "left"},
        )
        ns = {"xspf": "http://xspf.org/ns/0/"}
        titles = [t.text for t in tree.findall(".//xspf:track/xspf:title", ns)]
        assert "[+1] Liked Song" in titles


# ===========================================================================
# 5. SyncEngine integration tests (with mocks)
# ===========================================================================


class TestSyncEngineLikeIndicator:
    """Tests for SyncEngine like indicator integration."""

    def _make_engine(self, ytmusic, mpd, resolver, **kwargs):
        """Create a SyncEngine with sensible defaults + overrides."""
        defaults = {
            "sync_liked_songs": True,
            "like_indicator": {"enabled": True, "tag": "+1", "alignment": "right"},
        }
        defaults.update(kwargs)
        return SyncEngine(ytmusic, mpd, resolver, **defaults)

    def test_sync_passes_liked_ids_to_playlist_creation(self):
        """sync_all_playlists should pass liked_video_ids to create_or_replace_playlist."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Mix", track_count=1),
        ]
        ytmusic.get_liked_songs.return_value = [
            Track(video_id="liked1", title="Liked", artist="A"),
            Track(video_id="liked2", title="Liked2", artist="B"),
        ]
        ytmusic.get_playlist_tracks.return_value = [
            Track(video_id="vid1", title="Song", artist="C"),
        ]

        mpd = Mock()
        resolver = Mock()
        resolver.resolve_batch.return_value = {"vid1": "http://example.com/1.m4a"}

        engine = self._make_engine(ytmusic, mpd, resolver)
        engine.sync_all_playlists()

        # Find the call for the regular playlist (not "Liked Songs")
        calls = mpd.create_or_replace_playlist.call_args_list
        mix_call = [c for c in calls if c[0][0] == "YT: Mix"]
        assert len(mix_call) == 1

        kwargs = mix_call[0][1]
        assert kwargs["liked_video_ids"] == {"liked1", "liked2"}
        assert kwargs["like_indicator"] == {"enabled": True, "tag": "+1", "alignment": "right"}
        assert kwargs["is_liked_playlist"] is False

    def test_liked_playlist_gets_is_liked_flag(self):
        """The liked songs playlist should be passed is_liked_playlist=True."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = []
        ytmusic.get_liked_songs.return_value = [
            Track(video_id="liked1", title="Liked", artist="A"),
        ]

        mpd = Mock()
        resolver = Mock()
        resolver.resolve_batch.return_value = {"liked1": "http://example.com/liked1.m4a"}

        engine = self._make_engine(ytmusic, mpd, resolver)
        engine.sync_all_playlists()

        calls = mpd.create_or_replace_playlist.call_args_list
        liked_call = [c for c in calls if "Liked Songs" in c[0][0]]
        assert len(liked_call) == 1
        assert liked_call[0][1]["is_liked_playlist"] is True

    def test_indicator_disabled_passes_empty_liked_set(self):
        """When like_indicator is disabled, liked_video_ids should be empty."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Mix", track_count=1),
        ]
        ytmusic.get_liked_songs.return_value = [
            Track(video_id="liked1", title="Liked", artist="A"),
        ]
        ytmusic.get_playlist_tracks.return_value = [
            Track(video_id="vid1", title="Song", artist="C"),
        ]

        mpd = Mock()
        resolver = Mock()
        resolver.resolve_batch.return_value = {"vid1": "http://example.com/1.m4a"}

        engine = self._make_engine(
            ytmusic,
            mpd,
            resolver,
            like_indicator={"enabled": False, "tag": "+1", "alignment": "right"},
        )
        engine.sync_all_playlists()

        calls = mpd.create_or_replace_playlist.call_args_list
        mix_call = [c for c in calls if c[0][0] == "YT: Mix"]
        assert len(mix_call) == 1
        assert mix_call[0][1]["liked_video_ids"] == set()

    def test_sync_liked_false_indicator_enabled_fetches_separately(self):
        """When sync_liked_songs=False but indicator enabled, liked songs fetched for set only."""
        ytmusic = Mock()
        ytmusic.get_user_playlists.return_value = [
            Playlist(id="PL1", name="Mix", track_count=1),
        ]
        ytmusic.get_liked_songs.return_value = [
            Track(video_id="liked1", title="Liked", artist="A"),
        ]
        ytmusic.get_playlist_tracks.return_value = [
            Track(video_id="vid1", title="Song", artist="C"),
        ]

        mpd = Mock()
        resolver = Mock()
        resolver.resolve_batch.return_value = {"vid1": "http://example.com/1.m4a"}

        engine = self._make_engine(
            ytmusic,
            mpd,
            resolver,
            sync_liked_songs=False,
            like_indicator={"enabled": True, "tag": "+1", "alignment": "right"},
        )
        engine.sync_all_playlists()

        # get_liked_songs should have been called (for indicator set)
        ytmusic.get_liked_songs.assert_called_once()

        # But no liked songs playlist should be created (only Mix)
        calls = mpd.create_or_replace_playlist.call_args_list
        assert len(calls) == 1
        assert calls[0][0][0] == "YT: Mix"
        assert calls[0][1]["liked_video_ids"] == {"liked1"}
