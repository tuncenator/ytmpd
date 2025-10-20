"""XSPF playlist generator for ytmpd.

This module generates XSPF (XML Shareable Playlist Format) playlists that provide
separate artist/title metadata tags in MPD, enabling proper display in ncmpcpp with
color-coded fields and duration information.
"""

import xml.sax.saxutils as saxutils
from dataclasses import dataclass
from typing import Optional


@dataclass
class XSPFTrack:
    """Track data for XSPF playlist generation."""
    location: str  # URL (will be XML-escaped)
    creator: str   # Artist name
    title: str     # Track title
    duration: Optional[int] = None  # Duration in milliseconds


def generate_xspf(tracks: list[XSPFTrack]) -> str:
    """Generate XSPF playlist content from track list.

    Args:
        tracks: List of XSPFTrack objects with metadata.

    Returns:
        Complete XSPF playlist as XML string.

    Example:
        >>> tracks = [
        ...     XSPFTrack(
        ...         location="https://example.com/song.mp3",
        ...         creator="Artist Name",
        ...         title="Song Title",
        ...         duration=180000  # 3 minutes in milliseconds
        ...     )
        ... ]
        >>> xspf_content = generate_xspf(tracks)
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<playlist version="1" xmlns="http://xspf.org/ns/0/">',
        '  <trackList>',
    ]

    for track in tracks:
        lines.append('    <track>')

        # Escape URL for XML (& → &amp;, < → &lt;, etc.)
        escaped_location = saxutils.escape(track.location)
        lines.append(f'      <location>{escaped_location}</location>')

        # Escape metadata for XML
        escaped_creator = saxutils.escape(track.creator)
        escaped_title = saxutils.escape(track.title)
        lines.append(f'      <creator>{escaped_creator}</creator>')
        lines.append(f'      <title>{escaped_title}</title>')

        # Add duration if available (in milliseconds)
        if track.duration is not None:
            lines.append(f'      <duration>{track.duration}</duration>')

        lines.append('    </track>')

    lines.extend([
        '  </trackList>',
        '</playlist>',
    ])

    return '\n'.join(lines)


def seconds_to_milliseconds(seconds: float) -> int:
    """Convert seconds to milliseconds for XSPF duration tag.

    Args:
        seconds: Duration in seconds (can be float).

    Returns:
        Duration in milliseconds (integer).

    Example:
        >>> seconds_to_milliseconds(180.5)
        180500
    """
    return int(seconds * 1000)
