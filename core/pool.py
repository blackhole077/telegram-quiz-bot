"""Load, save, and merge the question pool JSON file."""

from __future__ import annotations

import json
from pathlib import Path

from core.constants import QUESTIONS_FILE
from core.schemas.schemas import Question


def load(path: str | Path = QUESTIONS_FILE) -> list[Question]:
    """Return all questions from the JSON pool file.

    Returns an empty list if the file does not exist (e.g. first run).
    Other I/O or JSON parse errors propagate to the caller.
    """
    try:
        data = json.loads(Path(path).read_text())
        return [Question.model_validate(q) for q in data]
    except FileNotFoundError:
        return []


def save(questions: list[Question], path: str | Path = QUESTIONS_FILE) -> None:
    """Overwrite the pool file with *questions*. Creates parent dirs as needed.

    The write is not atomic; a crash mid-write can corrupt the file.
    Acceptable for this system's single-user, single-process deployment.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([q.model_dump(mode="json") for q in questions], indent=2))


def merge(existing: list[Question], new: list[Question]) -> list[Question]:
    """Add new questions, skipping any whose id already exists."""
    existing_ids = {q.id for q in existing}
    return existing + [q for q in new if q.id not in existing_ids]
