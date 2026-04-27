"""Tests for quiz/pool.py — load, save, and merge."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import pool as poolmod
from core.schemas import QuestionType
from tests.conftest import make_question


class TestLoad:
    def test_missing_file_returns_empty_list(self, tmp_path):
        result = poolmod.load(tmp_path / "nonexistent.json")
        assert result == []

    def test_loads_questions_from_json(self, tmp_path):
        q = make_question(id="q1")
        p = tmp_path / "pool.json"
        poolmod.save([q], p)
        loaded = poolmod.load(p)
        assert len(loaded) == 1
        assert loaded[0].id == "q1"

    def test_preserves_all_fields(self, tmp_path):
        from core.schemas import HistoryEntry
        entry = HistoryEntry(date="2026-01-01", correct=False)
        q = make_question(id="q99", level=3, history=[entry], correct="C")
        p = tmp_path / "pool.json"
        poolmod.save([q], p)
        loaded = poolmod.load(p)
        lq = loaded[0]
        assert lq.level == 3
        assert lq.correct == "C"
        assert len(lq.history) == 1
        assert lq.history[0].correct is False

    def test_preserves_question_type(self, tmp_path):
        for qtype in QuestionType:
            opts = ["a", "b", "c", "d"] if qtype is QuestionType.MULTIPLE_CHOICE else ["a", "b"]
            q = make_question(id="qt", qtype=qtype, options=opts)
            p = tmp_path / f"pool_{qtype.name}.json"
            poolmod.save([q], p)
            loaded = poolmod.load(p)
            assert loaded[0].type is qtype

    def test_empty_json_array_returns_empty_list(self, tmp_path):
        p = tmp_path / "pool.json"
        p.write_text("[]")
        assert poolmod.load(p) == []

    def test_invalid_json_propagates_error(self, tmp_path):
        p = tmp_path / "pool.json"
        p.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            poolmod.load(p)


class TestSave:
    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "deep" / "nested" / "pool.json"
        q = make_question()
        poolmod.save([q], p)
        assert p.exists()

    def test_overwrites_existing_file(self, tmp_path):
        p = tmp_path / "pool.json"
        q1 = make_question(id="q1")
        q2 = make_question(id="q2")
        poolmod.save([q1], p)
        poolmod.save([q2], p)
        loaded = poolmod.load(p)
        assert len(loaded) == 1
        assert loaded[0].id == "q2"

    def test_saves_multiple_questions(self, tmp_path):
        qs = [make_question(id=f"q{i}") for i in range(3)]
        p = tmp_path / "pool.json"
        poolmod.save(qs, p)
        loaded = poolmod.load(p)
        assert {q.id for q in loaded} == {f"q{i}" for i in range(3)}

    def test_output_is_valid_json(self, tmp_path):
        q = make_question()
        p = tmp_path / "pool.json"
        poolmod.save([q], p)
        data = json.loads(p.read_text())
        assert isinstance(data, list)
        assert len(data) == 1


class TestMerge:
    def test_adds_new_questions(self):
        q1 = make_question(id="q1")
        q2 = make_question(id="q2")
        result = poolmod.merge([q1], [q2])
        assert len(result) == 2

    def test_skips_duplicate_ids(self):
        q1 = make_question(id="q1", level=1)
        q1_dup = make_question(id="q1", level=3)  # same id, different level
        result = poolmod.merge([q1], [q1_dup])
        assert len(result) == 1
        assert result[0].level == 1  # original preserved

    def test_empty_existing(self):
        q = make_question(id="q1")
        result = poolmod.merge([], [q])
        assert len(result) == 1

    def test_empty_new(self):
        q = make_question(id="q1")
        result = poolmod.merge([q], [])
        assert len(result) == 1

    def test_both_empty(self):
        assert poolmod.merge([], []) == []

    def test_partial_overlap(self):
        existing = [make_question(id="q1"), make_question(id="q2")]
        new = [make_question(id="q2"), make_question(id="q3")]
        result = poolmod.merge(existing, new)
        ids = [q.id for q in result]
        assert sorted(ids) == ["q1", "q2", "q3"]
