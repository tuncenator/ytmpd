"""Rating management for YouTube Music tracks.

This module implements the state machine for like/dislike toggle logic,
managing transitions between NEUTRAL, LIKED, and DISLIKED states.

Key API Limitation:
    The YouTube Music API has a known limitation where DISLIKED tracks
    appear as INDIFFERENT when queried. This means we cannot reliably
    distinguish between:
    - Tracks that have never been rated (NEUTRAL/INDIFFERENT)
    - Tracks that were explicitly disliked (DISLIKE → appears as INDIFFERENT)

    This limitation is documented in ytmusicapi's get_watch_playlist() method.
    Our toggle logic accepts this limitation and treats INDIFFERENT as NEUTRAL.

State Machine:
    Current State | User Action | New State  | API Call     | User Message
    --------------|-------------|------------|--------------|------------------
    NEUTRAL       | like        | LIKED      | LIKE         | ✓ Liked
    NEUTRAL       | dislike     | DISLIKED   | DISLIKE      | ✗ Disliked
    LIKED         | like        | NEUTRAL    | INDIFFERENT  | Removed like
    LIKED         | dislike     | DISLIKED   | DISLIKE      | ✗ Disliked
    DISLIKED      | like        | LIKED      | LIKE         | ✓ Liked
    DISLIKED      | dislike     | NEUTRAL    | INDIFFERENT  | Removed dislike
"""

from dataclasses import dataclass
from enum import Enum


class RatingState(Enum):
    """Represents the current rating state of a track.

    Attributes:
        NEUTRAL: No rating or indifferent (also includes DISLIKED due to API ambiguity)
        LIKED: Track is liked (thumbs up)
        DISLIKED: Track is disliked (thumbs down, but appears as INDIFFERENT in queries)
    """

    NEUTRAL = "INDIFFERENT"
    LIKED = "LIKE"
    DISLIKED = "DISLIKE"


class RatingAction(Enum):
    """Represents the user action to perform.

    Attributes:
        LIKE: User wants to toggle like status
        DISLIKE: User wants to toggle dislike status
    """

    LIKE = "like"
    DISLIKE = "dislike"


@dataclass
class RatingTransition:
    """Result of applying a rating action to a current state.

    Attributes:
        current_state: The rating state before the action
        action: The user action that was performed
        new_state: The rating state after the action
        api_value: The LikeStatus string to send to the YouTube Music API
        user_message: Feedback message to display to the user
    """

    current_state: RatingState
    action: RatingAction
    new_state: RatingState
    api_value: str
    user_message: str


class RatingManager:
    """Manages rating state transitions and toggle logic.

    This class implements a state machine that handles the toggle semantics
    for like and dislike actions. Each action toggles the rating state
    according to predefined rules.

    Example:
        >>> manager = RatingManager()
        >>> result = manager.apply_action(RatingState.NEUTRAL, RatingAction.LIKE)
        >>> print(result.new_state)
        RatingState.LIKED
        >>> print(result.user_message)
        ✓ Liked
    """

    # State transition table: (current_state, action) -> (new_state, api_value, message)
    _TRANSITIONS = {
        (RatingState.NEUTRAL, RatingAction.LIKE): (RatingState.LIKED, "LIKE", "✓ Liked"),
        (RatingState.NEUTRAL, RatingAction.DISLIKE): (
            RatingState.DISLIKED,
            "DISLIKE",
            "✗ Disliked",
        ),
        (RatingState.LIKED, RatingAction.LIKE): (
            RatingState.NEUTRAL,
            "INDIFFERENT",
            "Removed like",
        ),
        (RatingState.LIKED, RatingAction.DISLIKE): (RatingState.DISLIKED, "DISLIKE", "✗ Disliked"),
        (RatingState.DISLIKED, RatingAction.LIKE): (RatingState.LIKED, "LIKE", "✓ Liked"),
        (RatingState.DISLIKED, RatingAction.DISLIKE): (
            RatingState.NEUTRAL,
            "INDIFFERENT",
            "Removed dislike",
        ),
    }

    def apply_action(self, current_state: RatingState, action: RatingAction) -> RatingTransition:
        """Apply toggle logic to determine new state.

        Uses a state transition table to determine the new rating state
        based on the current state and the user's action.

        Args:
            current_state: Current rating state of the track
            action: User action (like or dislike)

        Returns:
            RatingTransition with new state, API value, and user message

        Raises:
            ValueError: If the state/action combination is invalid
        """
        key = (current_state, action)

        if key not in self._TRANSITIONS:
            raise ValueError(f"Invalid state transition: {current_state} + {action}")

        new_state, api_value, user_message = self._TRANSITIONS[key]

        return RatingTransition(
            current_state=current_state,
            action=action,
            new_state=new_state,
            api_value=api_value,
            user_message=user_message,
        )

    def parse_api_rating(self, api_rating: str) -> RatingState:
        """Convert API rating string to RatingState enum.

        The YouTube Music API returns rating status as strings:
        - "LIKE" for liked tracks
        - "INDIFFERENT" for neutral or disliked tracks (ambiguous)
        - "DISLIKE" may be returned in some contexts, but typically appears as INDIFFERENT

        Args:
            api_rating: Rating string from the YouTube Music API
                       (e.g., "LIKE", "INDIFFERENT", "DISLIKE")

        Returns:
            RatingState enum value

        Raises:
            ValueError: If api_rating is not a recognized value
        """
        # Normalize the input
        api_rating_upper = api_rating.upper().strip()

        # Map API strings to RatingState
        if api_rating_upper == "LIKE":
            return RatingState.LIKED
        elif api_rating_upper == "INDIFFERENT":
            # Due to API limitation, INDIFFERENT could mean NEUTRAL or DISLIKED
            # We treat it as NEUTRAL for toggle logic purposes
            return RatingState.NEUTRAL
        elif api_rating_upper == "DISLIKE":
            # Some API responses may return DISLIKE directly
            return RatingState.DISLIKED
        else:
            raise ValueError(
                f"Unknown API rating value: '{api_rating}'. "
                f"Expected 'LIKE', 'DISLIKE', or 'INDIFFERENT'."
            )
