"""Tests for quiz/selector.py — session selection logic."""

from __future__ import annotations

from quiz.schemas import HistoryEntry
from quiz.selector import select_session
from tests.conftest import make_question

TODAY = "2026-04-20"
PAST = "2026-01-01"   # earlier than TODAY → overdue
FUTURE = "2026-12-31" # later than TODAY → not yet due


def _answered(q, next_review: str = PAST):
    entry = HistoryEntry(date="2026-01-01", correct=True)
    return q.model_copy(update={"history": [entry], "next_review": next_review})


class TestSelectSession:
    def test_empty_pool_returns_empty(self):
        assert select_session([], today=TODAY) == []

    def test_new_questions_have_no_history(self):
        q = make_question(id="q1", created_date=PAST)
        result = select_session([q], today=TODAY)
        assert len(result) == 1
        assert result[0].id == "q1"

    def test_due_questions_included(self):
        q = _answered(make_question(id="q1", next_review=PAST))
        result = select_session([q], today=TODAY)
        assert len(result) == 1

    def test_not_due_questions_excluded(self):
        q = _answered(make_question(id="q1"), next_review=FUTURE)
        result = select_session([q], today=TODAY)
        assert result == []

    def test_history_guard_prevents_new_from_appearing_as_due(self):
        # A question with empty history but next_review <= today should only
        # be in the "new" bucket, not also in the "due" bucket.
        q = make_question(id="q1", next_review=PAST, history=[])
        result = select_session([q], today=TODAY, max_n=10, new_per_session=3)
        assert len(result) == 1

    def test_new_per_session_caps_new_questions(self):
        new_qs = [make_question(id=f"n{i}", created_date=PAST) for i in range(10)]
        result = select_session(new_qs, today=TODAY, max_n=10, new_per_session=3)
        assert len(result) == 3

    def test_review_slots_fill_remaining_budget(self):
        new_qs = [make_question(id=f"n{i}", created_date=PAST) for i in range(2)]
        due_qs = [_answered(make_question(id=f"d{i}", next_review=PAST)) for i in range(8)]
        result = select_session(new_qs + due_qs, today=TODAY, max_n=10, new_per_session=3)
        assert len(result) == 10

    def test_shortfall_not_backfilled(self):
        # shortfall in new slots is NOT backfilled with extra reviews
        new_qs = [make_question(id="n1", created_date=PAST)]
        due_qs = [_answered(make_question(id=f"d{i}", next_review=PAST)) for i in range(9)]
        result = select_session(new_qs + due_qs, today=TODAY, max_n=10, new_per_session=3)
        assert len(result) == 10

    def test_new_questions_ordered_oldest_first(self):
        q_old = make_question(id="old", created_date="2026-01-01")
        q_new = make_question(id="new", created_date="2026-04-01")
        result = select_session([q_new, q_old], today=TODAY, max_n=1, new_per_session=1)
        assert result[0].id == "old"

    def test_due_questions_ordered_most_overdue_first(self):
        q_less_overdue = _answered(make_question(id="q_recent"), next_review="2026-04-19")
        q_more_overdue = _answered(make_question(id="q_old"), next_review="2026-01-01")
        result = select_session(
            [q_less_overdue, q_more_overdue], today=TODAY, max_n=1, new_per_session=0
        )
        assert result[0].id == "q_old"

    def test_result_contains_shuffled_order(self):
        qs = [make_question(id=f"q{i}", created_date=PAST) for i in range(10)]
        orders = set()
        for _ in range(20):
            r = select_session(qs, today=TODAY, max_n=10, new_per_session=10)
            orders.add(tuple(q.id for q in r))
        assert len(orders) > 1

    def test_max_n_respected_with_mixed_bucket(self):
        new_qs = [make_question(id=f"n{i}", created_date=PAST) for i in range(5)]
        due_qs = [_answered(make_question(id=f"d{i}", next_review=PAST)) for i in range(5)]
        result = select_session(new_qs + due_qs, today=TODAY, max_n=6, new_per_session=3)
        assert len(result) == 6

    def test_all_due_no_new(self):
        due_qs = [_answered(make_question(id=f"d{i}", next_review=PAST)) for i in range(5)]
        result = select_session(due_qs, today=TODAY, max_n=10, new_per_session=3)
        assert len(result) == 5
