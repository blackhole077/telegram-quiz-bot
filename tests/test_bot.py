"""Tests for bot/bot.py — Telegram handlers with service layer mocked.

All business logic is provided by a ``MagicMock(spec=QuizService)`` patched
onto ``bot.bot._service``.  Telegram is mocked via MagicMock / AsyncMock so
no network calls are made.  The module-level ``settings`` singleton is patched
to control ``allowed_user_id``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ConversationHandler

# conftest.py sets TELEGRAM_BOT_TOKEN and ALLOWED_USER_ID before this import.
import frontend.telegram_bot.bot as bot_module
from core.schemas.answer_schemas import AnswerOutcome
from core.schemas.llm_schemas import (
    ExamGradeResult,
    ExamProblem,
    GradeResult,
    ProblemGrade,
)
from core.schemas.question_schemas import Problem
from core.schemas.schemas import QuizSession
from core.service import QuizService
from frontend.telegram_bot.bot import (
    AWAITING_ANSWER,
    AWAITING_EXAM_ANSWER,
    AWAITING_PRACTICE_ANSWER,
    _auth,
    cmd_cancel,
    cmd_exam,
    cmd_practice,
    cmd_stats,
    generate_and_start_quiz,
    handle_answer,
    handle_exam_submission,
    handle_practice_answer,
)
from tests.conftest import (
    ALLOWED_USER_ID,
    make_context,
    make_question,
    make_session,
    make_update,
)


def make_problem(
    id: str = "p1",
    topic: str = "RL",
    difficulty: int = 2,
    uses_latex: bool = False,
) -> Problem:
    return Problem(
        id=id,
        topic=topic,
        prompt="What is Q-learning?",
        solution_steps="It is a model-free algorithm...",
        difficulty=difficulty,
        uses_latex=uses_latex,
    )


# ---------------------------------------------------------------------------
# _auth decorator
# ---------------------------------------------------------------------------


class TestAuth:
    @pytest.mark.asyncio
    async def test_authorised_user_passes_through(self):
        update = make_update(user_id=ALLOWED_USER_ID)
        context = make_context()
        called = []

        async def fake_handler(u, c):
            called.append(True)
            return "ok"

        with patch.object(bot_module, "bot_settings") as mock_settings:
            mock_settings.allowed_user_id = ALLOWED_USER_ID
            wrapped = _auth(fake_handler)
            result = await wrapped(update, context)

        assert called == [True]
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_unauthorised_user_returns_end_silently(self):
        update = make_update(user_id=99998)
        context = make_context()
        called = []

        async def fake_handler(u, c):
            called.append(True)

        with patch.object(bot_module, "bot_settings") as mock_settings:
            mock_settings.allowed_user_id = ALLOWED_USER_ID
            wrapped = _auth(fake_handler)
            result = await wrapped(update, context)

        assert not called
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_no_effective_user_passes_through(self):
        update = MagicMock()
        update.effective_user = None
        update.message.reply_text = AsyncMock()
        context = make_context()
        called = []

        async def fake_handler(u, c):
            called.append(True)

        with patch.object(bot_module, "bot_settings") as mock_settings:
            mock_settings.allowed_user_id = ALLOWED_USER_ID
            wrapped = _auth(fake_handler)
            await wrapped(update, context)

        assert called == [True]

    @pytest.mark.asyncio
    async def test_handler_exception_sends_error_to_user(self):
        update = make_update(user_id=ALLOWED_USER_ID)
        context = make_context()

        async def raising_handler(u, c):
            raise ValueError("boom")

        with patch.object(bot_module, "bot_settings") as mock_settings:
            mock_settings.allowed_user_id = ALLOWED_USER_ID
            wrapped = _auth(raising_handler)
            result = await wrapped(update, context)

        assert result == ConversationHandler.END
        update.message.reply_text.assert_called_once()
        assert "error" in update.message.reply_text.call_args[0][0].lower()


# ---------------------------------------------------------------------------
# generate_and_start_quiz
# ---------------------------------------------------------------------------


class TestGenerateAndStartQuiz:
    @pytest.fixture(autouse=True)
    def _patch_service_and_settings(self):
        self.mock_service = MagicMock(spec=QuizService)
        with (
            patch.object(bot_module, "_service", self.mock_service),
            patch.object(bot_module, "bot_settings") as mock_settings,
        ):
            mock_settings.allowed_user_id = ALLOWED_USER_ID
            yield

    @pytest.mark.asyncio
    async def test_no_due_questions_sends_message_and_ends(self):
        self.mock_service.prepare_session.return_value = []
        update = make_update()
        context = make_context()
        result = await generate_and_start_quiz(update, context)
        assert result == ConversationHandler.END
        update.message.reply_text.assert_called_once()
        assert "No questions" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_due_questions_starts_session(self):
        q = make_question(id="q1")
        self.mock_service.prepare_session.return_value = [q]
        self.mock_service.start_session.return_value = make_session([q])
        update = make_update()
        context = make_context()
        result = await generate_and_start_quiz(update, context)
        assert result == AWAITING_ANSWER

    @pytest.mark.asyncio
    async def test_first_question_sent(self):
        q = make_question(id="q1")
        self.mock_service.prepare_session.return_value = [q]
        self.mock_service.start_session.return_value = make_session([q])
        update = make_update()
        context = make_context()
        await generate_and_start_quiz(update, context)
        assert update.message.reply_text.call_count == 1
        assert "[1/1]" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_session_stored_in_user_data(self):
        q = make_question(id="q1")
        session = make_session([q])
        self.mock_service.prepare_session.return_value = [q]
        self.mock_service.start_session.return_value = session
        update = make_update()
        context = make_context()
        await generate_and_start_quiz(update, context)
        assert context.user_data["session"] is session

    @pytest.mark.asyncio
    async def test_unauthorized_user_blocked(self):
        update = make_update(user_id=12345)
        context = make_context()
        result = await generate_and_start_quiz(update, context)
        assert result == ConversationHandler.END
        update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# handle_answer
# ---------------------------------------------------------------------------


class TestHandleAnswer:
    @pytest.fixture(autouse=True)
    def _patch_service_and_settings(self):
        self.mock_service = MagicMock(spec=QuizService)
        with (
            patch.object(bot_module, "_service", self.mock_service),
            patch.object(bot_module, "bot_settings") as mock_settings,
        ):
            mock_settings.allowed_user_id = ALLOWED_USER_ID
            yield

    def _setup(self, q=None, cursor=0):
        if q is None:
            q = make_question(id="q1", correct="A")
        session = make_session([q], cursor=cursor)
        return q, make_context({"session": session})

    @pytest.mark.asyncio
    async def test_invalid_answer_reprompts_and_stays_in_state(self):
        _q, context = self._setup()
        self.mock_service.process_answer.return_value = None
        update = make_update(text="Z")
        result = await handle_answer(update, context)
        assert result == AWAITING_ANSWER

    @pytest.mark.asyncio
    async def test_invalid_answer_does_not_call_end_session(self):
        _q, context = self._setup()
        self.mock_service.process_answer.return_value = None
        update = make_update(text="Z")
        await handle_answer(update, context)
        self.mock_service.end_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_correct_answer_increments_score_via_service(self):
        q, context = self._setup()
        session: QuizSession = context.user_data["session"]

        # Simulate service mutating the session (as the real service does)
        def advance_cursor(s, text, today):
            s.score += 1
            s.cursor += 1
            return AnswerOutcome(correct=True, graded_question=q)

        self.mock_service.process_answer.side_effect = advance_cursor
        update = make_update(text="A")
        await handle_answer(update, context)
        assert session.score == 1

    @pytest.mark.asyncio
    async def test_correct_outcome_shows_feedback(self):
        q, context = self._setup()

        def advance_cursor(s, text, today):
            s.cursor = s.total  # mark complete
            return AnswerOutcome(correct=True, graded_question=q)

        self.mock_service.process_answer.side_effect = advance_cursor
        update = make_update(text="A")
        await handle_answer(update, context)
        # First reply_text call is the feedback
        first_call = update.message.reply_text.call_args_list[0][0][0]
        assert "Correct" in first_call

    @pytest.mark.asyncio
    async def test_mid_session_returns_awaiting_answer(self):
        q1 = make_question(id="q1", correct="A")
        q2 = make_question(id="q2", correct="A")
        session = make_session([q1, q2])
        context = make_context({"session": session})

        def advance_cursor(s, text, today):
            s.cursor += 1
            return AnswerOutcome(correct=True, graded_question=q1)

        self.mock_service.process_answer.side_effect = advance_cursor
        update = make_update(text="A")
        result = await handle_answer(update, context)
        assert result == AWAITING_ANSWER

    @pytest.mark.asyncio
    async def test_last_question_calls_end_session_and_ends(self):
        q, context = self._setup()

        def complete_session(s, text, today):
            s.cursor = s.total
            return AnswerOutcome(correct=True, graded_question=q)

        self.mock_service.process_answer.side_effect = complete_session
        update = make_update(text="A")
        result = await handle_answer(update, context)
        assert result == ConversationHandler.END
        self.mock_service.end_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_last_question_sends_summary(self):
        q, context = self._setup()
        _session: QuizSession = context.user_data["session"]

        def complete_session(s, text, today):
            s.score += 1
            s.cursor = s.total
            return AnswerOutcome(correct=True, graded_question=q)

        self.mock_service.process_answer.side_effect = complete_session
        update = make_update(text="A")
        await handle_answer(update, context)
        summary_text = update.message.reply_text.call_args_list[-1][0][0]
        assert "Session complete" in summary_text
        assert "1/1" in summary_text

    @pytest.mark.asyncio
    async def test_mid_session_sends_next_question(self):
        q1 = make_question(id="q1", correct="A")
        q2 = make_question(id="q2", correct="B")
        session = make_session([q1, q2])
        context = make_context({"session": session})

        def advance_cursor(s, text, today):
            s.cursor += 1
            return AnswerOutcome(correct=True, graded_question=q1)

        self.mock_service.process_answer.side_effect = advance_cursor
        update = make_update(text="A")
        await handle_answer(update, context)
        assert update.message.reply_text.call_count == 2
        assert "[2/2]" in update.message.reply_text.call_args_list[-1][0][0]


# ---------------------------------------------------------------------------
# cmd_stats
# ---------------------------------------------------------------------------


class TestCmdStats:
    @pytest.fixture(autouse=True)
    def _patch_service_and_settings(self):
        self.mock_service = MagicMock(spec=QuizService)
        with (
            patch.object(bot_module, "_service", self.mock_service),
            patch.object(bot_module, "bot_settings") as mock_settings,
        ):
            mock_settings.allowed_user_id = ALLOWED_USER_ID
            yield

    @pytest.mark.asyncio
    async def test_empty_pool(self):
        self.mock_service.get_stats.return_value = (0, 0)
        update = make_update()
        context = make_context()
        await cmd_stats(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Total questions: 0" in text
        assert "Due today: 0" in text

    @pytest.mark.asyncio
    async def test_due_count_correct(self):
        self.mock_service.get_stats.return_value = (2, 1)
        update = make_update()
        context = make_context()
        await cmd_stats(update, context)
        assert "Due today: 1" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_unauthorized_user_blocked(self):
        update = make_update(user_id=11111)
        context = make_context()
        await cmd_stats(update, context)
        update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_cancel
# ---------------------------------------------------------------------------


class TestCmdCancel:
    @pytest.fixture(autouse=True)
    def _patch_service_and_settings(self):
        self.mock_service = MagicMock(spec=QuizService)
        with (
            patch.object(bot_module, "_service", self.mock_service),
            patch.object(bot_module, "bot_settings") as mock_settings,
        ):
            mock_settings.allowed_user_id = ALLOWED_USER_ID
            yield

    @pytest.mark.asyncio
    async def test_no_session_still_sends_message(self):
        update = make_update()
        context = make_context()
        result = await cmd_cancel(update, context)
        assert result == ConversationHandler.END
        update.message.reply_text.assert_called_once_with("Session cancelled.")
        self.mock_service.end_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_active_session_calls_end_session(self):
        q = make_question(id="q1")
        session = make_session([q])
        context = make_context({"session": session})
        update = make_update()
        result = await cmd_cancel(update, context)
        assert result == ConversationHandler.END
        self.mock_service.end_session.assert_called_once_with(session)


# ---------------------------------------------------------------------------
# cmd_practice
# ---------------------------------------------------------------------------


class TestCmdPractice:
    @pytest.fixture(autouse=True)
    def _patch(self):
        self.mock_service = MagicMock(spec=QuizService)
        with (
            patch.object(bot_module, "_service", self.mock_service),
            patch.object(bot_module, "bot_settings") as mock_settings,
        ):
            mock_settings.allowed_user_id = ALLOWED_USER_ID
            yield

    @pytest.mark.asyncio
    async def test_no_problems_file_sends_message_and_ends(self):
        with patch.object(bot_module, "_PROBLEMS", []):
            update = make_update()
            context = make_context()
            result = await cmd_practice(update, context)
        assert result == ConversationHandler.END
        update.message.reply_text.assert_called_once()
        assert "No problems" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_empty_pool_sends_message_and_ends(self):
        with patch.object(bot_module, "_PROBLEMS", []):
            update = make_update()
            context = make_context()
            result = await cmd_practice(update, context)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_problem_stored_in_user_data(self):
        problem = make_problem()
        with (
            patch.object(bot_module, "_PROBLEMS", [problem]),
            patch("frontend.telegram_bot.bot.pick_random", return_value=[problem]),
        ):
            update = make_update()
            context = make_context()
            await cmd_practice(update, context)
        assert context.user_data["practice_problem"] is problem

    @pytest.mark.asyncio
    async def test_returns_awaiting_practice_answer(self):
        problem = make_problem()
        with (
            patch.object(bot_module, "_PROBLEMS", [problem]),
            patch("frontend.telegram_bot.bot.pick_random", return_value=[problem]),
        ):
            update = make_update()
            context = make_context()
            result = await cmd_practice(update, context)
        assert result == AWAITING_PRACTICE_ANSWER

    @pytest.mark.asyncio
    async def test_topic_filter_applied(self):
        problem = make_problem(topic="RL")
        with (
            patch.object(bot_module, "_PROBLEMS", [problem]),
            patch(
                "frontend.telegram_bot.bot.filter_by_topic", return_value=[problem]
            ) as mock_filter,
            patch("frontend.telegram_bot.bot.pick_random", return_value=[problem]),
        ):
            update = make_update()
            context = make_context()
            context.args = ["RL"]
            await cmd_practice(update, context)
        mock_filter.assert_called_once()
        assert mock_filter.call_args[0][1] == "RL"

    @pytest.mark.asyncio
    async def test_unauthorized_user_blocked(self):
        update = make_update(user_id=11111)
        context = make_context()
        result = await cmd_practice(update, context)
        assert result == ConversationHandler.END
        update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# handle_practice_answer
# ---------------------------------------------------------------------------


class TestHandlePracticeAnswer:
    @pytest.fixture(autouse=True)
    def _patch(self):
        self.mock_service = MagicMock(spec=QuizService)
        with (
            patch.object(bot_module, "_service", self.mock_service),
            patch.object(bot_module, "bot_settings") as mock_settings,
        ):
            mock_settings.allowed_user_id = ALLOWED_USER_ID
            yield

    def _grade_result(self, correct=True, score=1.0):
        return GradeResult(
            correct=correct,
            score=score,
            feedback="Good work." if correct else "Not quite.",
            model_solution="The answer is 42.",
            error="",
        )

    @pytest.mark.asyncio
    async def test_calls_grade_answer(self):
        problem = make_problem()
        context = make_context({"practice_problem": problem})
        with patch(
            "frontend.telegram_bot.bot.grade_answer", return_value=self._grade_result()
        ) as mock_grade:
            update = make_update(text="my answer")
            await handle_practice_answer(update, context)
        mock_grade.assert_called_once_with(
            problem.prompt, problem.solution_steps, "my answer"
        )

    @pytest.mark.asyncio
    async def test_returns_end(self):
        problem = make_problem()
        context = make_context({"practice_problem": problem})
        with patch(
            "frontend.telegram_bot.bot.grade_answer", return_value=self._grade_result()
        ):
            update = make_update(text="answer")
            result = await handle_practice_answer(update, context)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_correct_result_shown(self):
        problem = make_problem()
        context = make_context({"practice_problem": problem})
        with patch(
            "frontend.telegram_bot.bot.grade_answer",
            return_value=self._grade_result(correct=True),
        ):
            update = make_update(text="answer")
            await handle_practice_answer(update, context)
        full_text = " ".join(c[0][0] for c in update.message.reply_text.call_args_list)
        assert "Correct" in full_text

    @pytest.mark.asyncio
    async def test_wrong_result_includes_model_solution(self):
        problem = make_problem()
        context = make_context({"practice_problem": problem})
        with patch(
            "frontend.telegram_bot.bot.grade_answer",
            return_value=self._grade_result(correct=False, score=0.0),
        ):
            update = make_update(text="wrong")
            await handle_practice_answer(update, context)
        full_text = " ".join(c[0][0] for c in update.message.reply_text.call_args_list)
        assert "Model solution" in full_text

    @pytest.mark.asyncio
    async def test_no_problem_in_context_ends_silently(self):
        context = make_context({})
        update = make_update(text="answer")
        result = await handle_practice_answer(update, context)
        assert result == ConversationHandler.END
        update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_exam
# ---------------------------------------------------------------------------


class TestCmdExam:
    @pytest.fixture(autouse=True)
    def _patch(self):
        self.mock_service = MagicMock(spec=QuizService)
        mock_report = MagicMock()
        mock_report.flagged_topics = []
        mock_report.difficult_questions = []
        self.mock_service.get_gap_report.return_value = mock_report
        with (
            patch.object(bot_module, "_service", self.mock_service),
            patch.object(bot_module, "bot_settings") as mock_settings,
        ):
            mock_settings.allowed_user_id = ALLOWED_USER_ID
            yield

    def _problems(self):
        return [ExamProblem(number=1, prompt="Prove X.", solution="Because Y.")]

    @pytest.mark.asyncio
    async def test_no_args_sends_usage_hint(self):
        update = make_update()
        context = make_context()
        context.args = []
        result = await cmd_exam(update, context)
        assert result == ConversationHandler.END
        assert "Usage" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_exam_generation_failure_sends_message(self):
        update = make_update()
        context = make_context()
        context.args = ["RL"]
        with patch("frontend.telegram_bot.bot.generate_exam", return_value=[]):
            result = await cmd_exam(update, context)
        assert result == ConversationHandler.END
        assert any(
            "failed" in c[0][0].lower()
            for c in update.message.reply_text.call_args_list
        )

    @pytest.mark.asyncio
    async def test_pdf_sent_as_document(self):
        update = make_update()
        update.message.reply_document = AsyncMock()
        context = make_context()
        context.args = ["Linear Algebra"]
        with (
            patch(
                "frontend.telegram_bot.bot.generate_exam", return_value=self._problems()
            ),
            patch(
                "frontend.telegram_bot.bot.render_exam_pdf", return_value=b"%PDF-fake"
            ),
        ):
            result = await cmd_exam(update, context)
        assert result == AWAITING_EXAM_ANSWER
        update.message.reply_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_exam_problems_stored_in_user_data(self):
        update = make_update()
        update.message.reply_document = AsyncMock()
        context = make_context()
        context.args = ["RL"]
        problems = self._problems()
        with (
            patch("frontend.telegram_bot.bot.generate_exam", return_value=problems),
            patch(
                "frontend.telegram_bot.bot.render_exam_pdf", return_value=b"%PDF-fake"
            ),
        ):
            await cmd_exam(update, context)
        assert context.user_data["exam_problems"] == problems

    @pytest.mark.asyncio
    async def test_weak_topics_passed_to_generate_exam(self):
        mock_report = MagicMock()
        mock_report.flagged_topics = ["Q-learning"]
        mock_report.difficult_questions = []
        self.mock_service.get_gap_report.return_value = mock_report
        update = make_update()
        update.message.reply_document = AsyncMock()
        context = make_context()
        context.args = ["RL"]
        with (
            patch(
                "frontend.telegram_bot.bot.generate_exam", return_value=self._problems()
            ) as mock_gen,
            patch(
                "frontend.telegram_bot.bot.render_exam_pdf", return_value=b"%PDF-fake"
            ),
        ):
            await cmd_exam(update, context)
        assert mock_gen.call_args.kwargs["weak_topics"] == ["Q-learning"]


# ---------------------------------------------------------------------------
# handle_exam_submission
# ---------------------------------------------------------------------------


class TestHandleExamSubmission:
    @pytest.fixture(autouse=True)
    def _patch(self):
        self.mock_service = MagicMock(spec=QuizService)
        with (
            patch.object(bot_module, "_service", self.mock_service),
            patch.object(bot_module, "bot_settings") as mock_settings,
        ):
            mock_settings.allowed_user_id = ALLOWED_USER_ID
            yield

    def _problems(self):
        return [ExamProblem(number=1, prompt="Prove X.", solution="Because Y.")]

    def _grade_result(self, score=0.8):
        return ExamGradeResult(
            problems=[ProblemGrade(number=1, score=score, feedback="Good.")],
            total_score=score,
            summary="Well done.",
        )

    @pytest.mark.asyncio
    async def test_text_submission_calls_grade_from_text(self):
        context = make_context({"exam_problems": self._problems()})
        with patch(
            "frontend.telegram_bot.bot.grade_from_text",
            return_value=self._grade_result(),
        ) as mock_grade:
            update = make_update(text="My answers here.")
            update.message.photo = []
            await handle_exam_submission(update, context)
        mock_grade.assert_called_once()

    @pytest.mark.asyncio
    async def test_photo_submission_calls_grade_from_image(self):
        context = make_context({"exam_problems": self._problems()})
        mock_file = MagicMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"imgdata"))
        mock_photo = MagicMock()
        mock_photo.get_file = AsyncMock(return_value=mock_file)

        update = make_update()
        update.message.photo = [mock_photo]
        update.message.text = None

        with patch(
            "frontend.telegram_bot.bot.grade_from_image",
            return_value=self._grade_result(),
        ) as mock_grade:
            await handle_exam_submission(update, context)
        mock_grade.assert_called_once()
        assert mock_grade.call_args[0][1] == b"imgdata"

    @pytest.mark.asyncio
    async def test_score_shown_in_reply(self):
        context = make_context({"exam_problems": self._problems()})
        with patch(
            "frontend.telegram_bot.bot.grade_from_text",
            return_value=self._grade_result(score=0.75),
        ):
            update = make_update(text="answers")
            update.message.photo = []
            await handle_exam_submission(update, context)
        full_text = " ".join(c[0][0] for c in update.message.reply_text.call_args_list)
        assert "75%" in full_text

    @pytest.mark.asyncio
    async def test_returns_end(self):
        context = make_context({"exam_problems": self._problems()})
        with patch(
            "frontend.telegram_bot.bot.grade_from_text",
            return_value=self._grade_result(),
        ):
            update = make_update(text="answers")
            update.message.photo = []
            result = await handle_exam_submission(update, context)
        assert result == ConversationHandler.END

    @pytest.mark.asyncio
    async def test_no_problems_in_context_ends_silently(self):
        context = make_context({})
        update = make_update(text="answers")
        update.message.photo = []
        result = await handle_exam_submission(update, context)
        assert result == ConversationHandler.END
        update.message.reply_text.assert_not_called()
