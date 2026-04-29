"""Pydantic models for LLM responses and the LLMBackend Protocol.

Field names in each model must match the corresponding schema in bot/data/schemas/.
See bot/data/README.md for the full correspondence table.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


@runtime_checkable
class LLMBackend(Protocol):
    """Interface any LLM provider must satisfy.

    Concrete implementations (e.g. ``_OpenAIBackend`` in ``bot/llm.py``) swap
    in transparently by changing env vars - no function signatures change.
    """

    def chat(self, system: str, user: str) -> str: ...

    def chat_with_image(
        self,
        system: str,
        user: str,
        image_bytes: bytes,
        media_type: str = "image/jpeg",
    ) -> str: ...


class GradeResult(BaseModel):
    """Result of grading a single free-text practice answer."""

    correct: bool
    score: float = Field(ge=0.0, le=1.0)
    feedback: str
    model_solution: str
    error: str = ""


class ExamProblem(BaseModel):
    """A single generated exam problem with its worked solution."""

    number: int
    topic: str = ""
    prompt: str
    solution: str
    is_remedial: bool = False


class Problem(BaseModel):
    id: str
    topic: str
    prompt: str
    solution_steps: str
    difficulty: int  # 1-3; soft hint passed to LLM grader
    uses_latex: bool


class ProblemGrade(BaseModel):
    """Per-problem score and feedback within an ExamGradeResult."""

    number: int
    score: float = Field(ge=0.0, le=1.0)
    feedback: str


class ExamGradeResult(BaseModel):
    """Result of grading a full exam (text or image submission)."""

    problems: list[ProblemGrade] = Field(default_factory=list)
    total_score: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str = ""
    error: str = ""


class TeachItBackResult(BaseModel):
    """Result of grading a teach-it-back exercise."""

    score: float = Field(ge=0.0, le=1.0)
    feedback: str
    missing_concepts: list[str] = Field(default_factory=list)
    analogy_issues: list[str] = Field(default_factory=list)
    error: str = ""
