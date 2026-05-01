"""Exam router.

Exam generation and grading logic lives in core.exam_service.ExamService.
This router only dispatches to service methods and renders templates.
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse

from backend.backends import make_backend
from core.config import settings
from core.exam import normalise_latex
from core.exam_service import ExamService
from core.service import QuizService
from frontend.web.constants import TEMPLATES
from frontend.web.schemas.schema import ExamState
from frontend.web.session import get_session_id, read_session_id

router = APIRouter()

_quiz_service = QuizService(make_backend(settings), settings.topics_path)
_exam_service = ExamService()

_states: dict[str, ExamState] = {}


def _get_state(request: Request) -> ExamState:
    session_id = read_session_id(request)
    if session_id not in _states:
        _states[session_id] = ExamState()
    return _states[session_id]


@router.get("/exam", response_class=HTMLResponse, tags=["exam"])
async def exam_page(request: Request):
    return TEMPLATES.TemplateResponse(
        request=request, name="exam_config.html", context={}
    )


@router.post("/exam/start", response_class=HTMLResponse, tags=["exam"])
async def exam_start(
    request: Request,
    response: Response,
    category: Annotated[str, Form()],
    count: Annotated[int, Form()] = 5,
):
    session_id = get_session_id(request, response)
    if session_id not in _states:
        _states[session_id] = ExamState()
    state = _states[session_id]

    weak_topics = _quiz_service.get_weak_topics()
    problems = await asyncio.to_thread(
        _exam_service.generate, category, count, weak_topics
    )
    if not problems:
        return HTMLResponse(
            '<p class="nothing-due">Failed to generate exam. Check LLM settings and try again.</p>'
        )
    state.problems = problems
    state.category = category
    return TEMPLATES.TemplateResponse(
        request=request,
        name="exam_form.html",
        context={"problems": state.problems},
    )


@router.post("/exam/submit", response_class=HTMLResponse, tags=["exam"])
async def exam_submit(request: Request, answer: Annotated[list[str], Form()]):
    state = _get_state(request)
    if not state.problems:
        return HTMLResponse(
            '<p class="nothing-due">No active exam. <a href="/exam">Start over</a>.</p>'
        )

    result = await asyncio.to_thread(_exam_service.grade, state.problems, answer)

    normalised_grades = [
        {
            "number": grade.number,
            "score": grade.score,
            "feedback": normalise_latex(grade.feedback),
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
