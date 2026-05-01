import asyncio
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request, Response
from fastapi.responses import HTMLResponse

from core.exam import normalise_latex
from core.knowledge import get_knowledge_graph
from core.llm import (
    evaluate_relational_explanation,
    generate_bridge_question,
    generate_scaffolded_derivation,
    generate_wrong_transposition,
    grade_answer,
    grade_teach_it_back,
)
from frontend.web.constants import TEMPLATES
from frontend.web.schemas.schema import LearnState
from frontend.web.session import get_session_id, read_session_id

router = APIRouter()

_states: dict[str, LearnState] = {}


def _get_state(request: Request) -> LearnState:
    session_id = read_session_id(request)
    if session_id not in _states:
        _states[session_id] = LearnState()
    return _states[session_id]


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
    response: Response,
    exercise_type: Annotated[str, Form()],
    concept_a: Annotated[str, Form()],
    concept_b: Annotated[str, Form()] = "",
    domain_b: Annotated[str, Form()] = "",
    audience: Annotated[str, Form()] = "a fellow student",
):
    session_id = get_session_id(request, response)
    if session_id not in _states:
        _states[session_id] = LearnState()
    state = _states[session_id]

    graph = get_knowledge_graph()
    node_a = graph.get_node(concept_a)
    topic_material = node_a.description if node_a else ""

    state.exercise_type = exercise_type
    state.concept_a = concept_a
    state.concept_b = concept_b
    state.domain_b = domain_b
    state.audience = audience
    state.generated_content = ""
    state.solution_steps = []

    if exercise_type == "connect":
        edge = graph.get_edge(concept_a, concept_b)
        edge_type = edge.edge_type if edge else "related"
        state.edge_type = edge_type

        node_b = graph.get_node(concept_b)
        result = await asyncio.to_thread(
            generate_bridge_question,
            concept_a,
            concept_b,
            edge_type,
            node_a.description if node_a else "",
            node_b.description if node_b else "",
            topic_material,
        )
        if result.error:
            return HTMLResponse(
                '<p class="nothing-due">Failed to generate exercise. Check LLM settings.</p>'
            )
        state.generated_content = result.question

        return TEMPLATES.TemplateResponse(
            request=request,
            name="learn_exercise.html",
            context={
                "exercise_type": exercise_type,
                "prompt": normalise_latex(result.question),
                "subtitle": f"Explain the connection between {concept_a} and {concept_b}",
                "placeholder": "Describe how these two concepts are related, and why that connection matters...",
            },
        )

    if exercise_type == "debug":
        domain_a = node_a.domain if node_a else "the source domain"
        result_text = await asyncio.to_thread(
            generate_wrong_transposition, concept_a, domain_a, domain_b, topic_material
        )
        if not result_text:
            return HTMLResponse(
                '<p class="nothing-due">Failed to generate exercise. Check LLM settings.</p>'
            )
        state.generated_content = result_text
        state.edge_type = domain_a

        return TEMPLATES.TemplateResponse(
            request=request,
            name="learn_exercise.html",
            context={
                "exercise_type": exercise_type,
                "prompt": normalise_latex(result_text),
                "subtitle": f"Something is wrong with this application of {concept_a} in {domain_b}",
                "placeholder": "Identify the error and explain what the correct application should be...",
            },
        )

    if exercise_type == "derive":
        source_text = node_a.description if node_a and node_a.description else concept_a
        result = await asyncio.to_thread(
            generate_scaffolded_derivation, source_text, topic_material
        )
        if result.error or not result.prompt:
            return HTMLResponse(
                '<p class="nothing-due">Failed to generate exercise. Check LLM settings.</p>'
            )
        state.generated_content = result.prompt
        state.solution_steps = result.solution_steps

        blank_count = result.prompt.count("[...]")
        return TEMPLATES.TemplateResponse(
            request=request,
            name="learn_exercise.html",
            context={
                "exercise_type": exercise_type,
                "prompt": normalise_latex(result.prompt),
                "subtitle": f"Fill in the {blank_count} blank step{'s' if blank_count != 1 else ''} in this derivation",
                "placeholder": "Write your answers for the blank steps, one per line...",
            },
        )

    if exercise_type == "teach":
        return TEMPLATES.TemplateResponse(
            request=request,
            name="learn_exercise.html",
            context={
                "exercise_type": exercise_type,
                "prompt": f"Explain {concept_a} to {audience}.",
                "subtitle": f"Teach-it-back: explain {concept_a} as if speaking to {audience}",
                "placeholder": f"Write your explanation of {concept_a} for {audience}...",
            },
        )

    return HTMLResponse('<p class="nothing-due">Unknown exercise type.</p>')


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

    if exercise_type == "connect":
        result = await asyncio.to_thread(
            evaluate_relational_explanation,
            answer,
            state.concept_a,
            state.concept_b,
            state.edge_type,
        )
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
        problem_prompt = (
            f"The following is a plausible but incorrect application of "
            f"'{state.concept_a}' in the domain of '{state.domain_b}'. "
            f"Identify what is wrong and explain the correct application:\n\n"
            f"{state.generated_content}"
        )
        result = await asyncio.to_thread(grade_answer, problem_prompt, "", answer)
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
        solution_text = "\n".join(
            f"{idx}. {step}" for idx, step in enumerate(state.solution_steps)
        )
        result = await asyncio.to_thread(
            grade_answer, state.generated_content, solution_text, answer
        )
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
        graph = get_knowledge_graph()
        node = graph.get_node(state.concept_a)
        topic_material = node.description if node else ""
        result = await asyncio.to_thread(
            grade_teach_it_back,
            state.concept_a,
            state.audience,
            answer,
            topic_material,
        )
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
