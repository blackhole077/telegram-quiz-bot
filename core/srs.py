"""Spaced-repetition scheduling: advance or demote question levels."""

from __future__ import annotations

from datetime import date, timedelta

from core.constants import SRS_INTERVALS
from core.schemas.schemas import HistoryEntry, Question


def _interval(level: int) -> int:
    # Falls back to 35 d for level > 4 (not reachable normally).
    return SRS_INTERVALS.get(level, 35)


def advance(q: Question, today: str | None = None) -> Question:
    """Increment level (capped at 4), reschedule, and append a correct entry.

    ``next_review`` uses the interval for the *new* level, so level 1→2
    schedules 7 days out. Returns a new object; does not mutate *q*.
    """
    t = today or date.today().isoformat()
    new_level = min(q.level + 1, 4)
    next_review = (
        date.fromisoformat(t) + timedelta(days=_interval(new_level))
    ).isoformat()
    return q.model_copy(
        update={
            "level": new_level,
            "next_review": next_review,
            "history": q.history + [HistoryEntry(date=t, correct=True)],
        }
    )


def demote(q: Question, today: str | None = None) -> Question:
    """Reset level to 1 and schedule for tomorrow; append an incorrect entry.

    Level resets hard to 1 (not decremented) because an incorrect answer
    signals foundational breakdown regardless of prior level.
    Returns a new object; does not mutate *q*.
    """
    t = today or date.today().isoformat()
    next_review = (date.fromisoformat(t) + timedelta(days=1)).isoformat()
    return q.model_copy(
        update={
            "level": 1,
            "next_review": next_review,
            "history": q.history + [HistoryEntry(date=t, correct=False)],
        }
    )
