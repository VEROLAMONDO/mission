"""Domain helpers for Mission's task, token, and memory-card logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Iterable


MINIMUM_TASK_MINUTES = 20
BASE_TOKEN_PER_UNIT = 10


class TaskStatus(StrEnum):
    DRAFT = "draft"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DEFERRED = "deferred"
    ABANDONED = "abandoned"


class TaskType(StrEnum):
    PROJECT = "project"
    MINIMUM = "minimum"
    DAILY = "daily"
    MEMORY = "memory"
    EXPLORATION = "exploration"


@dataclass(frozen=True)
class ProgressInput:
    progress: float
    estimated_minutes: int | None = None


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp with second precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def weighted_progress(children: Iterable[ProgressInput]) -> float:
    """Calculate parent progress from child progress weighted by estimated minutes."""
    total_weight = 0.0
    weighted_sum = 0.0
    for child in children:
        weight = child.estimated_minutes or MINIMUM_TASK_MINUTES
        progress = clamp(child.progress, 0, 100)
        total_weight += weight
        weighted_sum += progress * weight
    if total_weight == 0:
        return 0.0
    return round(weighted_sum / total_weight, 2)


def difficulty_factor(difficulty: int) -> float:
    return {1: 1.0, 2: 1.15, 3: 1.3, 4: 1.5, 5: 1.8}.get(difficulty, 1.0)


def streak_factor(streak_days: int) -> float:
    if streak_days >= 30:
        return 1.2
    if streak_days >= 14:
        return 1.15
    if streak_days >= 7:
        return 1.1
    if streak_days >= 3:
        return 1.05
    return 1.0


def quality_score(self_rating: int | None, objective_score: float | None) -> float:
    """Return a 0-100 quality score from self and objective ratings."""
    if objective_score is None:
        if self_rating is None:
            return 100.0
        return clamp(self_rating, 1, 5) / 5 * 100
    if self_rating is None:
        return clamp(objective_score, 0, 100)
    return clamp(self_rating, 1, 5) / 5 * 40 + clamp(objective_score, 0, 100) * 0.6


def reward_tokens(
    estimated_minutes: int,
    difficulty: int,
    completion_rate: float,
    actual_minutes: int | None = None,
    self_rating: int | None = None,
    objective_score: float | None = None,
    streak_days: int = 0,
) -> int:
    """Calculate positive token reward for a completed minimum task."""
    base = estimated_minutes / MINIMUM_TASK_MINUTES * BASE_TOKEN_PER_UNIT
    quality_factor = 0.7 + quality_score(self_rating, objective_score) / 100 * 0.3
    if actual_minutes and actual_minutes > 0:
        time_factor = clamp(estimated_minutes / actual_minutes, 0.8, 1.2)
    else:
        time_factor = 1.0
    reward = (
        base
        * difficulty_factor(difficulty)
        * clamp(completion_rate, 0, 100)
        / 100
        * quality_factor
        * time_factor
        * streak_factor(streak_days)
    )
    return round(reward)


def penalty_tokens(
    estimated_minutes: int,
    penalty_type: str,
    days_late: int = 0,
    importance: str = "medium",
    incomplete_rate: float = 100,
) -> int:
    """Calculate negative token amount for delay, abandonment, or low completion."""
    base = estimated_minutes / MINIMUM_TASK_MINUTES * BASE_TOKEN_PER_UNIT
    if penalty_type == "late":
        importance_factor = {"low": 0.5, "medium": 1.0, "high": 1.5, "urgent": 2.0}.get(importance, 1.0)
        amount = base * min(0.5, max(0, days_late) * 0.05) * importance_factor
    elif penalty_type == "abandoned":
        amount = clamp(incomplete_rate, 0, 100) / 100 * base * 0.5
    elif penalty_type == "low_completion":
        amount = base * 0.2
    else:
        amount = 0
    return -round(amount)


def next_review_at(success_count: int, quality: str = "correct", now: datetime | None = None) -> datetime:
    """Return the next Anki-style review timestamp."""
    now = now or datetime.now(timezone.utc)
    intervals = [0, 1, 3, 7, 15, 30, 60]
    if quality == "wrong":
        return now + timedelta(days=1)
    index = min(max(success_count, 0), len(intervals) - 1)
    days = intervals[index]
    if quality == "easy":
        days = max(1, round(days * 1.3))
    elif quality == "partial":
        days = max(1, round(days * 0.5))
    return now + timedelta(days=days)
