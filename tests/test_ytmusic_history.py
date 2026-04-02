"""Unit tests for YTMusicClient.get_song() and report_history()."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ytmpd.exceptions import YTMusicAuthError, YTMusicNotFoundError
from ytmpd.ytmusic import YTMusicClient


class TestGetSong:
    """Tests for YTMusicClient.get_song()."""

    @pytest.fixture
    def mock_ytmusic(self) -> Mock:
        return Mock()

    @pytest.fixture
    def client(self, tmp_path: Path, mock_ytmusic: Mock) -> YTMusicClient:
        auth_file = tmp_path / "browser.json"
        auth_file.write_text(json.dumps({"access_token": "t"}))
        with patch("ytmpd.ytmusic.YTMusic", return_value=mock_ytmusic):
            return YTMusicClient(auth_file=auth_file)

    def test_returns_song_dict(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        song_data = {"videoDetails": {"videoId": "abc12345678", "title": "Test"}}
        mock_ytmusic.get_song.return_value = song_data

        result = client.get_song("abc12345678")

        assert result == song_data
        mock_ytmusic.get_song.assert_called_once_with("abc12345678")

    def test_raises_not_found_for_empty_result(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        mock_ytmusic.get_song.return_value = {}

        with pytest.raises(YTMusicNotFoundError):
            client.get_song("abc12345678")

    def test_raises_not_found_for_none_result(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        mock_ytmusic.get_song.return_value = None

        with pytest.raises(YTMusicNotFoundError):
            client.get_song("abc12345678")

    def test_raises_auth_error_when_not_initialised(self, tmp_path: Path) -> None:
        auth_file = tmp_path / "browser.json"
        auth_file.write_text(json.dumps({"access_token": "t"}))
        with patch("ytmpd.ytmusic.YTMusic", return_value=Mock()):
            client = YTMusicClient(auth_file=auth_file)
        client._client = None

        with pytest.raises(YTMusicAuthError):
            client.get_song("abc12345678")

    def test_raises_auth_error_on_auth_failure(
        self, client: YTMusicClient, mock_ytmusic: Mock
    ) -> None:
        mock_ytmusic.get_song.side_effect = Exception("unauthorized auth failure")

        with pytest.raises(YTMusicAuthError):
            client.get_song("abc12345678")

    def test_uses_rate_limiting(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        mock_ytmusic.get_song.return_value = {"videoDetails": {"videoId": "x"}}

        with patch.object(client, "_rate_limit") as mock_rl:
            client.get_song("abc12345678")
            mock_rl.assert_called_once()


class TestReportHistory:
    """Tests for YTMusicClient.report_history()."""

    @pytest.fixture
    def mock_ytmusic(self) -> Mock:
        return Mock()

    @pytest.fixture
    def client(self, tmp_path: Path, mock_ytmusic: Mock) -> YTMusicClient:
        auth_file = tmp_path / "browser.json"
        auth_file.write_text(json.dumps({"access_token": "t"}))
        with patch("ytmpd.ytmusic.YTMusic", return_value=mock_ytmusic):
            return YTMusicClient(auth_file=auth_file)

    def test_returns_true_on_success(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        mock_ytmusic.add_history_item.return_value = "ok"
        song = {"videoDetails": {"videoId": "abc12345678"}}

        assert client.report_history(song) is True
        mock_ytmusic.add_history_item.assert_called_once_with(song)

    def test_returns_true_on_204_response(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        resp = Mock()
        resp.status_code = 204
        mock_ytmusic.add_history_item.return_value = resp

        assert client.report_history({"x": 1}) is True

    def test_returns_false_on_api_failure(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        mock_ytmusic.add_history_item.side_effect = Exception("server error")

        result = client.report_history({"x": 1})

        assert result is False

    def test_returns_false_on_auth_failure(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        mock_ytmusic.add_history_item.side_effect = Exception("unauthorized auth")

        result = client.report_history({"x": 1})

        assert result is False

    def test_returns_false_when_not_initialised(self, tmp_path: Path) -> None:
        auth_file = tmp_path / "browser.json"
        auth_file.write_text(json.dumps({"access_token": "t"}))
        with patch("ytmpd.ytmusic.YTMusic", return_value=Mock()):
            client = YTMusicClient(auth_file=auth_file)
        client._client = None

        assert client.report_history({"x": 1}) is False

    def test_uses_rate_limiting(self, client: YTMusicClient, mock_ytmusic: Mock) -> None:
        mock_ytmusic.add_history_item.return_value = "ok"

        with patch.object(client, "_rate_limit") as mock_rl:
            client.report_history({"x": 1})
            mock_rl.assert_called_once()
