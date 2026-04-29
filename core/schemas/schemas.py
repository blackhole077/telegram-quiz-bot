"""Pydantic models for questions, answer history, log entries, and session state."""

from __future__ import annotations

from pydantic import BaseModel

from core.schemas.question_schemas import Question


class QuizSession(BaseModel):
    """Mutable state for one quiz session.

    ``original_map`` holds only the *due* questions (not the full pool) so
    ``service.end_session`` can merge them back into the full pool on save.
    ``display_map`` holds shuffled copies for presentation.
    """

    session_ids: list[str]
    cursor: int
    score: int
    original_map: dict[str, Question]
    display_map: dict[str, Question]

    @property
    def total(self) -> int:
        return len(self.session_ids)

    @property
    def current_id(self) -> str:
        return self.session_ids[self.cursor]

    @property
    def current_display(self) -> Question:
        return self.display_map[self.current_id]

    @property
    def current_original(self) -> Question:
        return self.original_map[self.current_id]

    @property
    def is_complete(self) -> bool:
        return self.cursor >= self.total
