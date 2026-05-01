from pydantic import BaseModel, Field

from core.schemas.llm_schemas import ExamProblem
from core.schemas.schemas import QuizSession


class QuizState(BaseModel):
    """Represents the current state of a quiz session including progress and errors.

    Attributes:
        session (QuizSession | None): The active quiz session or None if not started.
        wrong_answers (list[dict]): List of incorrect answers with details."""

    session: QuizSession | None = None
    # TODO: Make this another Pydantic schema
    wrong_answers: list[dict] = Field(default_factory=list)


class LearnState(BaseModel):
    """Represents the state during a learning exercise, tracking concepts and progress.

    Attributes:
        exercise_type (str): Type of exercise being conducted.
        concept_a (str): First concept involved in the exercise.
        concept_b (str): Second concept involved in the exercise.
        edge_type (str): Relationship type between concepts.
        domain_b (str): Domain related to the second concept.
        audience (str): Target audience for the generated content.
        generated_content (str): Content created during the exercise.
        solution_steps (list[str]): Steps taken to solve the problem."""

    exercise_type: str = ""
    concept_a: str = ""
    concept_b: str = ""
    edge_type: str = ""
    domain_b: str = ""
    audience: str = ""
    generated_content: str = ""
    solution_steps: list[str] = Field(default_factory=list)


class PracticeState(BaseModel):
    """Represents the state during a practice session, tracking progress and errors.

    Attributes:
        session (QuizSession | None): The active practice session or None if not started.
        wrong_answers (list[dict]): List of incorrect answers with details."""

    session: QuizSession | None = None
    wrong_answers: list[dict] = Field(default_factory=list)


class ExamState(BaseModel):
    """Represents the state during an exam, tracking problems and category.

    Attributes:
        problems (list[ExamProblem]): List of exam problems to be solved.
        category (str): Category or type of exam."""

    problems: list[ExamProblem] = Field(default_factory=list)
    category: str = ""
