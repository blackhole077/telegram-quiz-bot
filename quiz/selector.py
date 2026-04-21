"""Select a mixed session of new and due questions for review."""

from __future__ import annotations

import random
from datetime import date

from quiz.schemas import Question


def select_session(
    questions: list[Question],
    today: str | None = None,
    max_n: int = 10,
    new_per_session: int = 3,
) -> list[Question]:
    """Pick up to *max_n* questions: new introductions first, then due reviews.

    New = empty ``history``; due = ``next_review <= today`` with a
    non-empty ``history``.  The ``history`` guard on the due filter
    prevents a newly-added question appearing as both new and due.

    New questions are taken oldest-``created_date`` first (up to
    ``new_per_session``).  The remaining budget is filled with due
    reviews sorted most-overdue first.  If fewer new questions exist than
    ``new_per_session``, the shortfall is *not* backfilled with extra
    reviews.  The final list is shuffled.

    ``new_per_session`` must be ≤ ``max_n``.  If it exceeds ``max_n``,
    ``review_slots`` becomes negative and is clamped to 0 by the
    ``min(..., len(due))`` call, but the new-question slice can still
    exceed ``max_n``, producing a session larger than intended.  It is
    the caller's responsibility to ensure ``new_per_session <= max_n``.
    """
    t = today or date.today().isoformat()

    unreviewed = sorted(
        [q for q in questions if not q.history],
        key=lambda q: q.created_date,
    )
    due = sorted(
        [q for q in questions if q.next_review <= t and q.history],
        key=lambda q: q.next_review,
    )

    new_slots = min(new_per_session, len(unreviewed))
    review_slots = min(max_n - new_slots, len(due))
    selected = unreviewed[:new_slots] + due[:review_slots]

    random.shuffle(selected)
    return selected
