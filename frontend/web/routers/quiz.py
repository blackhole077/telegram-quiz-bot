from collections import OrderedDict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from core.question import clean_option, labels
from core.schemas.question_schemas import QuestionType
from core.schemas.schemas import QuizSession
from frontend.web.constants import TEMPLATES
from frontend.web.dependencies import quiz_service
from frontend.web.schemas.schema import QuizState
from frontend.web.session import get_session_id, read_session_id, set_session_cookie

router = APIRouter()

_MAX_SESSIONS = 500
_states: OrderedDict[str, QuizState] = OrderedDict()


def _get_state(request: Request) -> QuizState:
    session_id = read_session_id(request)
    if session_id not in _states:
        _states[session_id] = QuizState()
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
        "answer_url": "/quiz/answer",
        "next_url": "/quiz/next",
        "target": "#quiz-area",
    }


@router.get("/quiz", response_class=HTMLResponse, tags=["quiz"])
async def quiz_page(request: Request):
    total, due = quiz_service.get_stats(_today())
    return TEMPLATES.TemplateResponse(
        request=request,
        name="quiz.html",
        context={"total": total, "due": due},
    )


@router.post("/quiz/start", response_class=HTMLResponse, tags=["quiz"])
async def quiz_start(request: Request):
    session_id, is_new = get_session_id(request)
    if session_id not in _states:
        _states[session_id] = QuizState()
    _states.move_to_end(session_id)
    if len(_states) > _MAX_SESSIONS:
        _states.popitem(last=False)
    state = _states[session_id]

    due = quiz_service.prepare_session(_today())
    if not due:
        resp = HTMLResponse(
            '<p class="nothing-due">Nothing due right now. Check back tomorrow!</p>'
        )
        if is_new:
            set_session_cookie(resp, session_id)
        return resp
    state.session = quiz_service.start_session(due)
    state.wrong_answers = []
    resp = TEMPLATES.TemplateResponse(
        request=request,
        name="question.html",
        context=_question_context(state.session),
    )
    if is_new:
        set_session_cookie(resp, session_id)
    return resp


@router.post("/quiz/answer", response_class=HTMLResponse, tags=["quiz"])
async def quiz_answer(request: Request, answer: Annotated[str, Form()]):
    state = _get_state(request)
    if state.session is None:
        return HTMLResponse(
            '<p class="nothing-due">No active session. <a href="/">Start over</a>.</p>'
        )

    outcome = quiz_service.process_answer(state.session, answer, _today())
    if outcome is None:
        ctx = _question_context(state.session)
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
        state.wrong_answers.append(
            {
                "question_text": question.question,
                "correct_label": question.correct,
                "correct_text": correct_text,
                "explanation": question.explanation,
            }
        )

    ref = question.references[0] if question.references else None
    is_last = state.session.is_complete

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
    state = _get_state(request)
    if state.session is None:
        return HTMLResponse(
            '<p class="nothing-due">No active session. <a href="/">Start over</a>.</p>'
        )

    if state.session.is_complete:
        score = state.session.score
        total = state.session.total
        wrong = list(state.wrong_answers)
        quiz_service.end_session(state.session)
        state.session = None
        state.wrong_answers.clear()
        total_questions, new_due = quiz_service.get_stats(_today())
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
        context=_question_context(state.session),
    )
