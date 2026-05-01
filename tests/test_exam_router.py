"""Tests for the exam router solution-pairing logic."""

from __future__ import annotations

import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-abc123")
os.environ.setdefault("ALLOWED_USER_ID", "99999")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("LLM_API_KEY", "ollama")
os.environ.setdefault("LLM_MODEL", "qwen2.5-vl:32b")

from core.schemas.llm_schemas import ExamGradeResult, ExamProblem, ProblemGrade
from frontend.web.schemas.schema import ExamState


def _make_state(problems: list[ExamProblem]) -> ExamState:
    state = ExamState()
    state.problems = problems
    return state


def _make_result(grades: list[ProblemGrade]) -> ExamGradeResult:
    return ExamGradeResult(problems=grades, total_score=0.8, summary="Good work")


def _pair_solutions(
    state: ExamState, result: ExamGradeResult
) -> list[dict]:
    """Mirrors the solution-pairing logic in exam_submit."""
    from core.exam import normalise_latex

    solution_by_number = {problem.number: problem.solution for problem in state.problems}
    return [
        {
            "number": grade.number,
            "score": grade.score,
            "feedback": normalise_latex(grade.feedback),
            "solution": solution_by_number.get(grade.number, ""),
        }
        for grade in result.problems
    ]


class TestSolutionPairing:
    def test_solution_paired_by_number(self):
        problems = [
            ExamProblem(number=1, prompt="What is 1+1?", solution="Answer: 2"),
            ExamProblem(number=2, prompt="What is 2+2?", solution="Answer: 4"),
        ]
        grades = [
            ProblemGrade(number=1, score=1.0, feedback="Correct"),
            ProblemGrade(number=2, score=0.5, feedback="Partial"),
        ]
        state = _make_state(problems)
        result = _make_result(grades)

        paired = _pair_solutions(state, result)

        assert paired[0]["solution"] == "Answer: 2"
        assert paired[1]["solution"] == "Answer: 4"

    def test_mismatched_number_returns_empty_string(self):
        problems = [ExamProblem(number=1, prompt="p", solution="s")]
        grades = [ProblemGrade(number=99, score=0.0, feedback="No match")]
        state = _make_state(problems)
        result = _make_result(grades)

        paired = _pair_solutions(state, result)

        assert paired[0]["solution"] == ""

    def test_partial_match_fills_missing_with_empty(self):
        problems = [ExamProblem(number=1, prompt="p", solution="sol1")]
        grades = [
            ProblemGrade(number=1, score=1.0, feedback="ok"),
            ProblemGrade(number=2, score=0.0, feedback="missing"),
        ]
        state = _make_state(problems)
        result = _make_result(grades)

        paired = _pair_solutions(state, result)

        assert paired[0]["solution"] == "sol1"
        assert paired[1]["solution"] == ""
