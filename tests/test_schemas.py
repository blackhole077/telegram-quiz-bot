"""Tests for quiz/schemas.py — Pydantic models and serialisation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.schemas import AnswerLogEntry, HistoryEntry, Question, QuestionType, Reference
from tests.conftest import make_log_entry, make_question, make_ref


class TestQuestionType:
    def test_members_exist(self):
        assert QuestionType.MULTIPLE_CHOICE
        assert QuestionType.TRUE_OR_FALSE
        assert QuestionType.BINARY_CHOICE

    def test_validate_by_integer_value(self):
        for member in QuestionType:
            assert QuestionType(member.value) is member

    def test_validate_by_string_name(self):
        assert QuestionType["MULTIPLE_CHOICE"] is QuestionType.MULTIPLE_CHOICE

    def test_roundtrip_via_model_dump(self):
        q = make_question(qtype=QuestionType.MULTIPLE_CHOICE)
        dumped = q.model_dump()
        restored = Question.model_validate(dumped)
        assert restored.type is QuestionType.MULTIPLE_CHOICE

    def test_roundtrip_all_types(self):
        for qtype in QuestionType:
            opts = ["A", "B", "C", "D"] if qtype is QuestionType.MULTIPLE_CHOICE else ["A", "B"]
            q = make_question(qtype=qtype, options=opts)
            restored = Question.model_validate(q.model_dump())
            assert restored.type is qtype


class TestQuestionModel:
    def test_defaults(self):
        q = make_question()
        assert q.level == 1
        assert q.history == []

    def test_history_entry_appended(self):
        entry = HistoryEntry(date="2026-01-01", correct=True)
        q = make_question(history=[entry])
        assert len(q.history) == 1
        assert q.history[0].correct is True

    def test_immutability_of_history_list(self):
        q = make_question()
        original_history = q.history
        q2 = q.model_copy(update={"history": [HistoryEntry(date="2026-01-01", correct=True)]})
        assert q.history is original_history
        assert len(q2.history) == 1

    def test_references_optional_empty(self):
        q = make_question(references=[])
        assert q.references == []

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Question.model_validate({"id": "q1"})

    def test_model_dump_roundtrip_preserves_all_fields(self):
        ref = make_ref("MNIH_2013")
        entry = HistoryEntry(date="2026-03-01", correct=False)
        q = make_question(level=3, history=[entry], references=[ref], correct="C")
        restored = Question.model_validate(q.model_dump())
        assert restored.id == q.id
        assert restored.level == 3
        assert restored.correct == "C"
        assert len(restored.history) == 1
        assert restored.history[0].correct is False
        assert restored.references[0].doc_id == "MNIH_2013"


class TestAnswerLogEntry:
    def test_construction(self):
        entry = make_log_entry(qid="q1", correct=True)
        assert entry.qid == "q1"
        assert entry.correct is True

    def test_empty_doc_id_allowed(self):
        # doc_id is "" when a question has no references — must not be None
        entry = make_log_entry(doc_id="")
        assert entry.doc_id == ""

    def test_json_roundtrip(self):
        entry = make_log_entry(qid="q1", doc_id="R1", level=2, correct=True, date="2026-04-01")
        restored = AnswerLogEntry.model_validate_json(entry.model_dump_json())
        assert restored == entry
