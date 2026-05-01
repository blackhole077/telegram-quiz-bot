"""Tests that router state is isolated per session cookie.

Each router previously used a single module-level state object, meaning two
concurrent users would share state. These tests verify that:
  1. Each router exposes _states: dict[str, XState] (not a single _state)
  2. State written for session "aaa" does not appear under session "bbb"
  3. A helper _get_state(request) creates a fresh entry on first access
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import Request

import frontend.web.routers.exam as exam_router
import frontend.web.routers.learn as learn_router
import frontend.web.routers.practice as practice_router
import frontend.web.routers.quiz as quiz_router

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
