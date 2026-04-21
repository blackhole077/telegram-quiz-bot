"""Tests for quiz/log.py — JSONL append and load."""

from __future__ import annotations

import json

import pytest

from quiz import log as logmod
from quiz.schemas import AnswerLogEntry
from tests.conftest import make_log_entry


class TestAppend:
    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "deep" / "nested" / "answers.jsonl"
        logmod.append(make_log_entry(), p)
        assert p.exists()

    def test_writes_valid_json_line(self, tmp_path):
        p = tmp_path / "answers.jsonl"
        entry = make_log_entry(qid="q1", correct=True)
        logmod.append(entry, p)
        lines = p.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["qid"] == "q1"
        assert data["correct"] is True

    def test_appends_multiple_entries(self, tmp_path):
        p = tmp_path / "answers.jsonl"
        for i in range(3):
            logmod.append(make_log_entry(qid=f"q{i}"), p)
        lines = p.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_append_does_not_overwrite(self, tmp_path):
        p = tmp_path / "answers.jsonl"
        logmod.append(make_log_entry(qid="q1"), p)
        logmod.append(make_log_entry(qid="q2"), p)
        loaded = logmod.load(p)
        assert {e.qid for e in loaded} == {"q1", "q2"}


class TestLoad:
    def test_missing_file_returns_empty_list(self, tmp_path):
        result = logmod.load(tmp_path / "nonexistent.jsonl")
        assert result == []

    def test_loads_single_entry(self, tmp_path):
        p = tmp_path / "answers.jsonl"
        logmod.append(make_log_entry(qid="q1", correct=False, level=1), p)
        loaded = logmod.load(p)
        assert len(loaded) == 1
        assert loaded[0].qid == "q1"
        assert loaded[0].correct is False

    def test_loads_multiple_entries_in_order(self, tmp_path):
        p = tmp_path / "answers.jsonl"
        entries = [make_log_entry(qid=f"q{i}", date=f"2026-04-{i+1:02d}") for i in range(5)]
        for e in entries:
            logmod.append(e, p)
        loaded = logmod.load(p)
        assert [e.qid for e in loaded] == [f"q{i}" for i in range(5)]

    def test_blank_lines_skipped(self, tmp_path):
        p = tmp_path / "answers.jsonl"
        entry = make_log_entry(qid="q1")
        p.write_text("\n" + entry.model_dump_json() + "\n\n")
        loaded = logmod.load(p)
        assert len(loaded) == 1

    def test_corrupt_line_raises(self, tmp_path):
        p = tmp_path / "answers.jsonl"
        p.write_text('{"qid": "q1"' + "\nnot json\n")
        with pytest.raises(json.JSONDecodeError):
            logmod.load(p)

    def test_roundtrip_preserves_all_fields(self, tmp_path):
        p = tmp_path / "answers.jsonl"
        entry = make_log_entry(qid="q42", topic="PPO", correct=False, level=3, date="2026-03-15", doc_id="DOC99")
        logmod.append(entry, p)
        loaded = logmod.load(p)
        e = loaded[0]
        assert e.qid == "q42"
        assert e.topic == "PPO"
        assert e.correct is False
        assert e.level == 3
        assert e.date == "2026-03-15"
        assert e.doc_id == "DOC99"
