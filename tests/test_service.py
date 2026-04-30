"""Tests for core/service.py — QuizService business logic."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from core.refinement import RefinementReport
from core.schemas.answer_schemas import AnswerLogEntry, AnswerOutcome
from core.schemas.question_schemas import (
    DifficultQuestion,
    HistoryEntry,
    Question,
    QuestionType,
)
from core.schemas.schemas import QuizSession
from core.service import QuizService
from core.storage import StorageBackend
from tests.conftest import make_log_entry, make_question, make_session


@pytest.fixture
def mock_backend() -> MagicMock:
    backend = MagicMock(spec=StorageBackend)
    backend.load_questions.return_value = []
    backend.load_answers.return_value = []
    return backend


@pytest.fixture
def service(mock_backend, tmp_path) -> QuizService:
    return QuizService(mock_backend, tmp_path / "topics.json")


# ---------------------------------------------------------------------------
# prepare_session
# ---------------------------------------------------------------------------


class TestPrepareSession:
    def test_returns_only_due_questions(self, service, mock_backend):
        due_q = make_question(id="q1", next_review="2026-01-01", history=[])
        # future_q has a history entry so it's in the "due reviews" bucket;
        # its far-future next_review means it won't be selected.
        future_q = make_question(
            id="q2",
            next_review="2099-01-01",
            history=[HistoryEntry(date="2026-01-01", correct=True)],
        )
        mock_backend.load_questions.return_value = [due_q, future_q]
        result = service.prepare_session("2026-04-27")
        assert any(q.id == "q1" for q in result)
        assert not any(q.id == "q2" for q in result)

    def test_empty_pool_returns_empty(self, service, mock_backend):
        mock_backend.load_questions.return_value = []
        assert service.prepare_session("2026-04-27") == []


# ---------------------------------------------------------------------------
# start_session
# ---------------------------------------------------------------------------


class TestStartSession:
    def test_returns_quiz_session(self, service):
        q = make_question(id="q1")
        session = service.start_session([q])
        assert isinstance(session, QuizSession)

    def test_cursor_starts_at_zero(self, service):
        q = make_question()
        session = service.start_session([q])
        assert session.cursor == 0

    def test_score_starts_at_zero(self, service):
        q = make_question()
        session = service.start_session([q])
        assert session.score == 0

    def test_session_length_matches_due_count(self, service):
        qs = [make_question(id=f"q{i}") for i in range(4)]
        session = service.start_session(qs)
        assert session.total == 4

    def test_original_map_contains_only_due_questions(self, service):
        due = [make_question(id="q1"), make_question(id="q2")]
        session = service.start_session(due)
        assert set(session.original_map.keys()) == {"q1", "q2"}

    def test_truefalse_not_shuffled(self, service):
        q = make_question(
            id="tof",
            qtype=QuestionType.TRUE_OR_FALSE,
            options=["True", "False"],
            correct="A",
        )
        for _ in range(20):
            session = service.start_session([q])
            assert session.display_map["tof"].options == ["True", "False"]

    def test_mcq_options_same_set_after_shuffle(self, service):
        q = make_question(
            id="q1", options=["alpha", "beta", "gamma", "delta"], correct="A"
        )
        for _ in range(20):
            session = service.start_session([q])
            assert sorted(session.display_map["q1"].options) == sorted(q.options)


# ---------------------------------------------------------------------------
# process_answer
# ---------------------------------------------------------------------------


class TestProcessAnswer:
    def test_invalid_answer_returns_none(self, service):
        q = make_question(id="q1", correct="A")
        session = make_session([q])
        result = service.process_answer(session, "Z", "2026-04-27")
        assert result is None

    def test_invalid_answer_does_not_advance_cursor(self, service):
        q = make_question(id="q1", correct="A")
        session = make_session([q])
        service.process_answer(session, "Z", "2026-04-27")
        assert session.cursor == 0

    def test_valid_correct_answer_returns_outcome(self, service, mock_backend):
        q = make_question(id="q1", correct="A")
        session = make_session([q])
        result = service.process_answer(session, "A", "2026-04-27")
        assert isinstance(result, AnswerOutcome)
        assert result.correct is True

    def test_valid_wrong_answer_returns_outcome(self, service, mock_backend):
        q = make_question(id="q1", correct="A")
        session = make_session([q])
        result = service.process_answer(session, "B", "2026-04-27")
        assert isinstance(result, AnswerOutcome)
        assert result.correct is False

    def test_correct_answer_increments_score(self, service, mock_backend):
        q = make_question(id="q1", correct="A")
        session = make_session([q])
        service.process_answer(session, "A", "2026-04-27")
        assert session.score == 1

    def test_wrong_answer_does_not_increment_score(self, service, mock_backend):
        q = make_question(id="q1", correct="A")
        session = make_session([q])
        service.process_answer(session, "B", "2026-04-27")
        assert session.score == 0

    def test_advances_cursor(self, service, mock_backend):
        q = make_question(id="q1", correct="A")
        session = make_session([q])
        service.process_answer(session, "A", "2026-04-27")
        assert session.cursor == 1

    def test_calls_append_answer(self, service, mock_backend):
        q = make_question(id="q1", topic="DQN", correct="A")
        session = make_session([q])
        service.process_answer(session, "A", "2026-04-27")
        mock_backend.append_answer.assert_called_once()
        entry: AnswerLogEntry = mock_backend.append_answer.call_args[0][0]
        assert entry.qid == "q1"
        assert entry.topic == "DQN"
        assert entry.correct is True

    def test_srs_advanced_on_correct(self, service, mock_backend):
        q = make_question(id="q1", level=1, correct="A")
        session = make_session([q])
        service.process_answer(session, "A", "2026-04-27")
        assert session.original_map["q1"].level == 2

    def test_srs_demoted_on_wrong(self, service, mock_backend):
        q = make_question(id="q1", level=3, correct="A")
        session = make_session([q])
        service.process_answer(session, "B", "2026-04-27")
        assert session.original_map["q1"].level == 1


# ---------------------------------------------------------------------------
# end_session
# ---------------------------------------------------------------------------


class TestEndSession:
    def test_merges_updated_questions_into_full_pool(self, service, mock_backend):
        full_pool = [
            make_question(id="q1", level=1),
            make_question(id="q2", level=1),
            make_question(id="q3", level=1),
        ]
        mock_backend.load_questions.return_value = full_pool

        updated_q1 = make_question(id="q1", level=2)
        session = make_session([make_question(id="q1", level=1)])
        session.original_map["q1"] = updated_q1

        service.end_session(session)

        saved = mock_backend.save_questions.call_args[0][0]
        saved_map = {q.id: q for q in saved}
        assert len(saved) == 3
        assert saved_map["q1"].level == 2
        assert saved_map["q2"].level == 1
        assert saved_map["q3"].level == 1

    def test_saves_all_questions(self, service, mock_backend):
        mock_backend.load_questions.return_value = [make_question(id="q1")]
        session = make_session([make_question(id="q1")])
        service.end_session(session)
        mock_backend.save_questions.assert_called_once()


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------


class TestGetGapReport:
    def test_returns_refinement_report(self, service, mock_backend):
        mock_backend.load_questions.return_value = []
        mock_backend.load_answers.return_value = []
        assert isinstance(service.get_gap_report(), RefinementReport)

    def test_loads_questions_and_answers(self, service, mock_backend):
        mock_backend.load_questions.return_value = []
        mock_backend.load_answers.return_value = []
        service.get_gap_report()
        mock_backend.load_questions.assert_called_once()
        mock_backend.load_answers.assert_called_once()


class TestGetDifficultQuestions:
    def _struggling_question(self, id: str = "q1") -> Question:
        history = [
            HistoryEntry(date=f"2026-04-{i+1:02d}", correct=c)
            for i, c in enumerate([False, False, True])
        ]
        return make_question(id=id, history=history)

    def test_returns_difficult_questions(self, service, mock_backend):
        q = self._struggling_question()
        mock_backend.load_questions.return_value = [q]
        mock_backend.load_answers.return_value = [make_log_entry()]
        result = service.get_difficult_questions()
        assert any(dq.question.id == "q1" for dq in result)

    def test_returns_list_of_difficult_question_type(self, service, mock_backend):
        q = self._struggling_question()
        mock_backend.load_questions.return_value = [q]
        mock_backend.load_answers.return_value = [make_log_entry()]
        result = service.get_difficult_questions()
        assert all(isinstance(dq, DifficultQuestion) for dq in result)

    def test_question_with_high_correct_rate_excluded(self, service, mock_backend):
        history = [
            HistoryEntry(date=f"2026-04-{i+1:02d}", correct=True) for i in range(3)
        ]
        q = make_question(id="q1", history=history)
        mock_backend.load_questions.return_value = [q]
        mock_backend.load_answers.return_value = [make_log_entry()]
        assert service.get_difficult_questions() == []

    def test_empty_pool_returns_empty(self, service, mock_backend):
        mock_backend.load_questions.return_value = []
        mock_backend.load_answers.return_value = []
        assert service.get_difficult_questions() == []


class TestGetStats:
    def test_returns_total_and_due_count(self, service, mock_backend):
        due_q = make_question(id="q1", next_review="2026-01-01")
        future_q = make_question(id="q2", next_review="2099-01-01")
        mock_backend.load_questions.return_value = [due_q, future_q]
        total, due = service.get_stats("2026-04-27")
        assert total == 2
        assert due == 1

    def test_empty_pool(self, service, mock_backend):
        mock_backend.load_questions.return_value = []
        total, due = service.get_stats("2026-04-27")
        assert total == 0
        assert due == 0
