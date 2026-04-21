"""Telegram bot: delivers spaced-repetition quiz sessions."""

from __future__ import annotations

import functools
import logging
import sys
from collections.abc import Callable, Coroutine
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# Makes ``import quiz`` work when run directly without package install.
sys.path.insert(0, str(Path(__file__).parent.parent))

from quiz import srs
from quiz.question import (
    fmt_feedback,
    fmt_question,
    input_hint,
    normalise_answer,
    shuffle,
)
from quiz.schemas import AnswerLogEntry, Question
from quiz.selector import select_session
from quiz.storage import StorageBackend, make_backend

from bot.config import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AWAITING_ANSWER = 1

_settings = Settings()
_backend: StorageBackend = make_backend(_settings)

_Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, Any]]


def _auth(func: _Handler) -> _Handler:
    """Decorator that silently drops updates from unauthorised users.

    Drops silently rather than replying, to avoid confirming the bot's
    existence to unknown callers. Updates with no ``effective_user``
    (e.g. channel posts) are passed through.

    Note:
        Returns ``ConversationHandler.END`` for unauthorised users. When
        the wrapped handler is not part of a ConversationHandler (e.g.
        ``cmd_stats``), that return value is discarded by the framework,
        so the apparent ``-> None`` type mismatch is harmless.
    """

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        if (
            update.effective_user
            and update.effective_user.id != _settings.allowed_user_id
        ):
            logger.warning(
                "Ignoring message from unknown user %s", update.effective_user.id
            )
            return ConversationHandler.END
        return await func(update, context)

    return wrapper  # type: ignore[return-value]


def _start_session(
    context: ContextTypes.DEFAULT_TYPE,
    all_questions: list[Question],
    due: list[Question],
) -> list[Question]:
    """Shuffle due questions and store all session state in context.user_data.

    Args:
        context: The handler context whose user_data will be populated.
        all_questions: The full question pool. Stored so handle_answer can
            write back the complete pool after each SRS update.
        due: Questions selected for this session.

    Returns:
        Shuffled display copies of due, in the same order.
    """
    assert context.user_data is not None
    display = [shuffle(q) for q in due]
    context.user_data["session"] = [q.id for q in due]
    context.user_data["cursor"] = 0
    context.user_data["score"] = 0
    context.user_data["qmap"] = {q.id: q for q in all_questions}
    context.user_data["display_qmap"] = {q.id: q for q in display}
    return display


@_auth
async def generate_and_start_quiz(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Handle the /quiz command: select due questions and start a new session.

    Args:
        update: The incoming Telegram update.
        context: Handler context; user_data is populated via _start_session.

    Returns:
        AWAITING_ANSWER to enter the answer-handling state, or
        ConversationHandler.END if no questions are due today.
    """
    assert update.message is not None
    all_questions = _backend.load_questions()
    today = date.today().isoformat()
    due = select_session(all_questions, today=today)

    if not due:
        await update.message.reply_text("No questions due today. Check back tomorrow!")
        return ConversationHandler.END

    display = _start_session(context, all_questions, due)
    await update.message.reply_text(fmt_question(display[0], 1, len(due)))
    return AWAITING_ANSWER


@_auth
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle a user's answer to the current question.

    Args:
        update: The incoming Telegram update containing the user's reply.
        context: Handler context with session state in user_data.

    Returns:
        AWAITING_ANSWER to continue the session, or ConversationHandler.END
        when the last question has been answered.
    """
    assert update.message is not None
    assert context.user_data is not None
    cursor: int = context.user_data["cursor"]
    session_ids: list[str] = context.user_data["session"]
    qmap: dict[str, Question] = context.user_data["qmap"]
    total: int = len(session_ids)

    qid = session_ids[cursor]
    q = context.user_data["display_qmap"][qid]
    original_q = qmap[qid]

    answer = normalise_answer(update.message.text or "", q)
    if answer is None:
        await update.message.reply_text(f"Please reply with {input_hint(q)}.")
        return AWAITING_ANSWER

    correct = answer == q.correct.upper()
    today = date.today().isoformat()

    updated_q = (
        srs.advance(original_q, today) if correct else srs.demote(original_q, today)
    )
    qmap[updated_q.id] = updated_q
    _backend.append_answer(
        AnswerLogEntry(
            qid=qid,
            topic=q.topic,
            doc_id=q.references[0].doc_id if q.references else "",
            level=updated_q.level,
            correct=correct,
            date=today,
        )
    )

    if correct:
        context.user_data["score"] += 1
    cursor += 1
    context.user_data["cursor"] = cursor

    await update.message.reply_text(fmt_feedback(q, correct))

    if cursor >= total:
        _backend.save_questions(list(qmap.values()))
        score = context.user_data["score"]
        await update.message.reply_text(
            f"Session complete. {score}/{total} correct.\n"
            f"Type /quiz for another session or /stats for progress."
        )
        return ConversationHandler.END

    next_q = context.user_data["display_qmap"][session_ids[cursor]]
    await update.message.reply_text(fmt_question(next_q, cursor + 1, total))
    return AWAITING_ANSWER


@_auth
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /stats command: show pool size, due count, and streak.

    Args:
        update: The incoming Telegram update.
        context: Handler context (unused).

    Note:
        Streak = consecutive calendar days with at least one answer, counting
        back from today. Multiple answers on the same day count as one.

        New (never-answered) questions have next_review == created_date and
        are counted as due, so the total reflects questions ready to study.
    """
    assert update.message is not None
    questions = _backend.load_questions()
    today = date.today().isoformat()
    due = [q for q in questions if q.next_review <= today]

    entries = _backend.load_answers()
    dates_with_answers = sorted({e.date for e in entries}, reverse=True)
    streak = 0
    check = date.fromisoformat(today)
    for d in dates_with_answers:
        if d == check.isoformat():
            streak += 1
            check -= timedelta(days=1)
        else:
            break

    await update.message.reply_text(
        f"📊 Quiz Stats\n"
        f"Total questions: {len(questions)}\n"
        f"Due today: {len(due)}\n"
        f"Current streak: {streak} day{'s' if streak != 1 else ''}"
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    qmap: dict[str, Question] | None = (context.user_data or {}).get("qmap")
    if qmap:
        _backend.save_questions(list(qmap.values()))
    await update.message.reply_text("Session cancelled.")
    return ConversationHandler.END


def main() -> None:
    """Build the bot application and start long-polling.

    Note:
        Uses long-polling rather than a webhook: simpler behind NAT (no port
        forwarding or TLS needed). A webhook cannot run alongside this process
        for the same token.
    """
    app = Application.builder().token(_settings.telegram_bot_token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("quiz", generate_and_start_quiz)],
        states={
            AWAITING_ANSWER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CommandHandler("quiz", generate_and_start_quiz),
        ],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("stats", cmd_stats))

    logger.info("Bot starting (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
