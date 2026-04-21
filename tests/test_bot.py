"""Tests for bot/bot.py — Telegram handlers with Telegram API mocked.

All storage I/O is provided by a ``MagicMock(spec=StorageBackend)`` patched
onto ``bot.bot._backend``.  Telegram is mocked via MagicMock / AsyncMock so
no network calls are made.  The module-level ``_settings`` singleton is patched
to control ``allowed_user_id``.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# conftest.py sets TELEGRAM_BOT_TOKEN and ALLOWED_USER_ID before this import.
import bot.bot as bot_module
from bot.bot import (
    AWAITING_ANSWER,
    _auth,
    _start_session,
    cmd_cancel,
    cmd_stats,
    generate_and_start_quiz,
    handle_answer,
)
from bot.config import Settings
from quiz.storage import StorageBackend
from telegram.ext import ConversationHandler
from tests.conftest import ALLOWED_USER_ID, make_log_entry, make_question, make_update, make_context


SETTINGS = Settings(
    telegram_bot_token="test-token",
    allowed_user_id=ALLOWED_USER_ID,
    data_dir="/tmp/quiz-test",
)


@pytest.fixture
def mock_backend():
    backend = MagicMock(spec=StorageBackend)
    backend.load_questions.return_value = []
    backend.load_answers.return_value = []
    return backend


@pytest.fixture(autouse=True)
def _patch_settings_and_backend(mock_backend):
    with (
        patch.object(bot_module, "_settings", SETTINGS),
        patch.object(bot_module, "_backend", mock_backend),
    ):
        yield


def _session_user_data(questions, display_questions=None):
    if display_questions is None:
        display_questions = questions
    return {
        "session": [q.id for q in questions],
        "cursor": 0,
        "score": 0,
        "qmap": {q.id: q for q in questions},
        "display_qmap": {q.id: q for q in display_questions},
    }


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

        wrapped = _auth(fake_handler)
        result = await wrapped(update, context)

        assert called == []
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

        wrapped = _auth(fake_handler)
        await wrapped(update, context)

        assert called == [True]


# ---------------------------------------------------------------------------
# _start_session
# ---------------------------------------------------------------------------


class TestStartSession:
    def test_populates_user_data_keys(self):
        q1 = make_question(id="q1")
        q2 = make_question(id="q2")
        context = make_context()
        _start_session(context, [q1, q2], [q1, q2])
        ud = context.user_data
        assert "session" in ud
        assert "cursor" in ud
        assert "score" in ud
        assert "qmap" in ud
        assert "display_qmap" in ud

    def test_cursor_starts_at_zero(self):
        q = make_question()
        context = make_context()
        _start_session(context, [q], [q])
        assert context.user_data["cursor"] == 0

    def test_score_starts_at_zero(self):
        q = make_question()
        context = make_context()
        _start_session(context, [q], [q])
        assert context.user_data["score"] == 0

    def test_session_length_matches_due_count(self):
        qs = [make_question(id=f"q{i}") for i in range(4)]
        context = make_context()
        _start_session(context, qs, qs)
        assert len(context.user_data["session"]) == 4

    def test_qmap_contains_all_pool_questions(self):
        pool = [make_question(id=f"p{i}") for i in range(5)]
        due = pool[:2]
        context = make_context()
        _start_session(context, pool, due)
        assert set(context.user_data["qmap"].keys()) == {q.id for q in pool}

    def test_display_qmap_contains_due_questions(self):
        q = make_question(id="q1")
        context = make_context()
        _start_session(context, [q], [q])
        assert "q1" in context.user_data["display_qmap"]

    def test_returns_display_copies(self):
        q = make_question(id="q1")
        context = make_context()
        result = _start_session(context, [q], [q])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# generate_and_start_quiz
# ---------------------------------------------------------------------------


class TestGenerateAndStartQuiz:
    @pytest.mark.asyncio
    async def test_no_due_questions_sends_message_and_ends(self, mock_backend):
        update = make_update()
        context = make_context()
        with patch("bot.bot.select_session", return_value=[]):
            result = await generate_and_start_quiz(update, context)
        assert result == ConversationHandler.END
        update.message.reply_text.assert_called_once()
        assert "No questions" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_due_questions_starts_session(self, mock_backend):
        q = make_question(id="q1")
        mock_backend.load_questions.return_value = [q]
        update = make_update()
        context = make_context()
        with patch("bot.bot.select_session", return_value=[q]):
            result = await generate_and_start_quiz(update, context)
        assert result == AWAITING_ANSWER

    @pytest.mark.asyncio
    async def test_first_question_sent(self, mock_backend):
        q = make_question(id="q1")
        mock_backend.load_questions.return_value = [q]
        update = make_update()
        context = make_context()
        with patch("bot.bot.select_session", return_value=[q]):
            await generate_and_start_quiz(update, context)
        assert update.message.reply_text.call_count == 1
        assert "[1/1]" in update.message.reply_text.call_args[0][0]

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
    def _setup(self, q=None, cursor=0):
        if q is None:
            q = make_question(id="q1", correct="A")
        ud = _session_user_data([q])
        ud["cursor"] = cursor
        return q, make_context(ud)

    @pytest.mark.asyncio
    async def test_invalid_answer_reprompts_and_stays_in_state(self):
        q, context = self._setup()
        update = make_update(text="Z")
        result = await handle_answer(update, context)
        assert result == AWAITING_ANSWER
        assert context.user_data["cursor"] == 0

    @pytest.mark.asyncio
    async def test_invalid_answer_does_not_write_log(self, mock_backend):
        q, context = self._setup()
        update = make_update(text="Z")
        await handle_answer(update, context)
        mock_backend.append_answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_correct_answer_increments_score(self):
        q, context = self._setup()
        update = make_update(text="A")
        await handle_answer(update, context)
        assert context.user_data["score"] == 1

    @pytest.mark.asyncio
    async def test_wrong_answer_does_not_increment_score(self):
        q, context = self._setup()
        update = make_update(text="B")
        await handle_answer(update, context)
        assert context.user_data["score"] == 0

    @pytest.mark.asyncio
    async def test_correct_answer_advances_cursor(self):
        q1 = make_question(id="q1", correct="A")
        q2 = make_question(id="q2", correct="A")
        context = make_context(_session_user_data([q1, q2]))
        update = make_update(text="A")
        await handle_answer(update, context)
        assert context.user_data["cursor"] == 1

    @pytest.mark.asyncio
    async def test_mid_session_returns_awaiting_answer(self):
        q1 = make_question(id="q1", correct="A")
        q2 = make_question(id="q2", correct="A")
        context = make_context(_session_user_data([q1, q2]))
        update = make_update(text="A")
        result = await handle_answer(update, context)
        assert result == AWAITING_ANSWER

    @pytest.mark.asyncio
    async def test_last_question_saves_pool_and_ends(self, mock_backend):
        q, context = self._setup()
        update = make_update(text="A")
        result = await handle_answer(update, context)
        assert result == ConversationHandler.END
        mock_backend.save_questions.assert_called_once()

    @pytest.mark.asyncio
    async def test_last_question_sends_summary(self):
        q, context = self._setup()
        update = make_update(text="A")
        await handle_answer(update, context)
        assert update.message.reply_text.call_count == 2
        summary_text = update.message.reply_text.call_args_list[-1][0][0]
        assert "Session complete" in summary_text
        assert "1/1" in summary_text

    @pytest.mark.asyncio
    async def test_answer_logged_with_correct_fields(self, mock_backend):
        q = make_question(id="q1", topic="DQN", correct="A")
        context = make_context(_session_user_data([q]))
        update = make_update(text="A")
        logged = []
        mock_backend.append_answer.side_effect = lambda e: logged.append(e)
        await handle_answer(update, context)
        assert len(logged) == 1
        entry = logged[0]
        assert entry.qid == "q1"
        assert entry.topic == "DQN"
        assert entry.correct is True

    @pytest.mark.asyncio
    async def test_srs_updated_in_qmap_on_correct(self):
        q = make_question(id="q1", level=1, correct="A")
        context = make_context(_session_user_data([q]))
        update = make_update(text="A")
        await handle_answer(update, context)
        assert context.user_data["qmap"]["q1"].level == 2

    @pytest.mark.asyncio
    async def test_srs_demoted_in_qmap_on_wrong(self):
        q = make_question(id="q1", level=3, correct="A")
        context = make_context(_session_user_data([q]))
        update = make_update(text="B")
        await handle_answer(update, context)
        assert context.user_data["qmap"]["q1"].level == 1

    @pytest.mark.asyncio
    async def test_mid_session_sends_next_question(self):
        q1 = make_question(id="q1", correct="A")
        q2 = make_question(id="q2", correct="B")
        context = make_context(_session_user_data([q1, q2]))
        update = make_update(text="A")
        await handle_answer(update, context)
        assert update.message.reply_text.call_count == 2
        assert "[2/2]" in update.message.reply_text.call_args_list[-1][0][0]


# ---------------------------------------------------------------------------
# cmd_stats
# ---------------------------------------------------------------------------


class TestCmdStats:
    @pytest.mark.asyncio
    async def test_empty_pool_and_log(self):
        update = make_update()
        context = make_context()
        await cmd_stats(update, context)
        text = update.message.reply_text.call_args[0][0]
        assert "Total questions: 0" in text
        assert "Due today: 0" in text
        assert "streak: 0" in text

    @pytest.mark.asyncio
    async def test_streak_single_day(self, mock_backend):
        from datetime import date
        entry = make_log_entry(date=date.today().isoformat())
        mock_backend.load_answers.return_value = [entry]
        update = make_update()
        context = make_context()
        await cmd_stats(update, context)
        assert "streak: 1 day" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_streak_consecutive_days(self, mock_backend):
        from datetime import date, timedelta
        today = date.today()
        entries = [
            make_log_entry(date=(today - timedelta(days=i)).isoformat())
            for i in range(3)
        ]
        mock_backend.load_answers.return_value = entries
        update = make_update()
        context = make_context()
        await cmd_stats(update, context)
        assert "streak: 3 days" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_streak_broken_by_gap(self, mock_backend):
        from datetime import date, timedelta
        today = date.today()
        entries = [
            make_log_entry(date=today.isoformat()),
            # gap: yesterday absent
            make_log_entry(date=(today - timedelta(days=2)).isoformat()),
        ]
        mock_backend.load_answers.return_value = entries
        update = make_update()
        context = make_context()
        await cmd_stats(update, context)
        assert "streak: 1 day" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_due_count_correct(self, mock_backend):
        due_q = make_question(id="q1", next_review="2026-01-01")
        future_q = make_question(id="q2", next_review="2099-01-01")
        mock_backend.load_questions.return_value = [due_q, future_q]
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
    @pytest.mark.asyncio
    async def test_no_session_still_sends_message(self, mock_backend):
        update = make_update()
        context = make_context()
        result = await cmd_cancel(update, context)
        assert result == ConversationHandler.END
        update.message.reply_text.assert_called_once_with("Session cancelled.")
        mock_backend.save_questions.assert_not_called()

    @pytest.mark.asyncio
    async def test_active_session_saves_pool(self, mock_backend):
        q = make_question(id="q1")
        context = make_context(_session_user_data([q]))
        update = make_update()
        result = await cmd_cancel(update, context)
        assert result == ConversationHandler.END
        mock_backend.save_questions.assert_called_once()
