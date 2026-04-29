"""Tests for core/problems.py."""

from __future__ import annotations

import json
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-abc123")
os.environ.setdefault("ALLOWED_USER_ID", "99999")

import pytest

from core.question import filter_by_topic, load_problems, pick_random
from core.schemas.question_schemas import Problem

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE = [
    {
        "id": "p1",
        "topic": "Linear Algebra",
        "prompt": "Find the eigenvalues of [[1,2],[3,4]].",
        "solution_steps": "det(A - lambda*I) = 0 ...",
        "difficulty": 2,
        "uses_latex": False,
    },
    {
        "id": "p2",
        "topic": "Probability",
        "prompt": "Bayes theorem problem.",
        "solution_steps": "P(A|B) = ...",
        "difficulty": 1,
        "uses_latex": False,
    },
    {
        "id": "p3",
        "topic": "linear algebra",  # intentional case variation
        "prompt": "Prove a matrix is invertible.",
        "solution_steps": "det != 0 ...",
        "difficulty": 3,
        "uses_latex": False,
    },
]


@pytest.fixture
def problems_file(tmp_path):
    path = tmp_path / "problems.json"
    path.write_text(json.dumps(_SAMPLE))
    return path


@pytest.fixture
def problems():
    return [Problem.model_validate(item) for item in _SAMPLE]


# ---------------------------------------------------------------------------
# load_problems
# ---------------------------------------------------------------------------

class TestLoadProblems:
    def test_returns_list_of_problems(self, problems_file):
        result = load_problems(problems_file)
        assert len(result) == 3
        assert all(isinstance(p, Problem) for p in result)

    def test_fields_preserved(self, problems_file):
        result = load_problems(problems_file)
        assert result[0].id == "p1"
        assert result[0].topic == "Linear Algebra"
        assert result[0].difficulty == 2

    def test_empty_file_returns_empty_list(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("[]")
        assert load_problems(path) == []

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_problems(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# filter_by_topic
# ---------------------------------------------------------------------------

class TestFilterByTopic:
    def test_exact_match(self, problems):
        result = filter_by_topic(problems, "Probability")
        assert len(result) == 1
        assert result[0].id == "p2"

    def test_case_insensitive(self, problems):
        result = filter_by_topic(problems, "linear algebra")
        assert len(result) == 2
        assert {p.id for p in result} == {"p1", "p3"}

    def test_no_match_returns_empty(self, problems):
        result = filter_by_topic(problems, "Thermodynamics")
        assert result == []

    def test_empty_input_returns_empty(self):
        assert filter_by_topic([], "RL") == []


# ---------------------------------------------------------------------------
# pick_random
# ---------------------------------------------------------------------------

class TestPickRandom:
    def test_returns_one_by_default(self, problems):
        result = pick_random(problems)
        assert len(result) == 1

    def test_returns_n_items(self, problems):
        result = pick_random(problems, n=2)
        assert len(result) == 2

    def test_n_larger_than_pool_returns_whole_pool(self, problems):
        result = pick_random(problems, n=100)
        assert len(result) == len(problems)

    def test_result_is_subset_of_input(self, problems):
        result = pick_random(problems, n=2)
        ids = {p.id for p in result}
        assert ids <= {p.id for p in problems}

    def test_empty_pool_returns_empty(self):
        assert pick_random([]) == []
