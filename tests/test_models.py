from datetime import datetime, timezone

from mission_app.models import ProgressInput, next_review_at, penalty_tokens, reward_tokens, weighted_progress


def test_weighted_progress_uses_estimated_minutes():
    assert weighted_progress([ProgressInput(100, 20), ProgressInput(0, 60)]) == 25


def test_reward_tokens_increases_with_difficulty_and_completion():
    easy = reward_tokens(20, difficulty=1, completion_rate=100, actual_minutes=20, self_rating=5)
    hard = reward_tokens(20, difficulty=5, completion_rate=100, actual_minutes=20, self_rating=5)
    partial = reward_tokens(20, difficulty=5, completion_rate=50, actual_minutes=20, self_rating=5)
    assert hard > easy
    assert partial < hard


def test_penalty_tokens_are_negative():
    assert penalty_tokens(40, "late", days_late=3, importance="high") < 0
    assert penalty_tokens(40, "abandoned", incomplete_rate=50) < 0


def test_next_review_wrong_repeats_next_day():
    now = datetime(2026, 5, 8, tzinfo=timezone.utc)
    assert (next_review_at(3, "wrong", now) - now).days == 1
