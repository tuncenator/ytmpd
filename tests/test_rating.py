"""Unit tests for the rating module.

Tests the RatingManager state machine and all state transitions.
"""

import pytest

from ytmpd.rating import RatingAction, RatingManager, RatingState, RatingTransition


class TestRatingStateEnum:
    """Tests for RatingState enum."""

    def test_rating_state_values(self):
        """Verify enum values match API expectations."""
        assert RatingState.NEUTRAL.value == "INDIFFERENT"
        assert RatingState.LIKED.value == "LIKE"
        assert RatingState.DISLIKED.value == "DISLIKE"


class TestRatingActionEnum:
    """Tests for RatingAction enum."""

    def test_rating_action_values(self):
        """Verify enum values."""
        assert RatingAction.LIKE.value == "like"
        assert RatingAction.DISLIKE.value == "dislike"


class TestRatingTransition:
    """Tests for RatingTransition dataclass."""

    def test_create_transition(self):
        """Verify RatingTransition can be created with all fields."""
        transition = RatingTransition(
            current_state=RatingState.NEUTRAL,
            action=RatingAction.LIKE,
            new_state=RatingState.LIKED,
            api_value="LIKE",
            user_message="✓ Liked",
        )

        assert transition.current_state == RatingState.NEUTRAL
        assert transition.action == RatingAction.LIKE
        assert transition.new_state == RatingState.LIKED
        assert transition.api_value == "LIKE"
        assert transition.user_message == "✓ Liked"


class TestRatingManagerApplyAction:
    """Tests for RatingManager.apply_action() - all 6 state transitions."""

    def test_neutral_like_becomes_liked(self):
        """NEUTRAL + like → LIKED."""
        manager = RatingManager()
        result = manager.apply_action(RatingState.NEUTRAL, RatingAction.LIKE)

        assert result.current_state == RatingState.NEUTRAL
        assert result.action == RatingAction.LIKE
        assert result.new_state == RatingState.LIKED
        assert result.api_value == "LIKE"
        assert "Liked" in result.user_message
        assert "✓" in result.user_message

    def test_neutral_dislike_becomes_disliked(self):
        """NEUTRAL + dislike → DISLIKED."""
        manager = RatingManager()
        result = manager.apply_action(RatingState.NEUTRAL, RatingAction.DISLIKE)

        assert result.current_state == RatingState.NEUTRAL
        assert result.action == RatingAction.DISLIKE
        assert result.new_state == RatingState.DISLIKED
        assert result.api_value == "DISLIKE"
        assert "Disliked" in result.user_message
        assert "✗" in result.user_message

    def test_liked_like_becomes_neutral(self):
        """LIKED + like → NEUTRAL (toggle off)."""
        manager = RatingManager()
        result = manager.apply_action(RatingState.LIKED, RatingAction.LIKE)

        assert result.current_state == RatingState.LIKED
        assert result.action == RatingAction.LIKE
        assert result.new_state == RatingState.NEUTRAL
        assert result.api_value == "INDIFFERENT"
        assert "Removed" in result.user_message

    def test_liked_dislike_becomes_disliked(self):
        """LIKED + dislike → DISLIKED."""
        manager = RatingManager()
        result = manager.apply_action(RatingState.LIKED, RatingAction.DISLIKE)

        assert result.current_state == RatingState.LIKED
        assert result.action == RatingAction.DISLIKE
        assert result.new_state == RatingState.DISLIKED
        assert result.api_value == "DISLIKE"
        assert "Disliked" in result.user_message
        assert "✗" in result.user_message

    def test_disliked_like_becomes_liked(self):
        """DISLIKED + like → LIKED."""
        manager = RatingManager()
        result = manager.apply_action(RatingState.DISLIKED, RatingAction.LIKE)

        assert result.current_state == RatingState.DISLIKED
        assert result.action == RatingAction.LIKE
        assert result.new_state == RatingState.LIKED
        assert result.api_value == "LIKE"
        assert "Liked" in result.user_message
        assert "✓" in result.user_message

    def test_disliked_dislike_becomes_neutral(self):
        """DISLIKED + dislike → NEUTRAL (toggle off)."""
        manager = RatingManager()
        result = manager.apply_action(RatingState.DISLIKED, RatingAction.DISLIKE)

        assert result.current_state == RatingState.DISLIKED
        assert result.action == RatingAction.DISLIKE
        assert result.new_state == RatingState.NEUTRAL
        assert result.api_value == "INDIFFERENT"
        assert "Removed" in result.user_message


class TestRatingManagerParseApiRating:
    """Tests for RatingManager.parse_api_rating()."""

    def test_parse_like(self):
        """Parse 'LIKE' API response."""
        manager = RatingManager()
        result = manager.parse_api_rating("LIKE")
        assert result == RatingState.LIKED

    def test_parse_like_lowercase(self):
        """Parse 'like' (case insensitive)."""
        manager = RatingManager()
        result = manager.parse_api_rating("like")
        assert result == RatingState.LIKED

    def test_parse_indifferent(self):
        """Parse 'INDIFFERENT' API response."""
        manager = RatingManager()
        result = manager.parse_api_rating("INDIFFERENT")
        assert result == RatingState.NEUTRAL

    def test_parse_indifferent_lowercase(self):
        """Parse 'indifferent' (case insensitive)."""
        manager = RatingManager()
        result = manager.parse_api_rating("indifferent")
        assert result == RatingState.NEUTRAL

    def test_parse_dislike(self):
        """Parse 'DISLIKE' API response (rare but possible)."""
        manager = RatingManager()
        result = manager.parse_api_rating("DISLIKE")
        assert result == RatingState.DISLIKED

    def test_parse_dislike_lowercase(self):
        """Parse 'dislike' (case insensitive)."""
        manager = RatingManager()
        result = manager.parse_api_rating("dislike")
        assert result == RatingState.DISLIKED

    def test_parse_with_whitespace(self):
        """Parse API rating with leading/trailing whitespace."""
        manager = RatingManager()
        result = manager.parse_api_rating("  LIKE  ")
        assert result == RatingState.LIKED

    def test_parse_invalid_rating_raises_error(self):
        """Parse invalid rating string raises ValueError."""
        manager = RatingManager()
        with pytest.raises(ValueError, match="Unknown API rating value"):
            manager.parse_api_rating("INVALID")

    def test_parse_empty_string_raises_error(self):
        """Parse empty string raises ValueError."""
        manager = RatingManager()
        with pytest.raises(ValueError, match="Unknown API rating value"):
            manager.parse_api_rating("")

    def test_parse_none_raises_error(self):
        """Parse None raises AttributeError."""
        manager = RatingManager()
        with pytest.raises(AttributeError):
            manager.parse_api_rating(None)


class TestRatingManagerEdgeCases:
    """Test edge cases and error handling."""

    def test_apply_action_with_invalid_state(self):
        """Applying action with invalid state should raise error.

        Note: This is difficult to test with enums, but we verify the
        transition table doesn't have unexpected entries.
        """
        manager = RatingManager()
        # All valid combinations should work
        all_states = [RatingState.NEUTRAL, RatingState.LIKED, RatingState.DISLIKED]
        all_actions = [RatingAction.LIKE, RatingAction.DISLIKE]

        for state in all_states:
            for action in all_actions:
                result = manager.apply_action(state, action)
                assert isinstance(result, RatingTransition)
                assert result.current_state == state
                assert result.action == action

    def test_transition_table_completeness(self):
        """Verify all 6 state transitions are defined."""
        manager = RatingManager()

        # Count all possible combinations
        states = [RatingState.NEUTRAL, RatingState.LIKED, RatingState.DISLIKED]
        actions = [RatingAction.LIKE, RatingAction.DISLIKE]

        expected_transitions = len(states) * len(actions)  # Should be 6
        actual_transitions = len(manager._TRANSITIONS)

        assert actual_transitions == expected_transitions, (
            f"Expected {expected_transitions} transitions, " f"but found {actual_transitions}"
        )

    def test_all_transitions_return_valid_api_values(self):
        """Verify all transitions return valid API values."""
        manager = RatingManager()
        valid_api_values = {"LIKE", "DISLIKE", "INDIFFERENT"}

        for (state, action), (new_state, api_value, message) in manager._TRANSITIONS.items():
            assert (
                api_value in valid_api_values
            ), f"Transition {state} + {action} has invalid API value: {api_value}"

    def test_all_transitions_have_user_messages(self):
        """Verify all transitions have non-empty user messages."""
        manager = RatingManager()

        for (state, action), (new_state, api_value, message) in manager._TRANSITIONS.items():
            assert message, f"Transition {state} + {action} has empty message"
            assert len(message) > 0
            assert isinstance(message, str)


class TestRatingManagerIntegration:
    """Integration tests simulating real usage scenarios."""

    def test_like_toggle_cycle(self):
        """Test full like toggle cycle: NEUTRAL → LIKED → NEUTRAL."""
        manager = RatingManager()

        # Start neutral, like it
        result1 = manager.apply_action(RatingState.NEUTRAL, RatingAction.LIKE)
        assert result1.new_state == RatingState.LIKED

        # Already liked, like again to remove
        result2 = manager.apply_action(RatingState.LIKED, RatingAction.LIKE)
        assert result2.new_state == RatingState.NEUTRAL

    def test_dislike_toggle_cycle(self):
        """Test full dislike toggle cycle: NEUTRAL → DISLIKED → NEUTRAL."""
        manager = RatingManager()

        # Start neutral, dislike it
        result1 = manager.apply_action(RatingState.NEUTRAL, RatingAction.DISLIKE)
        assert result1.new_state == RatingState.DISLIKED

        # Already disliked, dislike again to remove
        result2 = manager.apply_action(RatingState.DISLIKED, RatingAction.DISLIKE)
        assert result2.new_state == RatingState.NEUTRAL

    def test_switch_from_like_to_dislike(self):
        """Test switching from LIKED to DISLIKED."""
        manager = RatingManager()

        # Start neutral, like it
        result1 = manager.apply_action(RatingState.NEUTRAL, RatingAction.LIKE)
        assert result1.new_state == RatingState.LIKED

        # Switch to dislike
        result2 = manager.apply_action(RatingState.LIKED, RatingAction.DISLIKE)
        assert result2.new_state == RatingState.DISLIKED
        assert result2.api_value == "DISLIKE"

    def test_switch_from_dislike_to_like(self):
        """Test switching from DISLIKED to LIKED."""
        manager = RatingManager()

        # Start neutral, dislike it
        result1 = manager.apply_action(RatingState.NEUTRAL, RatingAction.DISLIKE)
        assert result1.new_state == RatingState.DISLIKED

        # Switch to like
        result2 = manager.apply_action(RatingState.DISLIKED, RatingAction.LIKE)
        assert result2.new_state == RatingState.LIKED
        assert result2.api_value == "LIKE"

    def test_api_ambiguity_handling(self):
        """Test handling of INDIFFERENT (which could be NEUTRAL or DISLIKED).

        When API returns INDIFFERENT, we parse it as NEUTRAL.
        User can then like or dislike from this state.
        """
        manager = RatingManager()

        # API returns INDIFFERENT (could be neutral or disliked, we don't know)
        current_state = manager.parse_api_rating("INDIFFERENT")
        assert current_state == RatingState.NEUTRAL

        # User can like from this state
        result_like = manager.apply_action(current_state, RatingAction.LIKE)
        assert result_like.new_state == RatingState.LIKED

        # Or user can dislike from this state
        result_dislike = manager.apply_action(current_state, RatingAction.DISLIKE)
        assert result_dislike.new_state == RatingState.DISLIKED
