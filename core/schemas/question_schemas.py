"""Pydantic models for questions, answer history, log entries, and session state."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "mcq"
    TRUE_OR_FALSE = "truefalse"
    BINARY_CHOICE = "binary"


class Reference(BaseModel):
    """A bibliographic reference attached to a question.

    ``doc_id`` uses the format ``<AUTHOR_YEAR_KEYWORD>`` (e.g.
    ``"SUTTON_2018_RL"``); must be unique within a question's reference
    list and is used as the ``doc_id`` key in ``AnswerLogEntry``.
    ``section`` is a chapter, section, or page range (e.g. ``"Ch. 6"``).
    """

    doc_id: str
    title: str
    authors: str
    year: int
    section: str


class HistoryEntry(BaseModel):
    """One attempt record appended by ``srs.advance``/``srs.demote``; never edited."""

    date: str  # YYYY-MM-DD
    correct: bool


class Question(BaseModel):
    """A single quiz question with SRS scheduling state.

    ``type`` semantics:
    - ``"mcq"``       — 4 options (A-D); ``correct`` is a letter label.
    - ``"truefalse"`` — 2 options; ``correct`` is ``"A"`` (True) or
                        ``"B"`` (False); option order is never shuffled.
    - ``"binary"``    — 2 options where neither is literally True/False;
                        rendered like ``truefalse`` but text is not fixed.

    ``references``: first entry (index 0) is displayed to the learner
    and logged.

    ``created_date`` orders new questions for introduction (oldest first);
    ``session_date`` may differ if questions are backfilled after the
    session occurred.

    SRS levels (1-4): level 1 reviews next day; 2 after 7 d; 3 after
    16 d; 4 after 35 d.  ``next_review`` is initialised to ``created_date``
    so new questions appear immediately.  An empty ``history`` means the
    question has never been answered.
    """

    id: str
    topic: str
    type: QuestionType
    question: str
    options: list[str]
    correct: str
    explanation: str
    references: list[Reference]
    created_date: str
    session_date: str
    level: int = 1
    next_review: str  # YYYY-MM-DD
    history: list[HistoryEntry] = []


class DifficultQuestion(BaseModel):
    """A Question the learner consistently struggles with, derived from SRS history."""

    question: Question
    correct_answer_rate: float
    reference_material: Reference | None
    related_material: list[str] = []
