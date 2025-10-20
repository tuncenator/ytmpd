"""Unit tests for TrackStore."""

import time
from pathlib import Path

import pytest

from ytmpd.track_store import TrackStore


@pytest.fixture
def memory_store() -> TrackStore:
    """Create an in-memory TrackStore for testing."""
    store = TrackStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def temp_store(tmp_path: Path) -> TrackStore:
    """Create a file-based TrackStore in a temporary directory."""
    db_path = tmp_path / "test_tracks.db"
    store = TrackStore(str(db_path))
    yield store
    store.close()


def test_track_store_initialization(memory_store: TrackStore) -> None:
    """Test TrackStore initializes correctly and creates schema."""
    # Verify schema was created by attempting to query the table
    cursor = memory_store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tracks'"
    )
    assert cursor.fetchone() is not None


def test_track_store_creates_parent_directories(tmp_path: Path) -> None:
    """Test TrackStore creates parent directories if they don't exist."""
    db_path = tmp_path / "subdir" / "nested" / "tracks.db"
    store = TrackStore(str(db_path))

    assert db_path.exists()
    assert db_path.parent.exists()

    store.close()


def test_add_track_insert(memory_store: TrackStore) -> None:
    """Test adding a new track to the store."""
    memory_store.add_track(
        video_id="dQw4w9WgXcQ",
        stream_url="https://youtube.com/watch?v=dQw4w9WgXcQ",
        title="Never Gonna Give You Up",
        artist="Rick Astley"
    )

    track = memory_store.get_track("dQw4w9WgXcQ")
    assert track is not None
    assert track["video_id"] == "dQw4w9WgXcQ"
    assert track["stream_url"] == "https://youtube.com/watch?v=dQw4w9WgXcQ"
    assert track["title"] == "Never Gonna Give You Up"
    assert track["artist"] == "Rick Astley"
    assert isinstance(track["updated_at"], float)


def test_add_track_update(memory_store: TrackStore) -> None:
    """Test updating an existing track (UPSERT behavior)."""
    # Add initial track
    memory_store.add_track(
        video_id="test123",
        stream_url="https://old-url.com",
        title="Old Title",
        artist="Old Artist"
    )

    initial_track = memory_store.get_track("test123")
    assert initial_track is not None
    initial_time = initial_track["updated_at"]

    # Wait a bit to ensure timestamp difference
    time.sleep(0.01)

    # Update track
    memory_store.add_track(
        video_id="test123",
        stream_url="https://new-url.com",
        title="New Title",
        artist="New Artist"
    )

    updated_track = memory_store.get_track("test123")
    assert updated_track is not None
    assert updated_track["stream_url"] == "https://new-url.com"
    assert updated_track["title"] == "New Title"
    assert updated_track["artist"] == "New Artist"
    assert updated_track["updated_at"] > initial_time


def test_add_track_without_artist(memory_store: TrackStore) -> None:
    """Test adding a track with no artist (nullable field)."""
    memory_store.add_track(
        video_id="test456",
        stream_url="https://youtube.com/watch?v=test456",
        title="No Artist Track"
    )

    track = memory_store.get_track("test456")
    assert track is not None
    assert track["artist"] is None
    assert track["title"] == "No Artist Track"


def test_get_track_not_found(memory_store: TrackStore) -> None:
    """Test getting a track that doesn't exist returns None."""
    track = memory_store.get_track("nonexistent")
    assert track is None


def test_get_track_found(memory_store: TrackStore) -> None:
    """Test getting an existing track returns correct data."""
    memory_store.add_track(
        video_id="found123",
        stream_url="https://youtube.com/watch?v=found123",
        title="Found Track",
        artist="Found Artist"
    )

    track = memory_store.get_track("found123")
    assert track is not None
    assert isinstance(track, dict)
    assert track["video_id"] == "found123"
    assert "stream_url" in track
    assert "artist" in track
    assert "title" in track
    assert "updated_at" in track


def test_update_stream_url(memory_store: TrackStore) -> None:
    """Test updating only the stream URL without modifying other fields."""
    # Add initial track
    memory_store.add_track(
        video_id="update123",
        stream_url="https://old-stream-url.com",
        title="Track Title",
        artist="Track Artist"
    )

    initial_track = memory_store.get_track("update123")
    assert initial_track is not None
    initial_time = initial_track["updated_at"]

    # Wait a bit to ensure timestamp difference
    time.sleep(0.01)

    # Update stream URL
    memory_store.update_stream_url("update123", "https://new-stream-url.com")

    updated_track = memory_store.get_track("update123")
    assert updated_track is not None
    assert updated_track["stream_url"] == "https://new-stream-url.com"
    assert updated_track["title"] == "Track Title"  # Unchanged
    assert updated_track["artist"] == "Track Artist"  # Unchanged
    assert updated_track["updated_at"] > initial_time  # Timestamp updated


def test_update_stream_url_nonexistent(memory_store: TrackStore) -> None:
    """Test updating stream URL for nonexistent track (should not error)."""
    # This should not raise an error, just silently do nothing
    memory_store.update_stream_url("nonexistent", "https://new-url.com")

    track = memory_store.get_track("nonexistent")
    assert track is None


def test_database_persistence(tmp_path: Path) -> None:
    """Test that data persists after closing and reopening the database."""
    db_path = tmp_path / "persistent.db"

    # Create store and add track
    store1 = TrackStore(str(db_path))
    store1.add_track(
        video_id="persist123",
        stream_url="https://youtube.com/watch?v=persist123",
        title="Persistent Track",
        artist="Persistent Artist"
    )
    store1.close()

    # Reopen database and verify track exists
    store2 = TrackStore(str(db_path))
    track = store2.get_track("persist123")
    assert track is not None
    assert track["video_id"] == "persist123"
    assert track["title"] == "Persistent Track"
    assert track["artist"] == "Persistent Artist"
    store2.close()


def test_context_manager(tmp_path: Path) -> None:
    """Test TrackStore works as a context manager."""
    db_path = tmp_path / "context.db"

    with TrackStore(str(db_path)) as store:
        store.add_track(
            video_id="ctx123",
            stream_url="https://youtube.com/watch?v=ctx123",
            title="Context Track"
        )
        track = store.get_track("ctx123")
        assert track is not None

    # Verify database connection was closed
    # We can't directly test if conn is closed, but we can reopen and verify data
    with TrackStore(str(db_path)) as store2:
        track = store2.get_track("ctx123")
        assert track is not None


def test_multiple_tracks(memory_store: TrackStore) -> None:
    """Test storing and retrieving multiple tracks."""
    tracks_data = [
        ("video1", "https://url1.com", "Title 1", "Artist 1"),
        ("video2", "https://url2.com", "Title 2", "Artist 2"),
        ("video3", "https://url3.com", "Title 3", None),
    ]

    for video_id, url, title, artist in tracks_data:
        memory_store.add_track(video_id, url, title, artist)

    # Verify all tracks exist
    for video_id, url, title, artist in tracks_data:
        track = memory_store.get_track(video_id)
        assert track is not None
        assert track["video_id"] == video_id
        assert track["stream_url"] == url
        assert track["title"] == title
        assert track["artist"] == artist


def test_track_updated_at_timestamp(memory_store: TrackStore) -> None:
    """Test that updated_at timestamp is reasonable."""
    before = time.time()
    memory_store.add_track(
        video_id="time123",
        stream_url="https://youtube.com/watch?v=time123",
        title="Time Track"
    )
    after = time.time()

    track = memory_store.get_track("time123")
    assert track is not None
    assert before <= track["updated_at"] <= after
