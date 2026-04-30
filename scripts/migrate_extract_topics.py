"""Extract topics.json from questions.json and remove domain from questions.

Reads the domain assigned to each question, builds the Topic registry,
writes data/topics.json, then strips the domain field from questions.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent / "data"


def migrate(data_dir: Path) -> None:
    questions_path = data_dir / "questions.json"
    topics_path = data_dir / "topics.json"

    questions = json.loads(questions_path.read_text())

    seen: dict[str, str] = {}
    for question in questions:
        name = question["topic"]
        domain = question.get("domain", "")
        if name not in seen:
            seen[name] = domain

    topics = [{"name": name, "domain": domain} for name, domain in sorted(seen.items())]
    topics_path.write_text(json.dumps(topics, indent=2))
    print(f"Wrote {len(topics)} topics to {topics_path}")

    for question in questions:
        question.pop("domain", None)
    questions_path.write_text(json.dumps(questions, indent=2))
    print(f"Removed domain field from {len(questions)} questions in {questions_path}")


if __name__ == "__main__":
    migrate(Path(sys.argv[1]) if len(sys.argv) > 1 else _DATA_DIR)
