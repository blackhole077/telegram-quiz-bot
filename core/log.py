"""Append and load answer log entries from a JSONL file."""

from __future__ import annotations

import json
from pathlib import Path

from core.constants import ANSWERS_FILE
from core.schemas.schemas import AnswerLogEntry


def append(entry: AnswerLogEntry, path: str | Path = ANSWERS_FILE) -> None:
    """Append *entry* as a JSON line. Creates parent dirs as needed.

    The log is strictly append-only and grows unboundedly; no rotation
    or pruning mechanism exists.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(entry.model_dump_json() + "\n")


def load(path: str | Path = ANSWERS_FILE) -> list[AnswerLogEntry]:
    """Return all log entries in file order. Returns ``[]`` if file absent.

    ``json.JSONDecodeError`` on any non-blank line is intentionally not
    caught so that data corruption is surfaced immediately.
    """
    try:
        return [
            AnswerLogEntry.model_validate(json.loads(line))
            for line in Path(path).read_text().splitlines()
            if line.strip()
        ]
    except FileNotFoundError:
        return []
