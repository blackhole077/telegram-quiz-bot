"""Tests that router state is isolated per session cookie.

Each router previously used a single module-level state object, meaning two
concurrent users would share state. These tests verify that:
  1. Each router exposes _states: dict[str, XState] (not a single _state)
  2. State written for session "aaa" does not appear under session "bbb"
  3. A helper _get_state(request) creates a fresh entry on first access
  4. After clearing the in-process cache, _get_state restores from the session store
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request

import frontend.web.routers.exam as exam_router
import frontend.web.routers.learn as learn_router
import frontend.web.routers.practice as practice_router
import frontend.web.routers.quiz as quiz_router
from frontend.web.schemas.schema import ExamState, LearnState, PracticeState, QuizState
from frontend.web.session_store import SessionStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(session_id: str) -> Request:
    """Build a minimal Request-like object that returns the given session_id cookie."""
    request = MagicMock(spec=Request)
    request.cookies = {"session_id": session_id}
    return request


# ---------------------------------------------------------------------------
# Structure tests: _states dict must exist, not _state singleton
# ---------------------------------------------------------------------------


class TestRouterStateStructure:
    """Routers must expose _states: dict, not a bare _state object."""

    def test_quiz_router_has_states_dict(self):
        assert hasattr(quiz_router, "_states"), "quiz router must have _states dict"
        assert isinstance(quiz_router._states, dict)

    def test_practice_router_has_states_dict(self):
        assert hasattr(
            practice_router, "_states"
        ), "practice router must have _states dict"
        assert isinstance(practice_router._states, dict)

    def test_exam_router_has_states_dict(self):
        assert hasattr(exam_router, "_states"), "exam router must have _states dict"
        assert isinstance(exam_router._states, dict)

    def test_learn_router_has_states_dict(self):
        assert hasattr(learn_router, "_states"), "learn router must have _states dict"
        assert isinstance(learn_router._states, dict)

    def test_quiz_router_has_no_bare_state_singleton(self):
        assert not hasattr(
            quiz_router, "_state"
        ), "quiz router must not have module-level _state singleton"

    def test_practice_router_has_no_bare_state_singleton(self):
        assert not hasattr(
            practice_router, "_state"
        ), "practice router must not have module-level _state singleton"

    def test_exam_router_has_no_bare_state_singleton(self):
        assert not hasattr(
            exam_router, "_state"
        ), "exam router must not have module-level _state singleton"

    def test_learn_router_has_no_bare_state_singleton(self):
        assert not hasattr(
            learn_router, "_state"
        ), "learn router must not have module-level _state singleton"


# ---------------------------------------------------------------------------
# Isolation tests: state keyed by session ID
# ---------------------------------------------------------------------------


class TestQuizRouterIsolation:
    def setup_method(self):
        quiz_router._states.clear()

    def test_get_state_creates_fresh_entry_per_session(self):
        req_a = _make_request("aaa")
        req_b = _make_request("bbb")

        state_a = quiz_router._get_state(req_a)
        state_b = quiz_router._get_state(req_b)

        assert state_a is not state_b

    def test_get_state_returns_same_object_for_same_session(self):
        req = _make_request("aaa")
        first = quiz_router._get_state(req)
        second = quiz_router._get_state(req)
        assert first is second

    def test_mutation_in_session_a_does_not_affect_session_b(self):
        req_a = _make_request("aaa")
        req_b = _make_request("bbb")

        state_a = quiz_router._get_state(req_a)
        state_a.wrong_answers.append({"question_text": "Q1"})

        state_b = quiz_router._get_state(req_b)
        assert state_b.wrong_answers == []


class TestPracticeRouterIsolation:
    def setup_method(self):
        practice_router._states.clear()

    def test_get_state_creates_fresh_entry_per_session(self):
        req_a = _make_request("aaa")
        req_b = _make_request("bbb")
        assert practice_router._get_state(req_a) is not practice_router._get_state(
            req_b
        )

    def test_mutation_in_session_a_does_not_affect_session_b(self):
        req_a = _make_request("aaa")
        req_b = _make_request("bbb")

        state_a = practice_router._get_state(req_a)
        state_a.wrong_answers.append({"question_text": "Q1"})

        assert practice_router._get_state(req_b).wrong_answers == []


class TestExamRouterIsolation:
    def setup_method(self):
        exam_router._states.clear()

    def test_get_state_creates_fresh_entry_per_session(self):
        req_a = _make_request("aaa")
        req_b = _make_request("bbb")
        assert exam_router._get_state(req_a) is not exam_router._get_state(req_b)

    def test_mutation_in_session_a_does_not_affect_session_b(self):
        req_a = _make_request("aaa")
        req_b = _make_request("bbb")

        state_a = exam_router._get_state(req_a)
        state_a.category = "RL"

        assert exam_router._get_state(req_b).category == ""


class TestLearnRouterIsolation:
    def setup_method(self):
        learn_router._states.clear()

    def test_get_state_creates_fresh_entry_per_session(self):
        req_a = _make_request("aaa")
        req_b = _make_request("bbb")
        assert learn_router._get_state(req_a) is not learn_router._get_state(req_b)

    def test_mutation_in_session_a_does_not_affect_session_b(self):
        req_a = _make_request("aaa")
        req_b = _make_request("bbb")

        state_a = learn_router._get_state(req_a)
        state_a.exercise_type = "connect"

        assert learn_router._get_state(req_b).exercise_type == ""


# ---------------------------------------------------------------------------
# Restore-on-read: after clearing the in-process cache, _get_state restores
# from the session store.
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions.db")


class TestRestoreOnRead:
    def _req(self, session_id: str) -> MagicMock:
        return _make_request(session_id)

    def test_quiz_restores_from_store(self, tmp_store: SessionStore):
        state = QuizState()
        state.wrong_answers = [{"question_text": "Q1"}]
        tmp_store.put("restore-sid", "quiz", state, ttl_seconds=3600)
        quiz_router._states.clear()
        with patch.object(quiz_router, "session_store", tmp_store):
            restored = quiz_router._get_state(self._req("restore-sid"))
        assert restored.wrong_answers == [{"question_text": "Q1"}]

    def test_practice_restores_from_store(self, tmp_store: SessionStore):
        state = PracticeState()
        state.wrong_answers = [{"question_text": "P1"}]
        tmp_store.put("restore-sid", "practice", state, ttl_seconds=3600)
        practice_router._states.clear()
        with patch.object(practice_router, "session_store", tmp_store):
            restored = practice_router._get_state(self._req("restore-sid"))
        assert restored.wrong_answers == [{"question_text": "P1"}]

    def test_exam_restores_from_store(self, tmp_store: SessionStore):
        from core.schemas.llm_schemas import ExamProblem

        state = ExamState(
            category="RL",
            problems=[ExamProblem(number=1, prompt="p", solution="s")],
        )
        tmp_store.put("restore-sid", "exam", state, ttl_seconds=3600)
        exam_router._states.clear()
        with patch.object(exam_router, "session_store", tmp_store):
            restored = exam_router._get_state(self._req("restore-sid"))
        assert restored.category == "RL"
        assert len(restored.problems) == 1

    def test_learn_restores_from_store(self, tmp_store: SessionStore):
        state = LearnState(exercise_type="teach", concept_a="DQN", audience="a child")
        tmp_store.put("restore-sid", "learn", state, ttl_seconds=3600)
        learn_router._states.clear()
        with patch.object(learn_router, "session_store", tmp_store):
            restored = learn_router._get_state(self._req("restore-sid"))
        assert restored.exercise_type == "teach"
        assert restored.concept_a == "DQN"
        assert restored.audience == "a child"

    def test_missing_from_store_returns_blank_state(self, tmp_store: SessionStore):
        quiz_router._states.clear()
        with patch.object(quiz_router, "session_store", tmp_store):
            restored = quiz_router._get_state(self._req("no-such-session"))
        assert restored.session is None
        assert restored.wrong_answers == []
