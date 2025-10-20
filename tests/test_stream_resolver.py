"""
Tests for ytmpd/stream_resolver.py - Stream URL resolver with yt-dlp integration.
"""

import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

import pytest
import yt_dlp

from ytmpd.stream_resolver import StreamResolver, CachedURL


class TestCachedURL:
    """Tests for CachedURL dataclass."""

    def test_cached_url_creation(self):
        """Test creating a CachedURL instance."""
        now = datetime.now()
        cached = CachedURL(
            url="https://example.com/audio.m4a",
            cached_at=now,
            video_id="dQw4w9WgXcQ"
        )

        assert cached.url == "https://example.com/audio.m4a"
        assert cached.cached_at == now
        assert cached.video_id == "dQw4w9WgXcQ"


class TestStreamResolverInit:
    """Tests for StreamResolver initialization."""

    def test_init_default_cache_hours(self):
        """Test initialization with default cache hours."""
        resolver = StreamResolver()
        assert resolver._cache_hours == 5
        assert resolver._cache == {}

    def test_init_custom_cache_hours(self):
        """Test initialization with custom cache hours."""
        resolver = StreamResolver(cache_hours=3)
        assert resolver._cache_hours == 3
        assert resolver._cache == {}


class TestStreamResolverCaching:
    """Tests for caching functionality."""

    def test_is_cache_valid_miss(self):
        """Test cache miss for non-existent video."""
        resolver = StreamResolver()
        assert not resolver._is_cache_valid("nonexistent")

    def test_is_cache_valid_hit(self):
        """Test cache hit for recently cached video."""
        resolver = StreamResolver(cache_hours=5)
        resolver._cache["vid123"] = CachedURL(
            url="https://example.com/audio.m4a",
            cached_at=datetime.now(),
            video_id="vid123"
        )

        assert resolver._is_cache_valid("vid123")

    def test_is_cache_valid_expired(self):
        """Test cache miss for expired entry."""
        resolver = StreamResolver(cache_hours=5)
        # Cache entry from 6 hours ago (expired)
        old_time = datetime.now() - timedelta(hours=6)
        resolver._cache["vid123"] = CachedURL(
            url="https://example.com/audio.m4a",
            cached_at=old_time,
            video_id="vid123"
        )

        assert not resolver._is_cache_valid("vid123")
        # Verify expired entry was removed
        assert "vid123" not in resolver._cache

    def test_clear_cache(self):
        """Test clearing the cache."""
        resolver = StreamResolver()
        resolver._cache["vid1"] = CachedURL("url1", datetime.now(), "vid1")
        resolver._cache["vid2"] = CachedURL("url2", datetime.now(), "vid2")

        assert len(resolver._cache) == 2

        resolver.clear_cache()

        assert len(resolver._cache) == 0

    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        resolver = StreamResolver(cache_hours=5)

        # Add fresh entry
        resolver._cache["vid1"] = CachedURL(
            url="url1",
            cached_at=datetime.now(),
            video_id="vid1"
        )

        # Add expired entry
        old_time = datetime.now() - timedelta(hours=6)
        resolver._cache["vid2"] = CachedURL(
            url="url2",
            cached_at=old_time,
            video_id="vid2"
        )

        stats = resolver.get_cache_stats()

        assert stats['cache_size'] == 2
        assert stats['valid_count'] == 1
        assert stats['expired_count'] == 1


class TestStreamResolverExtraction:
    """Tests for URL extraction with yt-dlp."""

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_extract_url_success(self, mock_ydl_class):
        """Test successful URL extraction."""
        # Mock yt-dlp context manager
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            'url': 'https://example.com/audio.m4a'
        }
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver._extract_url('dQw4w9WgXcQ')

        assert url == 'https://example.com/audio.m4a'
        mock_ydl.extract_info.assert_called_once_with(
            'https://youtube.com/watch?v=dQw4w9WgXcQ',
            download=False
        )

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_extract_url_no_info(self, mock_ydl_class):
        """Test extraction when no info is returned."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = None
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver._extract_url('bad_video')

        assert url is None

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_extract_url_no_url_in_info(self, mock_ydl_class):
        """Test extraction when info lacks URL field."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {'title': 'Some Title'}
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver._extract_url('bad_video')

        assert url is None

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_extract_url_private_video(self, mock_ydl_class):
        """Test extraction of private video."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError('This video is private')
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver._extract_url('private_vid')

        assert url is None

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_extract_url_unavailable_video(self, mock_ydl_class):
        """Test extraction of unavailable video."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError('Video unavailable')
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver._extract_url('unavailable_vid')

        assert url is None

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_extract_url_region_locked(self, mock_ydl_class):
        """Test extraction of region-locked video."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError(
            'Video blocked in your region'
        )
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver._extract_url('blocked_vid')

        assert url is None

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_extract_url_removed_video(self, mock_ydl_class):
        """Test extraction of removed video."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError(
            'This video has been removed'
        )
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver._extract_url('removed_vid')

        assert url is None

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_extract_url_extractor_error(self, mock_ydl_class):
        """Test extraction with extractor error."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.ExtractorError('Extractor failed')
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver._extract_url('error_vid')

        assert url is None

    @patch('ytmpd.stream_resolver.time.sleep')
    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_extract_url_network_error_retry_success(self, mock_ydl_class, mock_sleep):
        """Test extraction retries on network error and succeeds."""
        mock_ydl = MagicMock()
        # First call fails with network error, second succeeds
        mock_ydl.extract_info.side_effect = [
            Exception('Network timeout'),
            {'url': 'https://example.com/audio.m4a'}
        ]
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver._extract_url('network_fail_vid')

        assert url == 'https://example.com/audio.m4a'
        assert mock_ydl.extract_info.call_count == 2
        mock_sleep.assert_called_once_with(1)

    @patch('ytmpd.stream_resolver.time.sleep')
    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_extract_url_network_error_retry_fails(self, mock_ydl_class, mock_sleep):
        """Test extraction retries on network error and fails."""
        mock_ydl = MagicMock()
        # Both attempts fail
        mock_ydl.extract_info.side_effect = Exception('Network timeout')
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver._extract_url('network_fail_vid')

        assert url is None
        assert mock_ydl.extract_info.call_count == 2
        mock_sleep.assert_called_once_with(1)

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_extract_url_unexpected_error(self, mock_ydl_class):
        """Test extraction with unexpected error."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = RuntimeError('Unexpected error')
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver._extract_url('error_vid')

        assert url is None


class TestStreamResolverResolveVideoId:
    """Tests for resolve_video_id() method."""

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_resolve_video_id_cache_miss(self, mock_ydl_class):
        """Test resolving video ID with cache miss."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            'url': 'https://example.com/audio.m4a'
        }
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver.resolve_video_id('dQw4w9WgXcQ')

        assert url == 'https://example.com/audio.m4a'
        # Verify it was cached
        assert 'dQw4w9WgXcQ' in resolver._cache
        assert resolver._cache['dQw4w9WgXcQ'].url == 'https://example.com/audio.m4a'

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_resolve_video_id_cache_hit(self, mock_ydl_class):
        """Test resolving video ID with cache hit."""
        resolver = StreamResolver()
        # Pre-populate cache
        resolver._cache['cached_vid'] = CachedURL(
            url='https://cached.com/audio.m4a',
            cached_at=datetime.now(),
            video_id='cached_vid'
        )

        url = resolver.resolve_video_id('cached_vid')

        assert url == 'https://cached.com/audio.m4a'
        # Verify yt-dlp was not called
        mock_ydl_class.assert_not_called()

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_resolve_video_id_extraction_fails(self, mock_ydl_class):
        """Test resolving video ID when extraction fails."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError('Video unavailable')
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        url = resolver.resolve_video_id('bad_vid')

        assert url is None
        # Verify it was not cached
        assert 'bad_vid' not in resolver._cache

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_resolve_video_id_expired_cache(self, mock_ydl_class):
        """Test resolving video ID with expired cache entry."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {
            'url': 'https://new.com/audio.m4a'
        }
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver(cache_hours=5)
        # Add expired entry
        old_time = datetime.now() - timedelta(hours=6)
        resolver._cache['expired_vid'] = CachedURL(
            url='https://old.com/audio.m4a',
            cached_at=old_time,
            video_id='expired_vid'
        )

        url = resolver.resolve_video_id('expired_vid')

        # Should extract new URL
        assert url == 'https://new.com/audio.m4a'
        # Should have new cached entry
        assert resolver._cache['expired_vid'].url == 'https://new.com/audio.m4a'
        # Cached_at should be recent
        age = datetime.now() - resolver._cache['expired_vid'].cached_at
        assert age.total_seconds() < 2  # Within last 2 seconds


class TestStreamResolverBatchResolution:
    """Tests for resolve_batch() method."""

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_resolve_batch_empty_list(self, mock_ydl_class):
        """Test batch resolution with empty list."""
        resolver = StreamResolver()
        results = resolver.resolve_batch([])

        assert results == {}
        mock_ydl_class.assert_not_called()

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_resolve_batch_all_success(self, mock_ydl_class):
        """Test batch resolution where all videos succeed."""
        mock_ydl = MagicMock()

        def mock_extract(url, download):
            video_id = url.split('=')[1]
            return {'url': f'https://example.com/{video_id}.m4a'}

        mock_ydl.extract_info.side_effect = mock_extract
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        video_ids = ['vid1', 'vid2', 'vid3']
        results = resolver.resolve_batch(video_ids)

        assert len(results) == 3
        assert results['vid1'] == 'https://example.com/vid1.m4a'
        assert results['vid2'] == 'https://example.com/vid2.m4a'
        assert results['vid3'] == 'https://example.com/vid3.m4a'

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_resolve_batch_partial_success(self, mock_ydl_class):
        """Test batch resolution where some videos fail."""
        mock_ydl = MagicMock()

        def mock_extract(url, download):
            video_id = url.split('=')[1]
            if video_id == 'bad_vid':
                raise yt_dlp.utils.DownloadError('Video unavailable')
            return {'url': f'https://example.com/{video_id}.m4a'}

        mock_ydl.extract_info.side_effect = mock_extract
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        video_ids = ['vid1', 'bad_vid', 'vid3']
        results = resolver.resolve_batch(video_ids)

        assert len(results) == 2
        assert 'vid1' in results
        assert 'bad_vid' not in results
        assert 'vid3' in results

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_resolve_batch_uses_cache(self, mock_ydl_class):
        """Test batch resolution uses cached entries."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {'url': 'https://new.com/audio.m4a'}
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        # Pre-populate cache for one video
        resolver._cache['cached_vid'] = CachedURL(
            url='https://cached.com/audio.m4a',
            cached_at=datetime.now(),
            video_id='cached_vid'
        )

        video_ids = ['cached_vid', 'new_vid']
        results = resolver.resolve_batch(video_ids)

        assert len(results) == 2
        assert results['cached_vid'] == 'https://cached.com/audio.m4a'
        assert results['new_vid'] == 'https://new.com/audio.m4a'
        # Verify yt-dlp was only called once (for new_vid)
        assert mock_ydl.extract_info.call_count == 1

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_resolve_batch_handles_exceptions(self, mock_ydl_class):
        """Test batch resolution handles exceptions gracefully."""
        mock_ydl = MagicMock()

        def mock_extract(url, download):
            video_id = url.split('=')[1]
            if video_id == 'exception_vid':
                raise RuntimeError('Unexpected error')
            return {'url': f'https://example.com/{video_id}.m4a'}

        mock_ydl.extract_info.side_effect = mock_extract
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        video_ids = ['vid1', 'exception_vid', 'vid3']
        results = resolver.resolve_batch(video_ids)

        # Should get results for vid1 and vid3, not exception_vid
        assert len(results) == 2
        assert 'vid1' in results
        assert 'exception_vid' not in results
        assert 'vid3' in results

    @patch('ytmpd.stream_resolver.yt_dlp.YoutubeDL')
    def test_resolve_batch_parallel_processing(self, mock_ydl_class):
        """Test batch resolution processes videos in parallel."""
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = {'url': 'https://example.com/audio.m4a'}
        mock_ydl_class.return_value.__enter__.return_value = mock_ydl

        resolver = StreamResolver()
        # Test with 15 videos to verify parallel processing (should use max 10 workers)
        video_ids = [f'vid{i}' for i in range(15)]
        results = resolver.resolve_batch(video_ids)

        assert len(results) == 15
        assert mock_ydl.extract_info.call_count == 15
