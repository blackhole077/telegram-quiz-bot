from datetime import date
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from backend.backends import make_backend
from core.config import settings
from core.question import clean_option, labels
from core.schemas.question_schemas import QuestionType
from core.schemas.schemas import QuizSession
from core.service import QuizService
from web.constants import TEMPLATES
from web.schemas.schema import QuizState

router = APIRouter()

_service = QuizService(make_backend(settings), settings.topics_path)

_state = QuizState()


def _today() -> str:
    return date.today().isoformat()


# NOTE: FastAPI does support Pydantic (or rather, it uses it under the hood) so we might as well make use of it.
def _question_context(session: QuizSession) -> dict:
    question = session.current_display
    lbls = labels(question)
    is_tof = question.type is QuestionType.TRUE_OR_FALSE
    cleaned_options = [
        {
            "label": label,
            "text": clean_option(opt),
            "answer_val": clean_option(opt) if is_tof else label,
            "key_num": str(idx + 1),
        }
        for idx, (label, opt) in enumerate(zip(lbls, question.options))
    ]
    return {
        "question": question,
        "options": cleaned_options,
        "cursor": session.cursor,
        "total": session.total,
        "error": None,
        "answer_url": "/quiz/answer",
        "next_url": "/quiz/next",
        "target": "#quiz-area",
    }


# NOTE: I'll need to look at how FastAPI handles it, but splitting up the routes into their own pieces (e.g., quiz.py, exam.py, etc.) would be nice.
@router.get("/quiz", response_class=HTMLResponse, tags=["quiz"])
async def quiz_page(request: Request):
    total, due = _service.get_stats(_today())
    return TEMPLATES.TemplateResponse(
        request=request,
        name="quiz.html",
        context={"total": total, "due": due},
    )


@router.post("/quiz/start", response_class=HTMLResponse, tags=["quiz"])
async def quiz_start(request: Request):
    due = _service.prepare_session(_today())
    if not due:
        return HTMLResponse(
            '<p class="nothing-due">Nothing due right now. Check back tomorrow!</p>'
        )
    _state.session = _service.start_session(due)
    _state.wrong_answers = []
    return TEMPLATES.TemplateResponse(
        request=request,
        name="question.html",
        context=_question_context(_state.session),
    )


@router.post("/quiz/answer", response_class=HTMLResponse, tags=["quiz"])
async def quiz_answer(request: Request, answer: Annotated[str, Form()]):
    if _state.session is None:
        return HTMLResponse(
            '<p class="nothing-due">No active session. <a href="/">Start over</a>.</p>'
        )

    outcome = _service.process_answer(_state.session, answer, _today())
    if outcome is None:
        ctx = _question_context(_state.session)
        ctx["error"] = "Please select a valid option (A, B, C, or D)."
        return TEMPLATES.TemplateResponse(
            request=request, name="question.html", context=ctx
        )

    question = outcome.graded_question
    lbls = labels(question)
    correct_text = ""
    if not outcome.correct and question.correct in lbls:
        idx = lbls.index(question.correct)
        correct_text = clean_option(question.options[idx])

    if not outcome.correct:
        _state.wrong_answers.append(
            {
                "question_text": question.question,
                "correct_label": question.correct,
                "correct_text": correct_text,
                "explanation": question.explanation,
            }
        )

    ref = question.references[0] if question.references else None
    is_last = _state.session.is_complete

    return TEMPLATES.TemplateResponse(
        request=request,
        name="feedback.html",
        context={
            "correct": outcome.correct,
            "correct_label": question.correct,
            "correct_text": correct_text,
            "explanation": question.explanation,
            "ref": ref,
            "is_last": is_last,
            "next_url": "/quiz/next",
            "target": "#quiz-area",
        },
    )


@router.get("/quiz/next", response_class=HTMLResponse, tags=["quiz"])
async def quiz_next(request: Request):
    # NOTE: Might be better to just redirect back to "/quiz" instead?
    if _state.session is None:
        return HTMLResponse(
            '<p class="nothing-due">No active session. <a href="/">Start over</a>.</p>'
        )

    if _state.session.is_complete:
        score = _state.session.score
        total = _state.session.total
        wrong = list(_state.wrong_answers)
        _service.end_session(_state.session)
        _state.session = None
        _state.wrong_answers.clear()
        total_questions, new_due = _service.get_stats(_today())
        return TEMPLATES.TemplateResponse(
            request=request,
            name="summary.html",
            context={
                "score": score,
                "total": total,
                "wrong_answers": wrong,
                "total_questions": total_questions,
                "new_due": new_due,
            },
        )

    return TEMPLATES.TemplateResponse(
        request=request,
        name="question.html",
        context=_question_context(_state.session),
    )
