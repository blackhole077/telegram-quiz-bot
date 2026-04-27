from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_ROOT = REPO_ROOT / "data"
QUESTIONS_FILE = DATA_ROOT / "questions.json"
ANSWERS_FILE = DATA_ROOT / "answers.jsonl"

# Days until next review keyed by post-correct level.
# Roughly geometric spacing inspired by SM-2, but four fixed levels
# instead of a dynamic ease factor.
SRS_INTERVALS: dict[int, int] = {1: 1, 2: 7, 3: 16, 4: 35}
