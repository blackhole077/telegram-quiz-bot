import sqlite3
from pathlib import Path

from backend.backends import register_backend
from core.schemas.answer_schemas import AnswerLogEntry
from core.schemas.question_schemas import (
    HistoryEntry,
    PaperRef,
    Question,
    QuestionType,
    TextbookRef,
)

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
            for (
                source_type,
                doc_id,
                title,
                authors,
                year,
                section,
                edition,
                chapter,
                venue,
                doi,
            ) in cur.execute(
                "SELECT source_type, doc_id, title, authors, year, section, "
                "edition, chapter, venue, doi "
                "FROM question_references WHERE question_id = ? ORDER BY position",
                (qid,),
            ).fetchall():
                if source_type == "textbook":
                    references.append(
                        TextbookRef(
                            doc_id=doc_id,
                            title=title,
                            authors=authors,
                            year=year,
                            section=section,
                            edition=edition,
                            chapter=chapter,
                        )
                    )
                else:
                    references.append(
                        PaperRef(
                            doc_id=doc_id,
                            title=title,
                            authors=authors,
                            year=year,
                            section=section,
                            venue=venue,
                            doi=doi,
                        )
                    )
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
