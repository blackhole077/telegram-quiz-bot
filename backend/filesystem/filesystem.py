import json
from pathlib import Path

from backend.backends import register_backend
from core.schemas.answer_schemas import AnswerLogEntry
from core.schemas.question_schemas import Question


@register_backend("filesystem")
class FilesystemBackend:
    """StorageBackend backed by a JSON pool file and a JSONL answer log.

    Writes are not atomic: a crash mid-save can corrupt the pool file.
    Acceptable for this system's single-user, single-process deployment.
    """

    def __init__(self, pool_path: Path, log_path: Path) -> None:
        self._pool_path = pool_path
        self._log_path = log_path

    def load_questions(self) -> list[Question]:
        try:
            data = json.loads(self._pool_path.read_text())
            return [Question.model_validate(question) for question in data]
        except FileNotFoundError:
            return []

    def save_questions(self, questions: list[Question]) -> None:
        self._pool_path.parent.mkdir(parents=True, exist_ok=True)
        self._pool_path.write_text(
            json.dumps(
                [question.model_dump(mode="json") for question in questions], indent=2
            )
        )

    def append_answer(self, entry: AnswerLogEntry) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a") as log_file:
            log_file.write(entry.model_dump_json() + "\n")

    def load_answers(self) -> list[AnswerLogEntry]:
        try:
            return [
                AnswerLogEntry.model_validate(json.loads(line))
                for line in self._log_path.read_text().splitlines()
                if line.strip()
            ]
        except FileNotFoundError:
            return []
