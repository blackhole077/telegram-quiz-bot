"""QuizService: the business logic facade used by all frontends."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from core import srs
from core.question import normalise_answer, shuffle_answers
from core.refinement import RefinementReport, analyze_gaps
from core.schemas.answer_schemas import AnswerLogEntry, AnswerOutcome
from core.schemas.question_schemas import DifficultQuestion, Question
from core.schemas.schemas import QuizSession
from core.selector import select_session
from core.storage import StorageBackend


class QuizService:
    """Coordinates SRS scheduling, session management, and answer logging.

    All frontends (Telegram bot, CLI, etc.) should go through this service
    rather than calling srs, selector, or storage directly.
    """

    def __init__(self, backend: StorageBackend) -> None:
        self._backend = backend

    def prepare_session(self, today: str) -> list[Question]:
        """Load the question pool and return those due today."""
        all_questions = self._backend.load_questions()
        return select_session(all_questions, today=today)

    def start_session(self, due: list[Question]) -> QuizSession:
        """Build a shuffled session from the due questions."""
        display = [shuffle_answers(question) for question in due]
        return QuizSession(
            session_ids=[question.id for question in due],
            cursor=0,
            score=0,
            original_map={question.id: question for question in due},
            display_map={question.id: question for question in display},
        )

    def process_answer(
        self, session: QuizSession, user_text: str, today: str
    ) -> AnswerOutcome | None:
        """Validate and grade one answer, advancing session state on success.

        Returns ``None`` if ``user_text`` is not a valid answer label for the
        current question (caller should re-prompt without mutating any state).

        On a valid answer: updates the question's SRS level, logs the answer,
        advances ``session.cursor``, and increments ``session.score`` if correct.
        """
        question = session.current_display
        answer = normalise_answer(user_text, question)
        if answer is None:
            return None

        original = session.current_original
        correct = answer == question.correct.upper()
        updated = (
            srs.advance(original, today) if correct else srs.demote(original, today)
        )

        session.original_map[updated.id] = updated
        if correct:
            session.score += 1
        session.cursor += 1

        self._backend.append_answer(
            AnswerLogEntry(
                qid=original.id,
                topic=question.topic,
                doc_id=question.references[0].doc_id if question.references else "",
                level=updated.level,
                correct=correct,
                date=today,
            )
        )

        return AnswerOutcome(correct=correct, graded_question=question)

    def end_session(self, session: QuizSession) -> None:
        """Merge updated question states back into the full pool and save."""
        all_questions = self._backend.load_questions()
        updated_map = {q.id: q for q in all_questions}
        updated_map.update(session.original_map)
        self._backend.save_questions(list(updated_map.values()))

    def get_stats(self, today: str) -> tuple[int, int]:
        """Return (total_questions, due_today_count)."""
        questions = self._backend.load_questions()
        due_count = sum(1 for q in questions if q.next_review <= today)
        return len(questions), due_count

    def get_gap_report(self) -> RefinementReport:
        """Run gap analysis over the full question pool and answer log."""
        questions = self._backend.load_questions()
        answers = self._backend.load_answers()
        return analyze_gaps(answers, questions)

    def get_weak_topics(self) -> list[str]:
        """Return topics with >50% error rate and at least 3 attempts."""
        return self.get_gap_report().flagged_topics

    def get_difficult_questions(self) -> list[DifficultQuestion]:
        """Return questions with <50% correct rate and at least 3 attempts."""
        return self.get_gap_report().difficult_questions
