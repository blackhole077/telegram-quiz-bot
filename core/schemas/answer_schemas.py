from pydantic import BaseModel

from core.schemas.question_schemas import Question


class AnswerLogEntry(BaseModel):
    """Immutable record appended to the answer log after every response.

    Primary input for ``refinement.analyze_gaps``.

    ``doc_id`` is ``Reference.doc_id`` of the first reference, or ``""``
    when there are no references — always a string so entries can be
    grouped without special-casing ``None``.

    ``level`` is the post-update SRS level (after ``srs.advance``/
    ``srs.demote`` has run).
    """

    qid: str
    topic: str
    doc_id: str
    level: int
    correct: bool
    date: str  # YYYY-MM-DD


class AnswerOutcome(BaseModel):
    """Result of processing one answer through the service."""

    correct: bool
    graded_question: Question
