"""Tests for core.exam_service.ExamService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.exam_service import ExamService
from core.schemas.llm_schemas import ExamGradeResult, ExamProblem


def _make_problem(prompt: str = "Solve x=1", solution: str = "x=1") -> ExamProblem:
    problem = MagicMock(spec=ExamProblem)
    problem.prompt = prompt
    problem.solution = solution
    problem.model_copy.return_value = problem
    return problem


def _make_grade_result(total_score: float = 0.8) -> ExamGradeResult:
    result = MagicMock(spec=ExamGradeResult)
    result.total_score = total_score
    result.summary = "Good work."
    result.problems = []
    result.error = ""
    return result


class TestExamServiceGenerate:
    @patch("core.exam_service.generate_exam")
    def test_returns_normalised_problems(self, mock_generate):
        mock_problem = _make_problem()
        mock_generate.return_value = [mock_problem]

        service = ExamService()
        problems = service.generate("RL", count=1, weak_topics=[])

        assert len(problems) == 1

    @patch("core.exam_service.generate_exam")
    def test_returns_empty_list_on_llm_failure(self, mock_generate):
        mock_generate.return_value = []

        service = ExamService()
        problems = service.generate("RL", count=3, weak_topics=[])

        assert problems == []

    @patch("core.exam_service.generate_exam")
    def test_passes_args_to_generate_exam(self, mock_generate):
        mock_generate.return_value = []

        service = ExamService()
        service.generate("calculus", count=4, weak_topics=["integration"])

        mock_generate.assert_called_once_with("calculus", 4, ["integration"])


class TestExamServiceGrade:
    @patch("core.exam_service.grade_from_text")
    def test_returns_grade_result(self, mock_grade):
        mock_grade.return_value = _make_grade_result(total_score=0.75)
        problems = [_make_problem()]

        service = ExamService()
        result = service.grade(problems, ["answer one"])

        assert result.total_score == pytest.approx(0.75)

    @patch("core.exam_service.grade_from_text")
    def test_formats_answers_for_llm(self, mock_grade):
        mock_grade.return_value = _make_grade_result()
        problems = [_make_problem()]

        service = ExamService()
        service.grade(problems, ["first answer", "second answer"])

        call_args = mock_grade.call_args[0]
        answer_text = call_args[1]
        assert "1. first answer" in answer_text
        assert "2. second answer" in answer_text
