from pydantic import BaseModel, Field

from core.schemas.llm_schemas import ExamProblem
from core.schemas.schemas import QuizSession


class QuizState(BaseModel):
    session: QuizSession | None = None
    wrong_answers: list[dict] = Field(default_factory=list)


class LearnState(BaseModel):
    exercise_type: str = ""
    concept_a: str = ""
    concept_b: str = ""
    edge_type: str = ""
    domain_b: str = ""
    audience: str = ""
    generated_content: str = ""
    solution_steps: list[str] = Field(default_factory=list)


class PracticeState(BaseModel):
    session: QuizSession | None = None
    wrong_answers: list[dict] = Field(default_factory=list)


class ExamState(BaseModel):
    problems: list[ExamProblem] = Field(default_factory=list)
    category: str = ""
