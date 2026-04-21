"""Shared fixtures and test helpers.

Env vars must be set before any import of bot.bot because Settings() runs
at module level when the module is first imported.
"""

from __future__ import annotations

import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-abc123")
os.environ.setdefault("ALLOWED_USER_ID", "99999")

from unittest.mock import AsyncMock, MagicMock

import pytest

from quiz.schemas import AnswerLogEntry, HistoryEntry, Question, QuestionType, Reference

ALLOWED_USER_ID = 99999


# ---------------------------------------------------------------------------
# Builder helpers (plain functions, not fixtures — call directly when you
# need multiple instances in one test).
# ---------------------------------------------------------------------------


def make_ref(doc_id: str = "REF1") -> Reference:
    return Reference(
        doc_id=doc_id, title="Test Paper", authors="Author A", year=2020, section="Ch. 1"
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
    references: list[Reference] | None = None,
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
    return AnswerLogEntry(qid=qid, topic=topic, doc_id=doc_id, level=level, correct=correct, date=date)


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
