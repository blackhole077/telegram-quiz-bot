"""Concrete storage backend implementations: filesystem (JSON/JSONL) and SQLite."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.schemas.answer_schemas import AnswerLogEntry
from core.schemas.question_schemas import (HistoryEntry, PaperRef,
                                           Question, QuestionType,
                                           Reference, TextbookRef)
from core.storage import StorageBackend

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type] = {}


def register_backend(name: str):
    """Register *cls* under *name* so ``make_backend`` can find it by name.

    Used as a class decorator.  Registering the same name twice silently
    overwrites the earlier entry.
    """

    def decorator(cls):
        _REGISTRY[name] = cls
        return cls

    return decorator


def make_backend(settings) -> StorageBackend:
    """Construct and return the backend named by ``settings.storage_type``.

    Raises ``ValueError`` if the name is not in the registry.  Raises
    ``TypeError`` if the constructed instance does not satisfy ``StorageBackend``.
    """
    cls = _REGISTRY.get(settings.storage_type)
    if cls is None:
        raise ValueError(f"Unknown storage backend: {settings.storage_type!r}")
    if settings.storage_type == "sqlite":
        backend = cls(Path(settings.db_path))
    else:
        backend = cls(settings.pool_path, settings.log_path)
    if not isinstance(backend, StorageBackend):
        raise TypeError(f"{cls.__name__} does not implement StorageBackend")
    return backend


# ---------------------------------------------------------------------------
# Filesystem backend
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# SQLite backend
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id           TEXT    PRIMARY KEY,
    topic        TEXT    NOT NULL,
    type         TEXT    NOT NULL,
    question     TEXT    NOT NULL,
    correct      TEXT    NOT NULL,
    explanation  TEXT    NOT NULL,
    created_date TEXT    NOT NULL,
    session_date TEXT    NOT NULL,
    level        INTEGER NOT NULL DEFAULT 1,
    next_review  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS question_options (
    question_id TEXT    NOT NULL REFERENCES questions(id),
    position    INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    PRIMARY KEY (question_id, position)
);

CREATE TABLE IF NOT EXISTS question_references (
    question_id TEXT    NOT NULL REFERENCES questions(id),
    position    INTEGER NOT NULL,
    source_type TEXT    NOT NULL DEFAULT 'paper',
    doc_id      TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    authors     TEXT    NOT NULL,
    year        INTEGER NOT NULL,
    section     TEXT    NOT NULL,
    edition     INTEGER,
    chapter     INTEGER,
    venue       TEXT,
    doi         TEXT,
    PRIMARY KEY (question_id, position)
);

CREATE TABLE IF NOT EXISTS question_history (
    question_id TEXT    NOT NULL REFERENCES questions(id),
    position    INTEGER NOT NULL,
    date        TEXT    NOT NULL,
    correct     INTEGER NOT NULL,
    PRIMARY KEY (question_id, position)
);

CREATE TABLE IF NOT EXISTS answers (
    rowid   INTEGER PRIMARY KEY AUTOINCREMENT,
    qid     TEXT    NOT NULL,
    topic   TEXT    NOT NULL,
    doc_id  TEXT    NOT NULL,
    level   INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    date    TEXT    NOT NULL
);
"""


@register_backend("sqlite")
class SQLiteBackend:
    """StorageBackend backed by a SQLite database.

    The database is created at ``db_path`` on first use.  ``save_questions``
    replaces the entire pool in one transaction to match the filesystem
    backend's all-or-nothing write semantics.
    """

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def load_questions(self) -> list[Question]:
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT id, topic, type, question, correct, explanation, "
            "created_date, session_date, level, next_review FROM questions"
        ).fetchall()
        if not rows:
            return []

        questions = []
        for row in rows:
            qid = row[0]
            options = [
                text
                for (text,) in cur.execute(
                    "SELECT text FROM question_options WHERE question_id = ? ORDER BY position",
                    (qid,),
                ).fetchall()
            ]
            references = []
            for (source_type, doc_id, title, authors, year, section,
                 edition, chapter, venue, doi) in cur.execute(
                "SELECT source_type, doc_id, title, authors, year, section, "
                "edition, chapter, venue, doi "
                "FROM question_references WHERE question_id = ? ORDER BY position",
                (qid,),
            ).fetchall():
                if source_type == "textbook":
                    references.append(TextbookRef(
                        doc_id=doc_id, title=title, authors=authors,
                        year=year, section=section,
                        edition=edition, chapter=chapter,
                    ))
                else:
                    references.append(PaperRef(
                        doc_id=doc_id, title=title, authors=authors,
                        year=year, section=section,
                        venue=venue, doi=doi,
                    ))
            history = [
                HistoryEntry(date=date, correct=bool(correct))
                for (date, correct) in cur.execute(
                    "SELECT date, correct FROM question_history "
                    "WHERE question_id = ? ORDER BY position",
                    (qid,),
                ).fetchall()
            ]
            questions.append(
                Question(
                    id=row[0],
                    topic=row[1],
                    type=QuestionType(row[2]),
                    question=row[3],
                    correct=row[4],
                    explanation=row[5],
                    created_date=row[6],
                    session_date=row[7],
                    level=row[8],
                    next_review=row[9],
                    options=options,
                    references=references,
                    history=history,
                )
            )
        return questions

    def save_questions(self, questions: list[Question]) -> None:
        """Replace the entire question pool in one transaction."""
        with self._conn:
            self._conn.execute("DELETE FROM question_history")
            self._conn.execute("DELETE FROM question_options")
            self._conn.execute("DELETE FROM question_references")
            self._conn.execute("DELETE FROM questions")
            for question in questions:
                self._conn.execute(
                    "INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        question.id,
                        question.topic,
                        question.type.value,
                        question.question,
                        question.correct,
                        question.explanation,
                        question.created_date,
                        question.session_date,
                        question.level,
                        question.next_review,
                    ),
                )
                for position, text in enumerate(question.options):
                    self._conn.execute(
                        "INSERT INTO question_options VALUES (?,?,?)",
                        (question.id, position, text),
                    )
                for position, ref in enumerate(question.references):
                    self._conn.execute(
                        "INSERT INTO question_references VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            question.id,
                            position,
                            ref.source_type,
                            ref.doc_id,
                            ref.title,
                            ref.authors,
                            ref.year,
                            ref.section,
                            getattr(ref, "edition", None),
                            getattr(ref, "chapter", None),
                            getattr(ref, "venue", None),
                            getattr(ref, "doi", None),
                        ),
                    )
                for position, entry in enumerate(question.history):
                    self._conn.execute(
                        "INSERT INTO question_history VALUES (?,?,?,?)",
                        (question.id, position, entry.date, int(entry.correct)),
                    )

    def append_answer(self, entry: AnswerLogEntry) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO answers (qid, topic, doc_id, level, correct, date) VALUES (?,?,?,?,?,?)",
                (
                    entry.qid,
                    entry.topic,
                    entry.doc_id,
                    entry.level,
                    int(entry.correct),
                    entry.date,
                ),
            )

    def load_answers(self) -> list[AnswerLogEntry]:
        rows = self._conn.execute(
            "SELECT qid, topic, doc_id, level, correct, date FROM answers ORDER BY rowid"
        ).fetchall()
        return [
            AnswerLogEntry(
                qid=qid,
                topic=topic,
                doc_id=doc_id,
                level=level,
                correct=bool(correct),
                date=date,
            )
            for (qid, topic, doc_id, level, correct, date) in rows
        ]
