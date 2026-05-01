"""Learn/exercise router.

All exercise logic lives in core.learn_service.LearnService.
This router only dispatches to service methods and renders templates.

State is stored as LearnState (serializable). A transient LearnService is
reconstructed from LearnState at the start of each handler and discarded
after the response is built.
"""

import asyncio
from collections import OrderedDict
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse

from core.exam import normalise_latex
from core.knowledge import get_knowledge_graph
from core.learn_service import LearnService
from frontend.web.constants import TEMPLATES
from frontend.web.schemas.schema import LearnState
from frontend.web.session import get_session_id, read_session_id, set_session_cookie
from frontend.web.session_store import session_store

router = APIRouter()

_MAX_SESSIONS = 500
_ROUTER = "learn"
_TTL = 3600
_states: OrderedDict[str, LearnState] = OrderedDict()


def _get_state(request: Request) -> LearnState:
    session_id = read_session_id(request)
    if session_id not in _states:
        restored = session_store.get(session_id, _ROUTER, LearnState)
        _states[session_id] = restored if restored is not None else LearnState()
    _states.move_to_end(session_id)
    if len(_states) > _MAX_SESSIONS:
        _states.popitem(last=False)
    return _states[session_id]


def _service_from_state(state: LearnState) -> LearnService:
    svc = LearnService()
    svc.exercise_type = state.exercise_type
    svc.concept_a = state.concept_a
    svc.concept_b = state.concept_b
    svc.edge_type = state.edge_type
    svc.domain_b = state.domain_b
    svc.audience = state.audience
    svc.generated_content = state.generated_content
    svc.solution_steps = list(state.solution_steps)
    return svc


def _copy_service_to_state(service: LearnService, state: LearnState) -> None:
    state.exercise_type = service.exercise_type
    state.concept_a = service.concept_a
    state.concept_b = service.concept_b
    state.edge_type = service.edge_type
    state.domain_b = service.domain_b
    state.audience = service.audience
    state.generated_content = service.generated_content
    state.solution_steps = list(service.solution_steps)


def _node_names() -> list[str]:
    return sorted(node.name for node in get_knowledge_graph().all_nodes())


@router.get("/learn", response_class=HTMLResponse, tags=["learn"])
async def learn_page(request: Request):
    return TEMPLATES.TemplateResponse(
        request=request,
        name="learn_config.html",
        context={"node_names": _node_names()},
    )


@router.get("/learn/neighbors", response_class=HTMLResponse, tags=["learn"])
async def learn_neighbors(concept_a: Annotated[str, Query()] = ""):
    graph = get_knowledge_graph()
    edges = graph.get_neighbors(concept_a)
    if not edges:
        return HTMLResponse('<option value="">No connected concepts found</option>')
    options = "\n".join(
        f'<option value="{edge.target}">{edge.target}</option>' for edge in edges
    )
    return HTMLResponse(options)


@router.post("/learn/start", response_class=HTMLResponse, tags=["learn"])
async def learn_start(
    request: Request,
    exercise_type: Annotated[str, Form()],
    concept_a: Annotated[str, Form()],
    concept_b: Annotated[str, Form()] = "",
    domain_b: Annotated[str, Form()] = "",
    audience: Annotated[str, Form()] = "a fellow student",
):
    session_id, is_new = get_session_id(request)
    if session_id not in _states:
        restored = session_store.get(session_id, _ROUTER, LearnState)
        _states[session_id] = restored if restored is not None else LearnState()
    _states.move_to_end(session_id)
    if len(_states) > _MAX_SESSIONS:
        _states.popitem(last=False)
    state = _states[session_id]
    service = _service_from_state(state)

    def _with_cookie(resp: HTMLResponse) -> HTMLResponse:
        if is_new:
            set_session_cookie(resp, session_id)
        return resp

    if exercise_type == "connect":
        started = await asyncio.to_thread(service.start_connect, concept_a, concept_b)
        if started.error:
            return _with_cookie(
                HTMLResponse(
                    '<p class="nothing-due">Failed to generate exercise. Check LLM settings.</p>'
                )
            )
        _copy_service_to_state(service, state)
        await asyncio.to_thread(session_store.put, session_id, _ROUTER, state, _TTL)
        return _with_cookie(
            TEMPLATES.TemplateResponse(
                request=request,
                name="learn_exercise.html",
                context={
                    "exercise_type": exercise_type,
                    "prompt": normalise_latex(started.generated_content),
                    "subtitle": f"Explain the connection between {concept_a} and {concept_b}",
                    "placeholder": "Describe how these two concepts are related, and why that connection matters...",
                },
            )
        )

    if exercise_type == "debug":
        started = await asyncio.to_thread(service.start_debug, concept_a, domain_b)
        if started.error:
            return _with_cookie(
                HTMLResponse(
                    '<p class="nothing-due">Failed to generate exercise. Check LLM settings.</p>'
                )
            )
        _copy_service_to_state(service, state)
        await asyncio.to_thread(session_store.put, session_id, _ROUTER, state, _TTL)
        return _with_cookie(
            TEMPLATES.TemplateResponse(
                request=request,
                name="learn_exercise.html",
                context={
                    "exercise_type": exercise_type,
                    "prompt": normalise_latex(started.generated_content),
                    "subtitle": f"Something is wrong with this application of {concept_a} in {domain_b}",
                    "placeholder": "Identify the error and explain what the correct application should be...",
                },
            )
        )

    if exercise_type == "derive":
        started = await asyncio.to_thread(service.start_derive, concept_a)
        if started.error:
            return _with_cookie(
                HTMLResponse(
                    '<p class="nothing-due">Failed to generate exercise. Check LLM settings.</p>'
                )
            )
        blank_count = started.generated_content.count("[...]")
        _copy_service_to_state(service, state)
        await asyncio.to_thread(session_store.put, session_id, _ROUTER, state, _TTL)
        return _with_cookie(
            TEMPLATES.TemplateResponse(
                request=request,
                name="learn_exercise.html",
                context={
                    "exercise_type": exercise_type,
                    "prompt": normalise_latex(started.generated_content),
                    "subtitle": f"Fill in the {blank_count} blank step{'s' if blank_count != 1 else ''} in this derivation",
                    "placeholder": "Write your answers for the blank steps, one per line...",
                },
            )
        )

    if exercise_type == "teach":
        service.start_teach(concept_a, audience)
        _copy_service_to_state(service, state)
        await asyncio.to_thread(session_store.put, session_id, _ROUTER, state, _TTL)
        return _with_cookie(
            TEMPLATES.TemplateResponse(
                request=request,
                name="learn_exercise.html",
                context={
                    "exercise_type": exercise_type,
                    "prompt": f"Explain {concept_a} to {audience}.",
                    "subtitle": f"Teach-it-back: explain {concept_a} as if speaking to {audience}",
                    "placeholder": f"Write your explanation of {concept_a} for {audience}...",
                },
            )
        )

    return _with_cookie(
        HTMLResponse('<p class="nothing-due">Unknown exercise type.</p>')
    )


@router.post("/learn/submit", response_class=HTMLResponse, tags=["learn"])
async def learn_submit(
    request: Request,
    answer: Annotated[str, Form()],
):
    state = _get_state(request)
    if not state.exercise_type:
        return HTMLResponse(
            '<p class="nothing-due">No active exercise. <a href="/learn">Start over</a>.</p>'
        )

    exercise_type = state.exercise_type
    service = _service_from_state(state)

    if exercise_type == "connect":
        result = await asyncio.to_thread(service.grade_connect, answer)
        return TEMPLATES.TemplateResponse(
            request=request,
            name="learn_feedback.html",
            context={
                "exercise_type": exercise_type,
                "correct": result.correct,
                "score": result.score,
                "feedback": normalise_latex(result.feedback),
                "missing_claims": result.missing_relational_claims,
                "incorrect_claims": result.incorrect_relational_claims,
                "model_solution": normalise_latex(result.model_answer),
                "error": result.error,
                "concept_a": state.concept_a,
                "concept_b": state.concept_b,
            },
        )

    if exercise_type == "debug":
        result = await asyncio.to_thread(service.grade_debug, answer)
        return TEMPLATES.TemplateResponse(
            request=request,
            name="learn_feedback.html",
            context={
                "exercise_type": exercise_type,
                "correct": result.correct,
                "score": result.score,
                "feedback": normalise_latex(result.feedback),
                "missing_claims": [],
                "incorrect_claims": [],
                "model_solution": normalise_latex(result.model_solution),
                "error": result.error,
                "concept_a": state.concept_a,
                "concept_b": state.domain_b,
            },
        )

    if exercise_type == "derive":
        result = await asyncio.to_thread(service.grade_derive, answer)
        return TEMPLATES.TemplateResponse(
            request=request,
            name="learn_feedback.html",
            context={
                "exercise_type": exercise_type,
                "correct": result.correct,
                "score": result.score,
                "feedback": normalise_latex(result.feedback),
                "missing_claims": [],
                "incorrect_claims": [],
                "model_solution": normalise_latex(result.model_solution),
                "error": result.error,
                "concept_a": state.concept_a,
                "concept_b": "",
            },
        )

    if exercise_type == "teach":
        result = await asyncio.to_thread(service.grade_teach, answer)
        return TEMPLATES.TemplateResponse(
            request=request,
            name="learn_feedback.html",
            context={
                "exercise_type": exercise_type,
                "correct": result.score >= 0.7,
                "score": result.score,
                "feedback": normalise_latex(result.feedback),
                "missing_claims": result.missing_concepts,
                "incorrect_claims": result.analogy_issues,
                "model_solution": normalise_latex(result.model_answer),
                "error": result.error,
                "concept_a": state.concept_a,
                "concept_b": state.audience,
            },
        )

    return HTMLResponse('<p class="nothing-due">Unknown exercise type.</p>')
