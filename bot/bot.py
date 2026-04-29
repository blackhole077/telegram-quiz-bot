"""Telegram bot: SRS quiz sessions, free-text practice, and LLM-graded exams."""

from __future__ import annotations

import asyncio
import functools
import io
import logging
from collections.abc import Callable, Coroutine
from datetime import date
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from backend import make_backend
from core.config import settings
from core.exam import render_exam_pdf
from core.llm import (generate_exam, grade_answer, grade_from_image,
                      grade_from_text)
from core.problems import filter_by_topic, load_problems, pick_random
from core.question import fmt_feedback, fmt_question, input_hint
from core.schemas.schemas import QuizSession
from core.service import QuizService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AWAITING_ANSWER = 1
AWAITING_PRACTICE_ANSWER = 2
AWAITING_EXAM_ANSWER = 3

_KEY_SESSION = "session"
_KEY_PRACTICE_PROBLEM = "practice_problem"
_KEY_EXAM_PROBLEMS = "exam_problems"

_PROBLEMS_PATH = Path(settings.data_dir) / "problems.json"
try:
    _PROBLEMS = load_problems(_PROBLEMS_PATH)
except FileNotFoundError:
    _PROBLEMS = []

_service: QuizService = QuizService(make_backend(settings))

_Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, Any]]


def _auth(func: _Handler) -> _Handler:
    """Silently drop updates from unauthorised users; catch unexpected handler errors."""

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        if (
            update.effective_user
            and update.effective_user.id != settings.allowed_user_id
        ):
            logger.warning(
                "Ignoring message from unknown user %s", update.effective_user.id
            )
            return ConversationHandler.END
        try:
            return await func(update, context)
        except Exception:
            logger.exception("Handler %s raised", func.__name__)
            if update.message:
                await update.message.reply_text("An error occurred. Please try again.")
            return ConversationHandler.END

    return wrapper  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# /quiz
# ---------------------------------------------------------------------------


@_auth
async def generate_and_start_quiz(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    assert update.message is not None
    today = date.today().isoformat()
    due = _service.prepare_session(today)

    if not due:
        await update.message.reply_text(
            "No questions due today. "
            "Use /practice for word problems or /exam <topic> for a full test."
        )
        return ConversationHandler.END

    session = _service.start_session(due)
    context.user_data[_KEY_SESSION] = session  # type: ignore[index]
    await update.message.reply_text(
        fmt_question(session.current_display, 1, session.total)
    )
    return AWAITING_ANSWER


@_auth
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    assert context.user_data is not None
    session: QuizSession = context.user_data[_KEY_SESSION]
    today = date.today().isoformat()

    outcome = _service.process_answer(session, update.message.text or "", today)
    if outcome is None:
        await update.message.reply_text(
            f"Please reply with {input_hint(session.current_display)}."
        )
        return AWAITING_ANSWER

    await update.message.reply_text(
        fmt_feedback(outcome.graded_question, outcome.correct)
    )

    if session.is_complete:
        await asyncio.to_thread(_service.end_session, session)
        await update.message.reply_text(
            f"Session complete. {session.score}/{session.total} correct.\n"
            "Type /quiz for another session or /stats for progress."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        fmt_question(session.current_display, session.cursor + 1, session.total)
    )
    return AWAITING_ANSWER


# ---------------------------------------------------------------------------
# /practice
# ---------------------------------------------------------------------------


@_auth
async def cmd_practice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    topic = " ".join(context.args).strip() if context.args else ""

    if not _PROBLEMS:
        await update.message.reply_text("No problems available yet.")
        return ConversationHandler.END

    pool = filter_by_topic(_PROBLEMS, topic) if topic else _PROBLEMS
    if not pool:
        await update.message.reply_text(f"No problems found for topic '{topic}'.")
        return ConversationHandler.END

    problem = pick_random(pool)[0]
    context.user_data[_KEY_PRACTICE_PROBLEM] = problem  # type: ignore[index]
    await update.message.reply_text(
        f"Practice ({problem.topic}, difficulty {problem.difficulty}/3):\n\n"
        f"{problem.prompt}\n\n"
        "Reply with your answer."
    )
    return AWAITING_PRACTICE_ANSWER


@_auth
async def handle_practice_answer(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    assert update.message is not None
    assert context.user_data is not None
    problem = context.user_data.get(_KEY_PRACTICE_PROBLEM)
    if problem is None:
        return ConversationHandler.END

    await update.message.reply_text("Grading...")
    result = await asyncio.to_thread(
        grade_answer, problem.prompt, problem.solution_steps, update.message.text or ""
    )

    parts = [f"{'Correct' if result.correct else 'Incorrect'} ({result.score:.0%})"]
    parts.append(result.feedback)
    if not result.correct and result.model_solution:
        parts.append(f"\nModel solution:\n{result.model_solution}")
    parts.append("\nSend /practice for another problem or /quiz to resume reviewing.")

    await update.message.reply_text("\n\n".join(parts))
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /exam
# ---------------------------------------------------------------------------


@_auth
async def cmd_exam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    if not context.args:
        await update.message.reply_text(
            "Usage: /exam <category>  e.g. /exam Linear Algebra"
        )
        return ConversationHandler.END

    category = " ".join(context.args)
    today = date.today().isoformat()

    await update.message.reply_text(f"Generating {category} exam...")

    report = await asyncio.to_thread(_service.get_gap_report)
    problems = await asyncio.to_thread(
        generate_exam, category, n_questions=5, weak_topics=report.flagged_topics
    )
    if not problems:
        await update.message.reply_text("Exam generation failed. Please try again.")
        return ConversationHandler.END

    difficult_topics = {dq.question.topic for dq in report.difficult_questions}
    problems = [
        p.model_copy(update={"is_remedial": p.topic in difficult_topics})
        for p in problems
    ]

    pdf_bytes = await asyncio.to_thread(render_exam_pdf, problems, category, today)
    context.user_data[_KEY_EXAM_PROBLEMS] = problems  # type: ignore[index]

    filename = f"exam_{category.lower().replace(' ', '_')}_{today}.pdf"
    await update.message.reply_document(
        document=io.BytesIO(pdf_bytes),
        filename=filename,
        caption="Reply with your typed answers or send a photo of your completed work.",
    )
    return AWAITING_EXAM_ANSWER


@_auth
async def handle_exam_submission(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    assert update.message is not None
    assert context.user_data is not None
    problems = context.user_data.get(_KEY_EXAM_PROBLEMS)
    if problems is None:
        return ConversationHandler.END

    await update.message.reply_text("Grading your exam...")

    if update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        image_bytes = bytes(await file.download_as_bytearray())
        result = await asyncio.to_thread(grade_from_image, problems, image_bytes)
    else:
        result = await asyncio.to_thread(
            grade_from_text, problems, update.message.text or ""
        )

    parts = [f"Score: {result.total_score:.0%}", result.summary]
    for p in result.problems:
        parts.append(f"Problem {p.number}: {p.score:.0%} - {p.feedback}")
    if result.error:
        parts.append(f"Note: {result.error}")

    await update.message.reply_text("\n\n".join(parts))
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /stats, /cancel
# ---------------------------------------------------------------------------


@_auth
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    today = date.today().isoformat()
    total, due_count = _service.get_stats(today)
    await update.message.reply_text(
        f"Quiz Stats\nTotal questions: {total}\nDue today: {due_count}"
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    assert update.message is not None
    session: QuizSession | None = (context.user_data or {}).get(_KEY_SESSION)
    if session:
        _service.end_session(session)
    await update.message.reply_text("Session cancelled.")
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------


def main() -> None:
    app = Application.builder().token(settings.telegram_bot_token).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("quiz", generate_and_start_quiz),
            CommandHandler("practice", cmd_practice),
            CommandHandler("exam", cmd_exam),
        ],
        states={
            AWAITING_ANSWER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer),
            ],
            AWAITING_PRACTICE_ANSWER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_practice_answer),
            ],
            AWAITING_EXAM_ANSWER: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
                    handle_exam_submission,
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CommandHandler("quiz", generate_and_start_quiz),
            CommandHandler("practice", cmd_practice),
            CommandHandler("exam", cmd_exam),
        ],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("stats", cmd_stats))

    logger.info("Bot starting (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
