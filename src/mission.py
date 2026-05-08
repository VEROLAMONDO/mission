"""Helpers for validating and summarizing mission checklists."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class MissionStep:
    """A single checklist step in a mission plan."""

    title: str
    completed: bool = False


def normalize_title(title: str) -> str:
    """Return a mission title with extra whitespace collapsed."""
    return " ".join(title.split())


def completion_ratio(steps: list[MissionStep]) -> float:
    """Return the fraction of mission steps that are complete.

    An empty checklist is considered 0% complete because there is no mission
    progress to report.
    """
    if not steps:
        return 0.0

    completed = sum(step.completed for step in steps)
    return completed / len(steps)


def minutes_until_launch(launch_at: datetime, now: datetime | None = None) -> int:
    """Return the whole minutes remaining until launch.

    Naive datetimes are treated as UTC to keep command-line use predictable.
    Past launch times return 0.
    """
    now = now or datetime.now(timezone.utc)
    if launch_at.tzinfo is None:
        launch_at = launch_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    remaining_seconds = (launch_at - now).total_seconds()
    return max(0, int(remaining_seconds // 60))
