"""Problem bank: model and loader for hand-authored practice problems."""

from __future__ import annotations

import json
import random
from pathlib import Path

from pydantic import BaseModel


class Problem(BaseModel):
    id: str
    topic: str
    prompt: str
    solution_steps: str
    difficulty: int  # 1-3; soft hint passed to LLM grader
    uses_latex: bool


def load_problems(path: str | Path) -> list[Problem]:
    data = json.loads(Path(path).read_text())
    return [Problem.model_validate(item) for item in data]


def filter_by_topic(problems: list[Problem], topic: str) -> list[Problem]:
    key = topic.lower()
    return [p for p in problems if p.topic.lower() == key]


def pick_random(problems: list[Problem], n: int = 1) -> list[Problem]:
    return random.sample(problems, min(n, len(problems)))
