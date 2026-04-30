"""Pydantic models for LLM responses and the LLMBackend Protocol.

Field names in each model must match the corresponding schema in bot/data/schemas/.
See bot/data/README.md for the full correspondence table.
"""

from __future__ import annotations

from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, BeforeValidator, Field


def _coerce_str_to_list(value: object) -> object:
    """Allow LLMs that return a bare string to be accepted as a one-item list."""
    if isinstance(value, str):
        return [value] if value else []
    return value


_StrList = Annotated[list[str], BeforeValidator(_coerce_str_to_list)]


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
    missing_concepts: _StrList = Field(default_factory=list)
    analogy_issues: _StrList = Field(default_factory=list)
    model_answer: str = ""
    error: str = ""


class BridgeQuestion(BaseModel):
    """A question that requires understanding the edge between two concepts."""

    question: str
    requires_edge: bool
    edge_type: str
    error: str = ""


class WrongTransposition(BaseModel):
    """A plausible-but-wrong application of a concept in a new domain."""

    text: str
    error: str = ""


class ScaffoldedDerivation(BaseModel):
    """A fill-in-the-blank derivation with load-bearing steps removed."""

    prompt: str
    blank_indices: list[int] = Field(default_factory=list)
    solution_steps: _StrList = Field(default_factory=list)
    error: str = ""


class RelationalGradeResult(BaseModel):
    """Grade for a free-form explanation of the relationship between two concepts."""

    correct: bool
    score: float = Field(ge=0.0, le=1.0)
    feedback: str
    missing_relational_claims: _StrList = Field(default_factory=list)
    incorrect_relational_claims: _StrList = Field(default_factory=list)
    model_answer: str = ""
    error: str = ""
