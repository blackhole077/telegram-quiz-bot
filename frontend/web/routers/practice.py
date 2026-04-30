from datetime import date
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from backend.backends import make_backend
from core.config import settings
from core.question import clean_option, labels, normalise_answer
from core.schemas.question_schemas import QuestionType
from core.schemas.schemas import QuizSession
from core.service import QuizService
from frontend.web.constants import TEMPLATES
from frontend.web.schemas.schema import PracticeState

router = APIRouter()

_service = QuizService(make_backend(settings), settings.topics_path)

_state = PracticeState()


def _today() -> str:
    return date.today().isoformat()


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
        "answer_url": "/practice/answer",
        "next_url": "/practice/next",
        "target": "#practice-area",
    }


@router.get("/practice", response_class=HTMLResponse, tags=["practice"])
async def practice_page(request: Request):
    topics = _service.get_topics()
    return TEMPLATES.TemplateResponse(
        request=request,
        name="practice_config.html",
        context={"topics": topics},
    )


@router.post("/practice/start", response_class=HTMLResponse, tags=["practice"])
async def practice_start(
    request: Request,
    topic: Annotated[str, Form()] = "",
    count: Annotated[int, Form()] = 10,
):
    questions = _service.prepare_practice(topic or None, count)
    if not questions:
        return HTMLResponse(
            '<p class="nothing-due">No questions found for that topic.</p>'
        )
    _state.session = _service.start_session(questions)
    _state.wrong_answers = []
    return TEMPLATES.TemplateResponse(
        request=request,
        name="question.html",
        context=_question_context(_state.session),
    )


@router.post("/practice/answer", response_class=HTMLResponse, tags=["practice"])
async def practice_answer(request: Request, answer: Annotated[str, Form()]):
    if _state.session is None:
        return HTMLResponse(
            '<p class="nothing-due">No active session. <a href="/practice">Start over</a>.</p>'
        )

    question = _state.session.current_display
    normalised = normalise_answer(answer, question)
    if normalised is None:
        ctx = _question_context(_state.session)
        ctx["error"] = "Please select a valid option."
        return TEMPLATES.TemplateResponse(
            request=request, name="question.html", context=ctx
        )

    correct = normalised == question.correct.upper()
    if correct:
        _state.session.score += 1
    _state.session.cursor += 1

    lbls = labels(question)
    correct_text = ""
    if not correct and question.correct in lbls:
        idx = lbls.index(question.correct)
        correct_text = clean_option(question.options[idx])

    if not correct:
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
            "correct": correct,
            "correct_label": question.correct,
            "correct_text": correct_text,
            "explanation": question.explanation,
            "ref": ref,
            "is_last": is_last,
            "next_url": "/practice/next",
            "target": "#practice-area",
        },
    )


@router.get("/practice/next", response_class=HTMLResponse, tags=["practice"])
async def practice_next(request: Request):
    if _state.session is None:
        return HTMLResponse(
            '<p class="nothing-due">No active session. <a href="/practice">Start over</a>.</p>'
        )

    if _state.session.is_complete:
        score = _state.session.score
        total = _state.session.total
        wrong = list(_state.wrong_answers)
        _state.session = None
        _state.wrong_answers.clear()
        return TEMPLATES.TemplateResponse(
            request=request,
            name="practice_summary.html",
            context={"score": score, "total": total, "wrong_answers": wrong},
        )

    return TEMPLATES.TemplateResponse(
        request=request,
        name="question.html",
        context=_question_context(_state.session),
    )
