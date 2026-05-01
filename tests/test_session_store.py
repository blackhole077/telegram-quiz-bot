"""Tests for frontend/web/session_store.py."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-abc123")
os.environ.setdefault("ALLOWED_USER_ID", "99999")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("LLM_API_KEY", "ollama")
os.environ.setdefault("LLM_MODEL", "qwen2.5-vl:32b")

import pytest

from core.schemas.llm_schemas import ExamProblem
from core.schemas.schemas import QuizSession
from frontend.web.schemas.schema import ExamState, LearnState, PracticeState, QuizState
from frontend.web.session_store import SessionStore


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "sessions.db")


class TestSessionStoreRoundTrip:
    def test_put_and_get_quiz_state(self, store: SessionStore):
        state = QuizState()
        state.wrong_answers = [{"question_text": "Q1", "correct_label": "A"}]
        store.put("sid1", "quiz", state, ttl_seconds=3600)
        restored = store.get("sid1", "quiz", QuizState)
        assert restored is not None
        assert restored.wrong_answers == state.wrong_answers

    def test_put_and_get_learn_state(self, store: SessionStore):
        state = LearnState(exercise_type="connect", concept_a="DQN", concept_b="DDPG")
        store.put("sid1", "learn", state, ttl_seconds=3600)
        restored = store.get("sid1", "learn", LearnState)
        assert restored is not None
        assert restored.exercise_type == "connect"
        assert restored.concept_a == "DQN"
        assert restored.concept_b == "DDPG"

    def test_put_and_get_practice_state(self, store: SessionStore):
        state = PracticeState()
        state.wrong_answers = [{"question_text": "Q2"}]
        store.put("sid1", "practice", state, ttl_seconds=3600)
        restored = store.get("sid1", "practice", PracticeState)
        assert restored is not None
        assert restored.wrong_answers == state.wrong_answers

    def test_put_and_get_exam_state(self, store: SessionStore):
        state = ExamState(
            category="RL",
            problems=[ExamProblem(number=1, prompt="What is Q?", solution="Q-values")],
        )
        store.put("sid1", "exam", state, ttl_seconds=3600)
        restored = store.get("sid1", "exam", ExamState)
        assert restored is not None
        assert restored.category == "RL"
        assert len(restored.problems) == 1
        assert restored.problems[0].number == 1

    def test_put_overwrites_existing_entry(self, store: SessionStore):
        state1 = LearnState(concept_a="DQN")
        state2 = LearnState(concept_a="PPO")
        store.put("sid1", "learn", state1, ttl_seconds=3600)
        store.put("sid1", "learn", state2, ttl_seconds=3600)
        restored = store.get("sid1", "learn", LearnState)
        assert restored is not None
        assert restored.concept_a == "PPO"

    def test_get_missing_returns_none(self, store: SessionStore):
        result = store.get("no-such-session", "quiz", QuizState)
        assert result is None

    def test_different_routers_are_isolated(self, store: SessionStore):
        quiz_state = QuizState()
        learn_state = LearnState(concept_a="DQN")
        store.put("sid1", "quiz", quiz_state, ttl_seconds=3600)
        store.put("sid1", "learn", learn_state, ttl_seconds=3600)
        restored_learn = store.get("sid1", "learn", LearnState)
        assert restored_learn is not None
        assert restored_learn.concept_a == "DQN"
        assert store.get("sid1", "quiz", QuizState) is not None


class TestSessionStoreTTL:
    def test_get_returns_none_after_ttl_expires(self, store: SessionStore):
        state = QuizState()
        store.put("sid1", "quiz", state, ttl_seconds=3600)
        # Manually expire by updating expires_at to the past
        import sqlite3

        with sqlite3.connect(str(store._db_path)) as conn:
            past = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
            conn.execute(
                "UPDATE web_sessions SET expires_at = ? WHERE session_id = ?",
                (past, "sid1"),
            )
        result = store.get("sid1", "quiz", QuizState)
        assert result is None

    def test_get_returns_state_before_ttl_expires(self, store: SessionStore):
        state = QuizState()
        store.put("sid1", "quiz", state, ttl_seconds=3600)
        result = store.get("sid1", "quiz", QuizState)
        assert result is not None


class TestSessionStoreDelete:
    def test_delete_removes_entry(self, store: SessionStore):
        state = QuizState()
        store.put("sid1", "quiz", state, ttl_seconds=3600)
        store.delete("sid1", "quiz")
        assert store.get("sid1", "quiz", QuizState) is None

    def test_delete_only_removes_matching_router(self, store: SessionStore):
        state_quiz = QuizState()
        state_learn = LearnState(concept_a="PPO")
        store.put("sid1", "quiz", state_quiz, ttl_seconds=3600)
        store.put("sid1", "learn", state_learn, ttl_seconds=3600)
        store.delete("sid1", "quiz")
        assert store.get("sid1", "quiz", QuizState) is None
        assert store.get("sid1", "learn", LearnState) is not None

    def test_delete_nonexistent_is_noop(self, store: SessionStore):
        store.delete("no-such-session", "quiz")


class TestSessionStoreCleanup:
    def test_cleanup_removes_expired_rows(self, store: SessionStore):
        import sqlite3

        state = QuizState()
        store.put("sid1", "quiz", state, ttl_seconds=3600)
        store.put("sid2", "quiz", state, ttl_seconds=3600)
        past = (datetime.utcnow() - timedelta(seconds=1)).isoformat()
        with sqlite3.connect(str(store._db_path)) as conn:
            conn.execute(
                "UPDATE web_sessions SET expires_at = ? WHERE session_id = ?",
                (past, "sid1"),
            )
        store.cleanup(datetime.utcnow())
        assert store.get("sid1", "quiz", QuizState) is None
        assert store.get("sid2", "quiz", QuizState) is not None

    def test_cleanup_with_no_expired_rows_is_noop(self, store: SessionStore):
        state = QuizState()
        store.put("sid1", "quiz", state, ttl_seconds=3600)
        store.cleanup(datetime.utcnow() - timedelta(hours=1))
        assert store.get("sid1", "quiz", QuizState) is not None


class TestSessionStoreFlushAll:
    def test_flush_all_writes_all_dict_entries(self, store: SessionStore):
        states = {
            "sid1": QuizState(),
            "sid2": QuizState(),
        }
        states["sid1"].wrong_answers = [{"q": "Q1"}]
        store.flush_all("quiz", states, ttl_seconds=3600)
        assert store.get("sid1", "quiz", QuizState) is not None
        assert store.get("sid2", "quiz", QuizState) is not None

    def test_flush_all_empty_dict_is_noop(self, store: SessionStore):
        store.flush_all("quiz", {}, ttl_seconds=3600)
