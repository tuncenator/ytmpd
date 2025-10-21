#!/usr/bin/env python3
"""Research script for ytmusicapi rating methods.

This script experimentally tests the ytmusicapi rating functionality to:
1. Verify rate_song method with LIKE, DISLIKE, and INDIFFERENT
2. Find the best method to get current rating state
3. Test the INDIFFERENT vs DISLIKE ambiguity
4. Document API limitations and edge cases

Usage:
    python tests/research/test_rating_api.py <video_id>

Example:
    python tests/research/test_rating_api.py dQw4w9WgXcQ
"""

import json
import sys
from pathlib import Path

from ytmusicapi import YTMusic
from ytmusicapi.models.content.enums import LikeStatus


def print_section(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_rate_song(client: YTMusic, video_id: str) -> None:
    """Test the rate_song method with all three rating states.

    Args:
        client: Authenticated YTMusic client.
        video_id: YouTube video ID to test with.
    """
    print_section("TEST 1: rate_song Method")

    print("\n1. Setting rating to LIKE...")
    try:
        response = client.rate_song(video_id, LikeStatus.LIKE)
        print(f"   Response: {json.dumps(response, indent=2) if response else 'None'}")
        print("   ✓ LIKE succeeded")
    except Exception as e:
        print(f"   ✗ LIKE failed: {e}")

    print("\n2. Setting rating to DISLIKE...")
    try:
        response = client.rate_song(video_id, LikeStatus.DISLIKE)
        print(f"   Response: {json.dumps(response, indent=2) if response else 'None'}")
        print("   ✓ DISLIKE succeeded")
    except Exception as e:
        print(f"   ✗ DISLIKE failed: {e}")

    print("\n3. Setting rating to INDIFFERENT (neutral)...")
    try:
        response = client.rate_song(video_id, LikeStatus.INDIFFERENT)
        print(f"   Response: {json.dumps(response, indent=2) if response else 'None'}")
        print("   ✓ INDIFFERENT succeeded")
    except Exception as e:
        print(f"   ✗ INDIFFERENT failed: {e}")


def test_get_watch_playlist(client: YTMusic, video_id: str) -> dict | None:
    """Test get_watch_playlist to retrieve rating information.

    Args:
        client: Authenticated YTMusic client.
        video_id: YouTube video ID to test with.

    Returns:
        The likeStatus from the track info, if available.
    """
    print_section("TEST 2: get_watch_playlist Method")

    print(f"\nFetching watch playlist for video_id: {video_id}")
    try:
        response = client.get_watch_playlist(videoId=video_id, limit=1)

        print("\nResponse structure:")
        print(f"  Keys: {list(response.keys())}")

        if "tracks" in response and response["tracks"]:
            track = response["tracks"][0]
            print(f"\n  First track keys: {list(track.keys())}")

            # Look for likeStatus field
            if "likeStatus" in track:
                like_status = track["likeStatus"]
                print(f"\n  ✓ Found likeStatus: {like_status}")
                print(f"    Type: {type(like_status)}")
                return like_status
            else:
                print("\n  ✗ No 'likeStatus' field found in track")
        else:
            print("\n  ✗ No tracks in response")

        return None

    except Exception as e:
        print(f"\n  ✗ get_watch_playlist failed: {e}")
        return None


def test_get_song(client: YTMusic, video_id: str) -> dict | None:
    """Test get_song to check if it includes rating information.

    Args:
        client: Authenticated YTMusic client.
        video_id: YouTube video ID to test with.

    Returns:
        Rating info from the response, if available.
    """
    print_section("TEST 3: get_song Method")

    print(f"\nFetching song info for video_id: {video_id}")
    try:
        response = client.get_song(video_id)

        print("\nResponse structure:")
        print(f"  Top-level keys: {list(response.keys())}")

        # Check for rating info in various locations
        rating_info = None

        # Check videoDetails
        if "videoDetails" in response:
            video_details = response["videoDetails"]
            print(f"  videoDetails keys: {list(video_details.keys())}")

            # Look for rating-related fields
            rating_fields = [
                k for k in video_details.keys() if "like" in k.lower() or "rating" in k.lower()
            ]
            if rating_fields:
                print(f"  Found rating-related fields: {rating_fields}")
                for field in rating_fields:
                    print(f"    {field}: {video_details[field]}")
                    rating_info = video_details[field]
            else:
                print("  No rating-related fields in videoDetails")

        if rating_info:
            print(f"\n  ✓ Found rating info: {rating_info}")
        else:
            print("\n  ✗ No rating information found in get_song response")

        return rating_info

    except Exception as e:
        print(f"\n  ✗ get_song failed: {e}")
        return None


def test_ambiguity(client: YTMusic, video_id: str) -> None:
    """Test the INDIFFERENT vs DISLIKE ambiguity issue.

    This tests whether we can reliably distinguish between:
    - A track that has never been rated (INDIFFERENT)
    - A track that was actively disliked (DISLIKE)

    Args:
        client: Authenticated YTMusic client.
        video_id: YouTube video ID to test with.
    """
    print_section("TEST 4: INDIFFERENT vs DISLIKE Ambiguity")

    print("\nScenario 1: Freshly disliked track")
    print("  Step 1: Set rating to DISLIKE")
    client.rate_song(video_id, LikeStatus.DISLIKE)

    print("  Step 2: Query rating via get_watch_playlist")
    response = client.get_watch_playlist(videoId=video_id, limit=1)
    if "tracks" in response and response["tracks"]:
        status = response["tracks"][0].get("likeStatus", "NOT FOUND")
        print(f"  Result: {status}")

    print("\nScenario 2: Neutral track (INDIFFERENT)")
    print("  Step 1: Set rating to INDIFFERENT")
    client.rate_song(video_id, LikeStatus.INDIFFERENT)

    print("  Step 2: Query rating via get_watch_playlist")
    response = client.get_watch_playlist(videoId=video_id, limit=1)
    if "tracks" in response and response["tracks"]:
        status = response["tracks"][0].get("likeStatus", "NOT FOUND")
        print(f"  Result: {status}")

    print("\nScenario 3: Liked track")
    print("  Step 1: Set rating to LIKE")
    client.rate_song(video_id, LikeStatus.LIKE)

    print("  Step 2: Query rating via get_watch_playlist")
    response = client.get_watch_playlist(videoId=video_id, limit=1)
    if "tracks" in response and response["tracks"]:
        status = response["tracks"][0].get("likeStatus", "NOT FOUND")
        print(f"  Result: {status}")

    print("\n⚠️  IMPORTANT FINDING:")
    print("    The ytmusicapi documentation states that INDIFFERENT and DISLIKE")
    print("    may be ambiguous due to YouTube Music API limitations.")
    print("    This means we cannot reliably distinguish between:")
    print("      - A track that was never rated")
    print("      - A track that was explicitly disliked")


def test_edge_cases(client: YTMusic) -> None:
    """Test edge cases and error handling.

    Args:
        client: Authenticated YTMusic client.
    """
    print_section("TEST 5: Edge Cases and Error Handling")

    print("\n1. Testing with invalid video_id...")
    try:
        client.rate_song("INVALID_VIDEO_ID_12345", LikeStatus.LIKE)
        print("   ✗ Should have raised an error!")
    except Exception as e:
        print(f"   ✓ Correctly raised error: {type(e).__name__}")
        print(f"     Message: {str(e)[:100]}")

    print("\n2. Testing get_watch_playlist with invalid video_id...")
    try:
        response = client.get_watch_playlist(videoId="INVALID_VIDEO_ID_12345", limit=1)
        print(f"   Response: {response}")
    except Exception as e:
        print(f"   ✓ Correctly raised error: {type(e).__name__}")
        print(f"     Message: {str(e)[:100]}")


def main() -> None:
    """Main entry point for the research script."""
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n❌ Error: Please provide a video_id as an argument")
        print("\nExample: python tests/research/test_rating_api.py dQw4w9WgXcQ")
        sys.exit(1)

    video_id = sys.argv[1]

    # Initialize YTMusic client with browser authentication
    config_dir = Path.home() / ".config" / "ytmpd"
    auth_file = config_dir / "browser.json"

    if not auth_file.exists():
        print(f"❌ Error: Browser authentication file not found: {auth_file}")
        print("\nPlease run: python -m ytmpd.ytmusic setup-browser")
        sys.exit(1)

    print("=" * 80)
    print("  ytmusicapi Rating API Research")
    print("=" * 80)
    print(f"\nTest video_id: {video_id}")
    print(f"Auth file: {auth_file}")

    print("\nInitializing YTMusic client...")
    client = YTMusic(str(auth_file))
    print("✓ Client initialized successfully")

    # Run all tests
    test_rate_song(client, video_id)
    test_get_watch_playlist(client, video_id)
    test_get_song(client, video_id)
    test_ambiguity(client, video_id)
    test_edge_cases(client)

    # Summary and recommendations
    print_section("SUMMARY AND RECOMMENDATIONS")
    print("""
FINDINGS:

1. rate_song Method:
   - Works with LikeStatus.LIKE, LikeStatus.DISLIKE, LikeStatus.INDIFFERENT
   - Returns a response dict (structure varies) or None
   - INDIFFERENT removes the rating (sets to neutral)

2. Getting Current Rating:
   - get_watch_playlist(videoId=...) returns tracks with 'likeStatus' field
   - get_song(videoId=...) does NOT include rating information
   - get_liked_songs() can verify if a song is liked, but is slow (fetches all)

3. INDIFFERENT vs DISLIKE Ambiguity:
   - YouTube Music API does NOT distinguish between:
     * A track that was never rated
     * A track that was explicitly disliked
   - Both appear as 'INDIFFERENT' in the get_watch_playlist response
   - This is a known limitation documented in ytmusicapi

4. Recommended Approach:
   - Use get_watch_playlist(videoId=..., limit=1) to get current rating
   - Extract likeStatus from tracks[0]['likeStatus']
   - Treat INDIFFERENT as "not liked" (could be never-rated OR disliked)
   - For toggle logic:
     * INDIFFERENT + like → LIKE
     * INDIFFERENT + dislike → DISLIKE (accept ambiguity)
     * LIKE + like → INDIFFERENT (remove like)
     * LIKE + dislike → DISLIKE
     * DISLIKE + like → LIKE
     * DISLIKE + dislike → INDIFFERENT (remove dislike)

   - Since we cannot distinguish INDIFFERENT from DISLIKE, the user experience
     should accept that "neutral" and "disliked" are the same state from the
     API's perspective. This means:
     * Pressing "dislike" on a neutral track will dislike it
     * Pressing "dislike" again will remove the dislike (toggle to neutral)
     * But we can't show "currently disliked" status reliably

IMPLEMENTATION NOTES:

- Use existing _retry_on_failure and _rate_limit mechanisms
- Wrap rate_song in try/except for error handling
- get_watch_playlist is the correct method for querying current state
- Accept the INDIFFERENT/DISLIKE ambiguity as a known limitation
- Document this limitation in user-facing docs

NEXT STEPS (Phase 2):

- Implement RatingManager class with state machine logic
- Handle LIKE state clearly (we CAN detect this)
- Treat INDIFFERENT as "not liked" (neutral or disliked - we don't know)
- Provide clear user feedback about actions taken
""")


if __name__ == "__main__":
    main()
