"""ExamService: business logic for exam generation and grading.

Owns calls to generate_exam and grade_from_text. The web router calls these
methods and renders templates from the returned data.
"""

from __future__ import annotations

from core.exam import normalise_latex
from core.llm import generate_exam, grade_from_text
from core.schemas.llm_schemas import ExamGradeResult, ExamProblem


class ExamService:
    """Generates and grades open-ended exams via LLM."""

    def generate(
        self,
        category: str,
        count: int,
        weak_topics: list[str],
    ) -> list[ExamProblem]:
        """Generate exam problems, normalising LaTeX in prompts and solutions."""
        problems = generate_exam(category, count, weak_topics)
        return [
            problem.model_copy(
                update={
                    "prompt": normalise_latex(problem.prompt),
                    "solution": normalise_latex(problem.solution),
                }
            )
            for problem in problems
        ]

    def grade(
        self,
        problems: list[ExamProblem],
        answers: list[str],
    ) -> ExamGradeResult:
        """Grade a list of student answers against the given problems."""
        answer_text = "\n\n".join(
            f"{idx + 1}. {ans}" for idx, ans in enumerate(answers)
        )
        return grade_from_text(problems, answer_text)
