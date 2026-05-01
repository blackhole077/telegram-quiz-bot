"""Exam router.

Exam generation and grading logic lives in core.exam_service.ExamService.
This router only dispatches to service methods and renders templates.
"""

import asyncio
from collections import OrderedDict
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from core.exam import normalise_latex
from core.exam_service import ExamService
from frontend.web.constants import TEMPLATES
from frontend.web.dependencies import quiz_service
from frontend.web.schemas.schema import ExamState
from frontend.web.session import get_session_id, read_session_id, set_session_cookie
from frontend.web.session_store import session_store

router = APIRouter()

_exam_service = ExamService()

_MAX_SESSIONS = 500
_ROUTER = "exam"
_TTL = 14400
_states: OrderedDict[str, ExamState] = OrderedDict()


def _get_state(request: Request) -> ExamState:
    session_id = read_session_id(request)
    if session_id not in _states:
        restored = session_store.get(session_id, _ROUTER, ExamState)
        _states[session_id] = restored if restored is not None else ExamState()
    _states.move_to_end(session_id)
    if len(_states) > _MAX_SESSIONS:
        _states.popitem(last=False)
    return _states[session_id]


@router.get("/exam", response_class=HTMLResponse, tags=["exam"])
async def exam_page(request: Request):
    return TEMPLATES.TemplateResponse(
        request=request, name="exam_config.html", context={}
    )


@router.post("/exam/start", response_class=HTMLResponse, tags=["exam"])
async def exam_start(
    request: Request,
    category: Annotated[str, Form()],
    count: Annotated[int, Form()] = 5,
):
    session_id, is_new = get_session_id(request)
    if session_id not in _states:
        restored = session_store.get(session_id, _ROUTER, ExamState)
        _states[session_id] = restored if restored is not None else ExamState()
    _states.move_to_end(session_id)
    if len(_states) > _MAX_SESSIONS:
        _states.popitem(last=False)
    state = _states[session_id]

    weak_topics = quiz_service.get_weak_topics()
    problems = await asyncio.to_thread(
        _exam_service.generate, category, count, weak_topics
    )
    if not problems:
        resp = HTMLResponse(
            '<p class="nothing-due">Failed to generate exam. Check LLM settings and try again.</p>'
        )
        if is_new:
            set_session_cookie(resp, session_id)
        return resp
    state.problems = problems
    state.category = category
    await asyncio.to_thread(session_store.put, session_id, _ROUTER, state, _TTL)
    resp = TEMPLATES.TemplateResponse(
        request=request,
        name="exam_form.html",
        context={"problems": state.problems},
    )
    if is_new:
        set_session_cookie(resp, session_id)
    return resp


@router.post("/exam/submit", response_class=HTMLResponse, tags=["exam"])
async def exam_submit(request: Request, answer: Annotated[list[str], Form()]):
    state = _get_state(request)
    if not state.problems:
        return HTMLResponse(
            '<p class="nothing-due">No active exam. <a href="/exam">Start over</a>.</p>'
        )

    result = await asyncio.to_thread(_exam_service.grade, state.problems, answer)

    solution_by_number = {problem.number: problem.solution for problem in state.problems}

    normalised_grades = [
        {
            "number": grade.number,
            "score": grade.score,
            "feedback": normalise_latex(grade.feedback),
            "solution": solution_by_number.get(grade.number, ""),
        }
        for grade in result.problems
    ]
    return TEMPLATES.TemplateResponse(
        request=request,
        name="exam_results.html",
        context={
            "grades": normalised_grades,
            "total_score": result.total_score,
            "summary": normalise_latex(result.summary),
            "category": state.category,
            "error": result.error,
        },
    )
