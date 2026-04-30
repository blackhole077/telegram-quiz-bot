"""Shared fixtures and test helpers.

Env vars must be set before any import of bot.bot because Settings() runs
at module level when the module is first imported.
"""

from __future__ import annotations

import os

from core.schemas.answer_schemas import AnswerLogEntry
from core.schemas.question_schemas import (HistoryEntry, PaperRef, Question,
                                           QuestionType, SourceRef)
from core.schemas.schemas import QuizSession

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-abc123")
os.environ.setdefault("ALLOWED_USER_ID", "99999")

from unittest.mock import AsyncMock, MagicMock

import pytest

ALLOWED_USER_ID = 99999


# ---------------------------------------------------------------------------
# Builder helpers (plain functions, not fixtures — call directly when you
# need multiple instances in one test).
# ---------------------------------------------------------------------------


def make_ref(doc_id: str = "REF1") -> PaperRef:
    return PaperRef(
        doc_id=doc_id,
        title="Test Paper",
        authors="Author A",
        year=2020,
        section="Ch. 1",
    )


def make_question(
    id: str = "q1",
    topic: str = "DQN",
    qtype: QuestionType = QuestionType.MULTIPLE_CHOICE,
    level: int = 1,
    next_review: str = "2026-01-01",
    history: list[HistoryEntry] | None = None,
    options: list[str] | None = None,
    correct: str = "A",
    created_date: str = "2026-01-01",
    references: list[SourceRef] | None = None,
) -> Question:
    return Question(
        id=id,
        topic=topic,
        type=qtype,
        question="What is X?",
        options=options or ["opt A", "opt B", "opt C", "opt D"],
        correct=correct,
        explanation="Because X.",
        references=references if references is not None else [make_ref()],
        created_date=created_date,
        session_date=created_date,
        level=level,
        next_review=next_review,
        history=history or [],
    )


def make_log_entry(
    qid: str = "q1",
    topic: str = "DQN",
    correct: bool = True,
    level: int = 2,
    date: str = "2026-04-01",
    doc_id: str = "REF1",
) -> AnswerLogEntry:
    return AnswerLogEntry(
        qid=qid, topic=topic, doc_id=doc_id, level=level, correct=correct, date=date
    )


def make_update(user_id: int = ALLOWED_USER_ID, text: str = "A") -> MagicMock:
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = text
    update.message.reply_text = AsyncMock(return_value=None)
    return update


def make_context(user_data: dict | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.user_data = user_data if user_data is not None else {}
    return ctx


def make_session(
    questions: list[Question],
    display_questions: list[Question] | None = None,
    cursor: int = 0,
    score: int = 0,
) -> QuizSession:
    if display_questions is None:
        display_questions = questions
    return QuizSession(
        session_ids=[q.id for q in questions],
        cursor=cursor,
        score=score,
        original_map={q.id: q for q in questions},
        display_map={q.id: q for q in display_questions},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mcq() -> Question:
    return make_question()


@pytest.fixture
def tof() -> Question:
    return make_question(
        qtype=QuestionType.TRUE_OR_FALSE,
        options=["True", "False"],
        correct="A",
    )


@pytest.fixture
def binary() -> Question:
    return make_question(
        qtype=QuestionType.BINARY_CHOICE,
        options=["Yes", "No"],
        correct="A",
    )


# ---------------------------------------------------------------------------
# LLM test doubles
# ---------------------------------------------------------------------------


class MockBackend:
    """LLMBackend test double: captures call arguments and returns a canned response."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.last_system: str = ""
        self.last_user: str = ""
        self.last_image_bytes: bytes | None = None
        self.last_media_type: str = ""

    def chat(self, system: str, user: str) -> str:
        self.last_system = system
        self.last_user = user
        self.last_image_bytes = None
        return self._response

    def chat_with_image(
        self,
        system: str,
        user: str,
        image_bytes: bytes,
        media_type: str = "image/jpeg",
    ) -> str:
        self.last_system = system
        self.last_user = user
        self.last_image_bytes = image_bytes
        self.last_media_type = media_type
        return self._response


class ErrorBackend:
    """LLMBackend test double that always raises a configurable exception."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def chat(self, system: str, user: str) -> str:
        raise self._exc

    def chat_with_image(
        self,
        system: str,
        user: str,
        image_bytes: bytes,
        media_type: str = "image/jpeg",
    ) -> str:
        raise self._exc
