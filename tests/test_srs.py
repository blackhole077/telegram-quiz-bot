"""Tests for quiz/srs.py — advance and demote scheduling."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.constants import SRS_INTERVALS
from core.srs import advance, demote
from tests.conftest import make_question

TODAY = "2026-04-20"


class TestAdvance:
    def test_level_increments(self):
        q = make_question(level=1)
        q2 = advance(q, today=TODAY)
        assert q2.level == 2

    @pytest.mark.parametrize(
        "start_level,expected_next_level",
        [
            (1, 2),
            (2, 3),
            (3, 4),
            (4, 4),  # cap
        ],
    )
    def test_advance_level_and_schedule(self, start_level, expected_next_level):
        q = make_question(level=start_level)
        q2 = advance(q, today=TODAY)
        assert q2.level == expected_next_level
        expected_days = SRS_INTERVALS[expected_next_level]
        expected_date = (
            date.fromisoformat(TODAY) + timedelta(days=expected_days)
        ).isoformat()
        assert q2.next_review == expected_date

    def test_history_entry_appended_correct(self):
        q = make_question(level=1, history=[])
        q2 = advance(q, today=TODAY)
        assert len(q2.history) == 1
        assert q2.history[-1].date == TODAY
        assert q2.history[-1].correct is True

    def test_history_grows_cumulatively(self):
        from core.schemas.question_schemas import HistoryEntry

        existing = [HistoryEntry(date="2026-01-01", correct=True)]
        q = make_question(history=existing)
        q2 = advance(q, today=TODAY)
        assert len(q2.history) == 2

    def test_does_not_mutate_original(self):
        q = make_question(level=1, history=[])
        advance(q, today=TODAY)
        assert q.level == 1
        assert not q.history

    def test_uses_todays_date_when_none(self):
        q = make_question(level=1)
        q2 = advance(q)
        today_str = date.today().isoformat()
        assert q2.history[-1].date == today_str


class TestDemote:
    @pytest.mark.parametrize("start_level", [1, 2, 3, 4])
    def test_level_resets_to_one_from_any_level(self, start_level):
        q = make_question(level=start_level)
        q2 = demote(q, today=TODAY)
        assert q2.level == 1

    def test_next_review_is_tomorrow(self):
        q = make_question(level=3)
        q2 = demote(q, today=TODAY)
        expected = (date.fromisoformat(TODAY) + timedelta(days=1)).isoformat()
        assert q2.next_review == expected

    def test_history_entry_appended_incorrect(self):
        q = make_question()
        q2 = demote(q, today=TODAY)
        assert len(q2.history) == 1
        assert q2.history[-1].date == TODAY
        assert q2.history[-1].correct is False

    def test_does_not_mutate_original(self):
        q = make_question(level=3)
        demote(q, today=TODAY)
        assert q.level == 3

    def test_level_one_stays_at_one(self):
        q = make_question(level=1)
        q2 = demote(q, today=TODAY)
        assert q2.level == 1
