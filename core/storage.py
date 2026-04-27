"""StorageBackend protocol — the interface that all backend implementations must satisfy."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.schemas import AnswerLogEntry, Question


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol defining the storage contract for questions and answers.

    Any class that implements all four methods satisfies this interface without
    explicit inheritance.  ``@runtime_checkable`` allows ``isinstance`` checks
    at construction time (see ``backend.make_backend``) to catch misimplemented
    backends early rather than at the first call site.

    Admin operations (individual question updates, deletions) are out of scope;
    they belong in a separate management interface.
    """

    def load_questions(self) -> list[Question]: ...
    def save_questions(self, questions: list[Question]) -> None: ...
    def append_answer(self, entry: AnswerLogEntry) -> None: ...
    def load_answers(self) -> list[AnswerLogEntry]: ...
