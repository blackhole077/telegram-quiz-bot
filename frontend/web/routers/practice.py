import asyncio
from collections import OrderedDict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from core.question import clean_option, labels, normalise_answer
from core.schemas.question_schemas import QuestionType
from core.schemas.schemas import QuizSession
from frontend.web.constants import TEMPLATES
from frontend.web.dependencies import quiz_service
from frontend.web.schemas.schema import PracticeState
from frontend.web.session import get_session_id, read_session_id, set_session_cookie
from frontend.web.session_store import session_store

router = APIRouter()

_MAX_SESSIONS = 500
_ROUTER = "practice"
_TTL = 7200
_states: OrderedDict[str, PracticeState] = OrderedDict()


def _get_state(request: Request) -> PracticeState:
    session_id = read_session_id(request)
    if session_id not in _states:
        restored = session_store.get(session_id, _ROUTER, PracticeState)
        _states[session_id] = restored if restored is not None else PracticeState()
    _states.move_to_end(session_id)
    if len(_states) > _MAX_SESSIONS:
        _states.popitem(last=False)
    return _states[session_id]


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
    topics = quiz_service.get_topics()
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
    session_id, is_new = get_session_id(request)
    if session_id not in _states:
        restored = session_store.get(session_id, _ROUTER, PracticeState)
        _states[session_id] = restored if restored is not None else PracticeState()
    _states.move_to_end(session_id)
    if len(_states) > _MAX_SESSIONS:
        _states.popitem(last=False)
    state = _states[session_id]

    questions = quiz_service.prepare_practice(topic or None, count)
    if not questions:
        resp = HTMLResponse(
            '<p class="nothing-due">No questions found for that topic.</p>'
        )
        if is_new:
            set_session_cookie(resp, session_id)
        return resp
    state.session = quiz_service.start_session(questions)
    state.wrong_answers = []
    await asyncio.to_thread(session_store.put, session_id, _ROUTER, state, _TTL)
    resp = TEMPLATES.TemplateResponse(
        request=request,
        name="question.html",
        context=_question_context(state.session),
    )
    if is_new:
        set_session_cookie(resp, session_id)
    return resp


@router.post("/practice/answer", response_class=HTMLResponse, tags=["practice"])
async def practice_answer(request: Request, answer: Annotated[str, Form()]):
    state = _get_state(request)
    if state.session is None:
        return HTMLResponse(
            '<p class="nothing-due">No active session. <a href="/practice">Start over</a>.</p>'
        )

    question = state.session.current_display
    normalised = normalise_answer(answer, question)
    if normalised is None:
        ctx = _question_context(state.session)
        ctx["error"] = "Please select a valid option."
        return TEMPLATES.TemplateResponse(
            request=request, name="question.html", context=ctx
        )

    correct = normalised == question.correct.upper()
    if correct:
        state.session.score += 1
    state.session.cursor += 1

    lbls = labels(question)
    correct_text = ""
    if not correct and question.correct in lbls:
        idx = lbls.index(question.correct)
        correct_text = clean_option(question.options[idx])

    if not correct:
        state.wrong_answers.append(
            {
                "question_text": question.question,
                "correct_label": question.correct,
                "correct_text": correct_text,
                "explanation": question.explanation,
            }
        )
    session_id = read_session_id(request)
    await asyncio.to_thread(session_store.put, session_id, _ROUTER, state, _TTL)

    ref = question.references[0] if question.references else None
    is_last = state.session.is_complete

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
    state = _get_state(request)
    if state.session is None:
        return HTMLResponse(
            '<p class="nothing-due">No active session. <a href="/practice">Start over</a>.</p>'
        )

    if state.session.is_complete:
        score = state.session.score
        total = state.session.total
        wrong = list(state.wrong_answers)
        state.session = None
        state.wrong_answers.clear()
        session_id = read_session_id(request)
        await asyncio.to_thread(session_store.delete, session_id, _ROUTER)
        return TEMPLATES.TemplateResponse(
            request=request,
            name="practice_summary.html",
            context={"score": score, "total": total, "wrong_answers": wrong},
        )

    return TEMPLATES.TemplateResponse(
        request=request,
        name="question.html",
        context=_question_context(state.session),
    )
