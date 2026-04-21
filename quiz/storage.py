"""Storage backends for the question pool and answer log."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Protocol, runtime_checkable

from quiz.schemas import AnswerLogEntry, HistoryEntry, Question, QuestionType, Reference

# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type] = {}


def register_backend(name: str):
    """Register *cls* under *name* in the backend registry.

    Used as a class decorator.  *name* is the value of ``Settings.storage_type``
    that selects this backend (e.g. ``"sqlite"``).  Registering the same name
    twice silently overwrites the earlier entry.
    """
    def decorator(cls):
        _REGISTRY[name] = cls
        return cls
    return decorator


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol defining the storage contract for questions and answers.

    Any class that implements all four methods satisfies this interface without
    explicit inheritance.  ``@runtime_checkable`` allows ``isinstance`` checks
    at construction time (see ``make_backend``) to catch misimplemented backends
    early rather than at the first call site inside the bot.

    This protocol covers only the operations the bot requires.  Admin operations
    (individual question updates, deletions) are out of scope; they belong in a
    separate management interface.
    """

    def load_questions(self) -> list[Question]: ...
    def save_questions(self, questions: list[Question]) -> None: ...
    def append_answer(self, entry: AnswerLogEntry) -> None: ...
    def load_answers(self) -> list[AnswerLogEntry]: ...


def make_backend(settings) -> StorageBackend:
    """Construct and return the backend named by ``settings.storage_type``.

    Raises ``ValueError`` if the name is not in the registry.  Raises
    ``TypeError`` if the constructed instance does not satisfy ``StorageBackend``
    — this guards against backends registered with an incomplete implementation.
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
    """StorageBackend that reads and writes plain files.

    Questions are stored as a JSON array at ``pool_path``; answers are stored as
    a JSONL append-only log at ``log_path``.  Both paths default to the values
    configured in ``Settings`` and are created on first write.

    Writes are not atomic: a crash mid-save can corrupt the pool file.
    Acceptable for this system's single-user, single-process deployment.
    """

    def __init__(self, pool_path: Path, log_path: Path) -> None:
        self._pool_path = pool_path
        self._log_path = log_path

    def load_questions(self) -> list[Question]:
        """Return all questions from the JSON pool file.

        Returns ``[]`` if the file does not exist (e.g. first run).
        Other I/O or parse errors propagate to the caller.
        """
        try:
            data = json.loads(self._pool_path.read_text())
            return [Question.model_validate(q) for q in data]
        except FileNotFoundError:
            return []

    def save_questions(self, questions: list[Question]) -> None:
        """Overwrite the pool file with *questions*. Creates parent dirs as needed."""
        self._pool_path.parent.mkdir(parents=True, exist_ok=True)
        self._pool_path.write_text(
            json.dumps([q.model_dump(mode="json") for q in questions], indent=2)
        )

    def append_answer(self, entry: AnswerLogEntry) -> None:
        """Append *entry* as a JSON line to the answer log. Creates parent dirs as needed."""
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a") as f:
            f.write(entry.model_dump_json() + "\n")

    def load_answers(self) -> list[AnswerLogEntry]:
        """Return all log entries in file order. Returns ``[]`` if the file is absent.

        ``json.JSONDecodeError`` on any non-blank line is intentionally not caught
        so that data corruption is surfaced immediately.
        """
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
    doc_id      TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    authors     TEXT    NOT NULL,
    year        INTEGER NOT NULL,
    section     TEXT    NOT NULL,
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

    The database is created at ``db_path`` on first use; all tables are
    initialized with ``CREATE TABLE IF NOT EXISTS`` in ``__init__`` so the
    backend is safe to instantiate against a fresh path.

    Questions are stored across four normalized tables (``questions``,
    ``question_options``, ``question_references``, ``question_history``).
    Answers are a single append-only ``answers`` table.  ``save_questions``
    replaces the entire pool in one transaction to match the filesystem
    backend's all-or-nothing write semantics.
    """

    def __init__(self, db_path: Path) -> None:
        """Open (or create) the database at *db_path* and initialize the schema."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def load_questions(self) -> list[Question]:
        """Return all questions by joining across the four question tables."""
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

            references = [
                Reference(doc_id=doc_id, title=title, authors=authors, year=year, section=section)
                for (doc_id, title, authors, year, section) in cur.execute(
                    "SELECT doc_id, title, authors, year, section "
                    "FROM question_references WHERE question_id = ? ORDER BY position",
                    (qid,),
                ).fetchall()
            ]

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
                    type=QuestionType[row[2]],
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
        """Replace the entire question pool in one transaction.

        Deletes all rows from the four question tables before inserting *questions*,
        matching the filesystem backend's full-overwrite semantics.
        """
        with self._conn:
            self._conn.execute("DELETE FROM question_history")
            self._conn.execute("DELETE FROM question_options")
            self._conn.execute("DELETE FROM question_references")
            self._conn.execute("DELETE FROM questions")

            for q in questions:
                self._conn.execute(
                    "INSERT INTO questions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        q.id, q.topic, q.type.name, q.question, q.correct,
                        q.explanation, q.created_date, q.session_date, q.level, q.next_review,
                    ),
                )
                for i, text in enumerate(q.options):
                    self._conn.execute(
                        "INSERT INTO question_options VALUES (?,?,?)",
                        (q.id, i, text),
                    )
                for i, ref in enumerate(q.references):
                    self._conn.execute(
                        "INSERT INTO question_references VALUES (?,?,?,?,?,?,?)",
                        (q.id, i, ref.doc_id, ref.title, ref.authors, ref.year, ref.section),
                    )
                for i, h in enumerate(q.history):
                    self._conn.execute(
                        "INSERT INTO question_history VALUES (?,?,?,?)",
                        (q.id, i, h.date, int(h.correct)),
                    )

    def append_answer(self, entry: AnswerLogEntry) -> None:
        """Insert *entry* as a single row in the answers table."""
        with self._conn:
            self._conn.execute(
                "INSERT INTO answers (qid, topic, doc_id, level, correct, date) VALUES (?,?,?,?,?,?)",
                (entry.qid, entry.topic, entry.doc_id, entry.level, int(entry.correct), entry.date),
            )

    def load_answers(self) -> list[AnswerLogEntry]:
        """Return all answer log entries in insertion order."""
        rows = self._conn.execute(
            "SELECT qid, topic, doc_id, level, correct, date FROM answers ORDER BY rowid"
        ).fetchall()
        return [
            AnswerLogEntry(qid=qid, topic=topic, doc_id=doc_id, level=level, correct=bool(correct), date=date)
            for (qid, topic, doc_id, level, correct, date) in rows
        ]
