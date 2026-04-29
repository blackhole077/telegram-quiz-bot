"""Tests for core/exam.py -- LaTeX/tectonic PDF generation."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-abc123")
os.environ.setdefault("ALLOWED_USER_ID", "99999")

from core.constants import REMEDIAL_TEMPLATE_SRC
from core.exam import _build_content, _escape, render_exam_pdf
from core.schemas.llm_schemas import ExamProblem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _problems(num_exam_problem: int = 2) -> list[ExamProblem]:
    return [
        ExamProblem(
            number=i + 1,
            topic=f"Topic {i + 1}",
            prompt=f"Problem {i + 1} prompt.",
            solution=f"Solution {i + 1}.",
        )
        for i in range(num_exam_problem)
    ]


def _latex_problems() -> list[ExamProblem]:
    return [
        ExamProblem(
            number=1,
            topic="Linear Algebra",
            prompt=r"Find the eigenvalues of $A = \begin{pmatrix} 3 & 1 \\ 0 & 2 \end{pmatrix}$.",
            solution=r"$(3-\lambda)(2-\lambda)=0$, so $\lambda_1=3,\ \lambda_2=2$.",
        )
    ]


# ---------------------------------------------------------------------------
# _escape
# ---------------------------------------------------------------------------


class TestEscape:
    def test_plain_text_unchanged(self):
        assert _escape("hello world") == "hello world"

    def test_ampersand(self):
        assert _escape("A & B") == r"A \& B"

    def test_percent(self):
        assert _escape("50%") == r"50\%"

    def test_dollar(self):
        assert _escape("$10") == r"\$10"

    def test_hash(self):
        assert _escape("#1") == r"\#1"

    def test_underscore(self):
        assert _escape("x_y") == r"x\_y"

    def test_braces(self):
        assert _escape("{a}") == r"\{a\}"

    def test_backslash(self):
        assert r"\textbackslash{}" in _escape("a\\b")

    def test_empty_string(self):
        assert _escape("") == ""


# ---------------------------------------------------------------------------
# _build_content
# ---------------------------------------------------------------------------


class TestBuildContent:
    def test_returns_string(self):
        assert isinstance(_build_content(_problems()), str)

    def test_problem_command_count(self):
        result = _build_content(_problems(num_exam_problem=3))
        assert result.count(r"\problem{") == 3

    def test_solution_command_count(self):
        result = _build_content(_problems(num_exam_problem=3))
        assert result.count(r"\solution{") == 3

    def test_contains_working_space(self):
        assert r"\vspace" in _build_content(_problems())

    def test_answer_key_section_present(self):
        assert r"\section*{Answer Key}" in _build_content(_problems())

    def test_newpage_before_answer_key(self):
        assert r"\newpage" in _build_content(_problems())

    def test_topic_in_output(self):
        p = [ExamProblem(number=1, topic="Eigenvalues", prompt="p", solution="s")]
        assert "Eigenvalues" in _build_content(p)

    def test_prompt_and_solution_in_output(self):
        p = [
            ExamProblem(number=1, topic="T", prompt="my prompt", solution="my solution")
        ]
        result = _build_content(p)
        assert "my prompt" in result
        assert "my solution" in result

    def test_empty_list_still_has_answer_key(self):
        assert r"\section*{Answer Key}" in _build_content([])

    def test_remedial_problem_uses_rproblem_command(self):
        p = ExamProblem(number=1, topic="T", prompt="p", solution="s", is_remedial=True)
        result = _build_content([p])
        assert r"\rproblem{" in result
        assert r"\problem{" not in result

    def test_remedial_problem_uses_rsolution_command(self):
        p = ExamProblem(number=1, topic="T", prompt="p", solution="s", is_remedial=True)
        result = _build_content([p])
        assert r"\rsolution{" in result
        assert r"\solution{" not in result

    def test_non_remedial_uses_standard_commands(self):
        p = ExamProblem(
            number=1, topic="T", prompt="p", solution="s", is_remedial=False
        )
        result = _build_content([p])
        assert r"\problem{" in result
        assert r"\solution{" in result
        assert r"\rproblem{" not in result
        assert r"\rsolution{" not in result

    def test_mixed_uses_both_command_sets(self):
        problems = [
            ExamProblem(
                number=1, topic="T1", prompt="p1", solution="s1", is_remedial=True
            ),
            ExamProblem(
                number=2, topic="T2", prompt="p2", solution="s2", is_remedial=False
            ),
        ]
        result = _build_content(problems)
        assert r"\rproblem{" in result
        assert r"\problem{" in result


# ---------------------------------------------------------------------------
# render_exam_pdf
# ---------------------------------------------------------------------------


class TestRenderExamPdf:
    def test_returns_valid_pdf(self):
        result = render_exam_pdf(_problems(), "Test Category", "2026-04-28")
        assert isinstance(result, bytes)
        assert result[:4] == b"%PDF"

    def test_multiple_problems(self):
        result = render_exam_pdf(_problems(num_exam_problem=5), "Linear Algebra", "2026-04-28")
        assert result[:4] == b"%PDF"

    def test_full_latex_including_pmatrix(self):
        result = render_exam_pdf(_latex_problems(), "Math", "2026-04-28")
        assert result[:4] == b"%PDF"

    def test_empty_problem_list(self):
        result = render_exam_pdf([], "Empty Exam", "2026-04-28")
        assert result[:4] == b"%PDF"

    def test_all_remedial_problems_produces_valid_pdf(self):
        problems = [
            ExamProblem(
                number=1, topic="DQN", prompt="p", solution="s", is_remedial=True
            )
        ]
        result = render_exam_pdf(problems, "DQN", "2026-04-28")
        assert result[:4] == b"%PDF"

    def test_remedial_template_contains_remedial_review(self):
        assert "Remedial Review" in REMEDIAL_TEMPLATE_SRC

    def test_raises_on_compiler_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "tectonic: fatal error"
        with patch("core.exam.subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="tectonic failed"):
                render_exam_pdf(_problems(), "Bad Exam", "2026-04-28")
