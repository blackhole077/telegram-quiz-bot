"""Tests for quiz/refinement.py — analyze_gaps edge cases."""

from __future__ import annotations

from quiz.refinement import RefinementReport, analyze_gaps
from quiz.schemas import HistoryEntry
from tests.conftest import make_log_entry, make_question


def _wrong(qid: str, topic: str = "DQN", date: str = "2026-04-01") -> object:
    return make_log_entry(qid=qid, topic=topic, correct=False, date=date)


def _right(qid: str, topic: str = "DQN", date: str = "2026-04-01") -> object:
    return make_log_entry(qid=qid, topic=topic, correct=True, date=date)


class TestAnalyzeGapsEarlyReturns:
    def test_empty_log_returns_empty_report(self):
        q = make_question()
        report = analyze_gaps([], [q])
        assert report == RefinementReport()

    def test_empty_questions_returns_empty_report(self):
        entry = _wrong("q1")
        report = analyze_gaps([entry], [])
        assert report == RefinementReport()

    def test_both_empty_returns_empty_report(self):
        assert analyze_gaps([], []) == RefinementReport()


class TestRewriteIds:
    def test_one_wrong_not_flagged(self):
        q = make_question(id="q1")
        report = analyze_gaps([_wrong("q1")], [q])
        assert "q1" not in report.rewrite_ids

    def test_two_wrongs_flagged(self):
        q = make_question(id="q1")
        report = analyze_gaps([_wrong("q1"), _wrong("q1")], [q])
        assert "q1" in report.rewrite_ids

    def test_correct_answers_not_counted(self):
        q = make_question(id="q1")
        entries = [_right("q1"), _right("q1"), _right("q1")]
        report = analyze_gaps(entries, [q])
        assert "q1" not in report.rewrite_ids

    def test_mixed_correct_and_wrong_counted_separately(self):
        q = make_question(id="q1")
        entries = [_right("q1"), _right("q1"), _wrong("q1")]
        report = analyze_gaps(entries, [q])
        assert "q1" not in report.rewrite_ids


class TestSimplifyIds:
    def test_rewrite_at_level_one_included(self):
        q = make_question(id="q1", level=1)
        entries = [_wrong("q1"), _wrong("q1")]
        report = analyze_gaps(entries, [q])
        assert "q1" in report.simplify_ids

    def test_rewrite_at_level_higher_excluded(self):
        q = make_question(id="q1", level=2)
        entries = [_wrong("q1"), _wrong("q1")]
        report = analyze_gaps(entries, [q])
        assert "q1" not in report.simplify_ids

    def test_question_removed_from_pool_excluded(self):
        # Log has the qid but question is no longer in the pool.
        q_other = make_question(id="q2", level=1)
        entries = [_wrong("q1"), _wrong("q1")]
        report = analyze_gaps(entries, [q_other])
        assert "q1" not in report.simplify_ids

    def test_simplify_is_subset_of_rewrite(self):
        q = make_question(id="q1", level=1)
        entries = [_wrong("q1"), _wrong("q1")]
        report = analyze_gaps(entries, [q])
        assert set(report.simplify_ids).issubset(set(report.rewrite_ids))


class TestFlaggedTopics:
    def test_below_min_attempts_not_flagged(self):
        q = make_question(id="q1", topic="DQN")
        entries = [_wrong("q1", topic="DQN"), _wrong("q1", topic="DQN")]
        report = analyze_gaps(entries, [q])
        assert "DQN" not in report.flagged_topics

    def test_exactly_three_attempts_counted(self):
        q = make_question(id="q1", topic="DQN")
        # 3 attempts: 2 wrong + 1 right = 66.7% error > 50%
        entries = [_wrong("q1", "DQN"), _wrong("q1", "DQN"), _right("q1", "DQN")]
        report = analyze_gaps(entries, [q])
        assert "DQN" in report.flagged_topics

    def test_fifty_percent_exactly_not_flagged(self):
        q = make_question(id="q1", topic="DQN")
        # 2/4 = 50% — not strictly greater than 50%
        entries = [_wrong("q1", "DQN"), _wrong("q1", "DQN"), _right("q1", "DQN"), _right("q1", "DQN")]
        report = analyze_gaps(entries, [q])
        assert "DQN" not in report.flagged_topics

    def test_multiple_topics_independently_evaluated(self):
        q1 = make_question(id="q1", topic="DQN")
        q2 = make_question(id="q2", topic="PPO")
        # DQN: 2/3 wrong → flagged; PPO: 0/3 wrong → not flagged
        entries = (
            [_wrong("q1", "DQN"), _wrong("q1", "DQN"), _right("q1", "DQN")]
            + [_right("q2", "PPO"), _right("q2", "PPO"), _right("q2", "PPO")]
        )
        report = analyze_gaps(entries, [q1, q2])
        assert "DQN" in report.flagged_topics
        assert "PPO" not in report.flagged_topics


class TestRetireIds:
    def _make_history(self, *corrects: bool):
        return [HistoryEntry(date=f"2026-04-{i+1:02d}", correct=c) for i, c in enumerate(corrects)]

    def test_level_four_last_three_correct_retired(self):
        q = make_question(id="q1", level=4, history=self._make_history(True, True, True))
        report = analyze_gaps([_right("q1")], [q])
        assert "q1" in report.retire_ids

    def test_level_four_one_wrong_in_last_three_not_retired(self):
        q = make_question(id="q1", level=4, history=self._make_history(True, False, True))
        report = analyze_gaps([_right("q1")], [q])
        assert "q1" not in report.retire_ids

    def test_level_below_four_not_retired(self):
        q = make_question(id="q1", level=3, history=self._make_history(True, True, True))
        report = analyze_gaps([_right("q1")], [q])
        assert "q1" not in report.retire_ids

    def test_fewer_than_three_history_entries_not_retired(self):
        q = make_question(id="q1", level=4, history=self._make_history(True, True))
        report = analyze_gaps([_right("q1")], [q])
        assert "q1" not in report.retire_ids

    def test_longer_history_uses_last_three_only(self):
        # Many wrong early on, but last 3 are correct → retired.
        history = self._make_history(False, False, False, False, True, True, True)
        q = make_question(id="q1", level=4, history=history)
        report = analyze_gaps([_right("q1")], [q])
        assert "q1" in report.retire_ids

    def test_stateless_does_not_modify_inputs(self):
        q = make_question(id="q1", level=4, history=self._make_history(True, True, True))
        entries = [_right("q1")]
        original_len = len(entries)
        analyze_gaps(entries, [q])
        assert len(entries) == original_len
