from datetime import datetime, timezone

from mission import MissionStep, completion_ratio, minutes_until_launch, normalize_title


def test_normalize_title_collapses_whitespace():
    assert normalize_title("  Lunar   sample\treturn  ") == "Lunar sample return"


def test_completion_ratio_counts_completed_steps():
    steps = [
        MissionStep("Fuel tanks", completed=True),
        MissionStep("Crew ingress", completed=False),
        MissionStep("Go/no-go poll", completed=True),
    ]

    assert completion_ratio(steps) == 2 / 3


def test_completion_ratio_for_empty_checklist_is_zero():
    assert completion_ratio([]) == 0.0


def test_minutes_until_launch_accepts_naive_and_aware_datetimes():
    now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
    launch_at = datetime(2026, 5, 8, 12, 45)

    assert minutes_until_launch(launch_at, now=now) == 45


def test_minutes_until_launch_clamps_past_launch_to_zero():
    now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
    launch_at = datetime(2026, 5, 8, 11, 0, tzinfo=timezone.utc)

    assert minutes_until_launch(launch_at, now=now) == 0
