"""Tests for FilesystemBackend — answer log and question pool."""

from __future__ import annotations

import json

import pytest

from backend.backends import FilesystemBackend
from core.schemas.question_schemas import HistoryEntry, QuestionType
from tests.conftest import make_log_entry, make_question


@pytest.fixture
def backend(tmp_path):
    return FilesystemBackend(tmp_path / "pool.json", tmp_path / "answers.jsonl")


# ---------------------------------------------------------------------------
# append_answer / load_answers
# ---------------------------------------------------------------------------


class TestAppendAnswer:
    def test_creates_parent_dirs(self, tmp_path):
        nested = FilesystemBackend(
            tmp_path / "pool.json",
            tmp_path / "deep" / "nested" / "answers.jsonl",
        )
        nested.append_answer(make_log_entry())
        assert (tmp_path / "deep" / "nested" / "answers.jsonl").exists()

    def test_writes_valid_json_line(self, backend, tmp_path):
        entry = make_log_entry(qid="q1", correct=True)
        backend.append_answer(entry)
        lines = (tmp_path / "answers.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["qid"] == "q1"
        assert data["correct"] is True

    def test_appends_multiple_entries(self, backend, tmp_path):
        for i in range(3):
            backend.append_answer(make_log_entry(qid=f"q{i}"))
        lines = (tmp_path / "answers.jsonl").read_text().strip().splitlines()
        assert len(lines) == 3

    def test_does_not_overwrite(self, backend):
        backend.append_answer(make_log_entry(qid="q1"))
        backend.append_answer(make_log_entry(qid="q2"))
        loaded = backend.load_answers()
        assert {entry.qid for entry in loaded} == {"q1", "q2"}


class TestLoadAnswers:
    def test_missing_file_returns_empty_list(self, backend):
        assert backend.load_answers() == []

    def test_loads_single_entry(self, backend):
        backend.append_answer(make_log_entry(qid="q1", correct=False, level=1))
        loaded = backend.load_answers()
        assert len(loaded) == 1
        assert loaded[0].qid == "q1"
        assert loaded[0].correct is False

    def test_loads_entries_in_order(self, backend):
        entries = [make_log_entry(qid=f"q{i}", date=f"2026-04-{i+1:02d}") for i in range(5)]
        for entry in entries:
            backend.append_answer(entry)
        loaded = backend.load_answers()
        assert [entry.qid for entry in loaded] == [f"q{i}" for i in range(5)]

    def test_blank_lines_skipped(self, backend, tmp_path):
        entry = make_log_entry(qid="q1")
        (tmp_path / "answers.jsonl").write_text("\n" + entry.model_dump_json() + "\n\n")
        assert len(backend.load_answers()) == 1

    def test_corrupt_line_raises(self, backend, tmp_path):
        (tmp_path / "answers.jsonl").write_text('{"qid": "q1"' + "\nnot json\n")
        with pytest.raises(json.JSONDecodeError):
            backend.load_answers()

    def test_roundtrip_preserves_all_fields(self, backend):
        entry = make_log_entry(qid="q42", topic="PPO", correct=False, level=3, date="2026-03-15", doc_id="DOC99")
        backend.append_answer(entry)
        loaded = backend.load_answers()[0]
        assert loaded.qid == "q42"
        assert loaded.topic == "PPO"
        assert loaded.correct is False
        assert loaded.level == 3
        assert loaded.date == "2026-03-15"
        assert loaded.doc_id == "DOC99"


# ---------------------------------------------------------------------------
# load_questions / save_questions
# ---------------------------------------------------------------------------


class TestLoadQuestions:
    def test_missing_file_returns_empty_list(self, backend):
        assert backend.load_questions() == []

    def test_loads_questions(self, backend):
        backend.save_questions([make_question(id="q1")])
        loaded = backend.load_questions()
        assert len(loaded) == 1
        assert loaded[0].id == "q1"

    def test_preserves_all_fields(self, backend):
        history_entry = HistoryEntry(date="2026-01-01", correct=False)
        question = make_question(id="q99", level=3, history=[history_entry], correct="C")
        backend.save_questions([question])
        loaded = backend.load_questions()[0]
        assert loaded.level == 3
        assert loaded.correct == "C"
        assert len(loaded.history) == 1
        assert loaded.history[0].correct is False

    def test_preserves_question_type(self, backend):
        for qtype in QuestionType:
            opts = ["a", "b", "c", "d"] if qtype is QuestionType.MULTIPLE_CHOICE else ["a", "b"]
            question = make_question(id="qt", qtype=qtype, options=opts)
            backend.save_questions([question])
            assert backend.load_questions()[0].type is qtype

    def test_empty_pool_returns_empty_list(self, backend, tmp_path):
        (tmp_path / "pool.json").write_text("[]")
        assert backend.load_questions() == []

    def test_invalid_json_propagates_error(self, backend, tmp_path):
        (tmp_path / "pool.json").write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            backend.load_questions()


class TestSaveQuestions:
    def test_creates_parent_dirs(self, tmp_path):
        nested = FilesystemBackend(
            tmp_path / "deep" / "nested" / "pool.json",
            tmp_path / "answers.jsonl",
        )
        nested.save_questions([make_question()])
        assert (tmp_path / "deep" / "nested" / "pool.json").exists()

    def test_overwrites_existing(self, backend):
        backend.save_questions([make_question(id="q1")])
        backend.save_questions([make_question(id="q2")])
        loaded = backend.load_questions()
        assert len(loaded) == 1
        assert loaded[0].id == "q2"

    def test_saves_multiple_questions(self, backend):
        questions = [make_question(id=f"q{i}") for i in range(3)]
        backend.save_questions(questions)
        loaded = backend.load_questions()
        assert {question.id for question in loaded} == {f"q{i}" for i in range(3)}

    def test_output_is_valid_json(self, backend, tmp_path):
        backend.save_questions([make_question()])
        data = json.loads((tmp_path / "pool.json").read_text())
        assert isinstance(data, list)
        assert len(data) == 1
