"""LLM client for grading and exam generation.

Uses the OpenAI-compatible API, which works with Ollama (local) or any
hosted provider (DeepSeek, OpenRouter, etc.) by swapping LLM_BASE_URL,
LLM_API_KEY, and LLM_MODEL in the environment.

System prompts live in core/data/prompts/system/*.md; user message templates
in core/data/prompts/user/*.md; response schemas in core/data/schemas/*.json.
See core/data/README.md before editing any of these.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import openai
from PIL import Image
from pydantic import BaseModel, ValidationError

from core.constants import LLM_ROOT

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

from core.config import settings
from core.schemas.llm_schemas import (
    BridgeQuestion,
    ExamGradeResult,
    ExamProblem,
    GradeResult,
    LLMBackend,
    LLMModelType,
    RelationalGradeResult,
    ScaffoldedDerivation,
    TeachItBackResult,
    WrongTransposition,
    infer_model_type,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template and schema loading (file I/O at import time only)
# ---------------------------------------------------------------------------


def _load_prompt(path: str) -> str:
    return (LLM_ROOT / "prompts" / path).read_text()


def _load_schema(name: str) -> str:
    return (LLM_ROOT / "schemas" / f"{name}.json").read_text().strip()


def _load_rubric(name: str) -> str:
    path = LLM_ROOT / "prompts" / "rubrics" / f"{name}.md"
    return path.read_text() if path.exists() else ""


def _render(template: str, **kwargs: str) -> str:
    return template.format_map(defaultdict(str, **kwargs))


# System prompt templates
_SYS_GRADER = _load_prompt("system/grader.md")
_SYS_EXAMINER = _load_prompt("system/examiner.md")
_SYS_EXAM_GRADER = _load_prompt("system/exam_grader.md")
_SYS_TEACH_IT_BACK = _load_prompt("system/teach_it_back.md")
_SYS_BRIDGE_QUESTION = _load_prompt("system/bridge_question.md")
_SYS_WRONG_TRANSPOSITION = _load_prompt("system/wrong_transposition.md")
_SYS_SCAFFOLDED_DERIVATION = _load_prompt("system/scaffolded_derivation.md")
_SYS_RELATIONAL_GRADER = _load_prompt("system/relational_grader.md")

# User message templates
_USR_GRADER = _load_prompt("user/grader.md")
_USR_EXAMINER = _load_prompt("user/examiner.md")
_USR_EXAMINER_WEAK = _load_prompt("user/examiner_weak_section.md")
_USR_EXAM_TEXT = _load_prompt("user/exam_grader_text.md")
_USR_EXAM_IMAGE = _load_prompt("user/exam_grader_image.md")
_USR_TEACH_IT_BACK = _load_prompt("user/teach_it_back.md")
_USR_BRIDGE_QUESTION = _load_prompt("user/bridge_question.md")
_USR_WRONG_TRANSPOSITION = _load_prompt("user/wrong_transposition.md")
_USR_SCAFFOLDED_DERIVATION = _load_prompt("user/scaffolded_derivation.md")
_USR_RELATIONAL_GRADER = _load_prompt("user/relational_grader.md")

# Rubrics (injected into grader system prompts for model-agnostic consistency)
_RUB_GRADE = _load_rubric("grader")
_RUB_RELATIONAL = _load_rubric("relational_grader")
_RUB_TEACH_IT_BACK = _load_rubric("teach_it_back")
_RUB_EXAM_GRADE = _load_rubric("exam_grader")

# Response schemas (injected verbatim into system prompts)
_SCH_GRADE = _load_schema("grade_result")
_SCH_EXAM_PROBLEMS = _load_schema("exam_problems")
_SCH_EXAM_GRADE = _load_schema("exam_grade_result")
_SCH_TEACH_IT_BACK = _load_schema("teach_it_back_result")
_SCH_BRIDGE_QUESTION = _load_schema("bridge_question")
_SCH_WRONG_TRANSPOSITION = _load_schema("wrong_transposition")
_SCH_SCAFFOLDED_DERIVATION = _load_schema("scaffolded_derivation")
_SCH_RELATIONAL_GRADE = _load_schema("relational_grade_result")


class _ExamProblemsResponse(BaseModel):
    problems: list[ExamProblem]


# ---------------------------------------------------------------------------
# Image normalization
# ---------------------------------------------------------------------------


def normalize_image(image_bytes: bytes) -> tuple[bytes, str]:
    """Convert any supported image format (including HEIC/HEIF) to JPEG.

    Returns (jpeg_bytes, "image/jpeg"). Raises ValueError for unreadable input.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.format == "JPEG":
            return image_bytes, "image/jpeg"
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG")
        return buf.getvalue(), "image/jpeg"
    except Exception as exc:
        raise ValueError(f"Cannot decode image: {exc}") from exc


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------


class OpenAIBackend:
    """OpenAI-compatible backend - works unchanged with Ollama, DeepSeek, etc."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._model = model or settings.llm_model
        self._model_type = infer_model_type(self._model)
        logger.info("llm_backend model=%s type=%s", self._model, self._model_type.name)
        self._client = openai.OpenAI(
            base_url=base_url or settings.llm_base_url,
            api_key=api_key or settings.llm_api_key,
        )

    def chat(self, system: str, user: str, schema: BaseModel = None) -> str:
        if self._model_type == LLMModelType.REASONING:
            return self._chat_reasoning(system, user, schema)
        return self._chat_standard(system, user, schema)

    def _chat_standard(self, system: str, user: str, schema: BaseModel = None):
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if not schema:
            response_format = {"type": "json_object"}
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            }
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            response_format=response_format,
        )
        return resp.choices[0].message.content or ""

    # FLAG
    def _chat_reasoning(self, system: str, user: str, schema: BaseModel = None):
        # Since R1 de-prioritizes system prompts we'll fold the two together.
        combined = f"{system}\n\n{user}" if system else user
        messages = [{"role": "user", "content": combined}]
        if not schema:
            response_format = {"type": "json_object"}
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            }
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            response_format=response_format,
        )
        return resp.choices[0].message.content or ""

    def chat_with_image(
        self,
        system: str,
        user: str,
        image_bytes: bytes,
        media_type: str = "image/jpeg",
    ) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{b64}"},
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""


_backend: LLMBackend = OpenAIBackend()


@contextlib.contextmanager
def override_backend(backend: LLMBackend):  # type: ignore[return]
    """Swap the module-level backend for the duration of a with-block (for tests)."""
    global _backend  # pylint: disable=global-statement
    original = _backend
    _backend = backend
    try:
        yield backend
    finally:
        _backend = original


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _material_block(topic_material: str) -> str:
    return (
        f"\n\nRelevant background material:\n{topic_material}" if topic_material else ""
    )


_CONSISTENCY_THRESHOLD = 0.5
_CONSISTENCY_MAX_DRIFT = 0.2


def _timed_chat(fn_name: str, system: str, user: str, schema=None) -> str:
    start = time.perf_counter()
    exc_type = None
    try:
        return _backend.chat(system, user, schema)
    except Exception as exc:
        exc_type = type(exc).__name__
        raise
    finally:
        elapsed = round((time.perf_counter() - start) * 1000)
        logger.info("llm_call fn=%s latency_ms=%s error=%s", fn_name, elapsed, exc_type)


def _timed_chat_image(
    fn_name: str,
    system: str,
    user: str,
    image_bytes: bytes,
    media_type: str = "image/jpeg",
) -> str:
    start = time.perf_counter()
    exc_type = None
    try:
        return _backend.chat_with_image(system, user, image_bytes, media_type)
    except Exception as exc:
        exc_type = type(exc).__name__
        raise
    finally:
        elapsed = round((time.perf_counter() - start) * 1000)
        logger.info("llm_call fn=%s latency_ms=%s error=%s", fn_name, elapsed, exc_type)


def _consistent_grade(
    fn_name: str,
    system: str,
    user: str,
    parse: Callable[[str], Any],
    schema: BaseModel = None,
) -> Any:
    """Grade once; re-grade borderline results and take the lower on disagreement.

    If the two scores differ by more than _CONSISTENCY_MAX_DRIFT, logs a warning
    and returns the stricter result. This keeps grades stable across model runs.
    """
    result = parse(_timed_chat(fn_name, system, user, schema))
    score = getattr(result, "score", None)
    if score is not None and score < _CONSISTENCY_THRESHOLD:
        result2 = parse(_timed_chat(fn_name, system, user, schema))
        score2 = getattr(result2, "score", None)
        if score2 is not None and abs(score - score2) > _CONSISTENCY_MAX_DRIFT:
            logger.warning(
                "grading inconsistency detected: %.2f vs %.2f - using lower score",
                score,
                score2,
            )
            return result if score <= score2 else result2
    return result


def _problems_block(exam_problems: list[ExamProblem]) -> str:
    return "\n\n".join(
        f"Problem {p.number}:\n{p.prompt}\n\nSolution:\n{p.solution}"
        for p in exam_problems
    )


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def grade_answer(
    problem_prompt: str,
    solution_steps: str,
    user_answer: str,
    topic_material: str = "",
) -> GradeResult:
    """Grade a single free-text practice answer."""
    system = _render(
        _SYS_GRADER,
        schema=_SCH_GRADE,
        rubric=_RUB_GRADE,
        topic_material=_material_block(topic_material),
    )
    user = _render(
        _USR_GRADER,
        problem_prompt=problem_prompt,
        solution_steps=solution_steps,
        user_answer=user_answer,
    )

    def _parse(raw: str) -> GradeResult:
        return GradeResult.model_validate(json.loads(raw))

    try:
        return _consistent_grade("grade_answer", system, user, _parse, GradeResult)
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("grade_answer failed: %s", type(exc).__name__)
        return GradeResult(
            correct=False,
            score=0.0,
            feedback="Grading failed - please try again.",
            model_solution="",
            error=str(exc),
        )


def generate_exam(
    category: str,
    n_questions: int,
    weak_topics: list[str],
    topic_material: str = "",
) -> list[ExamProblem]:
    """Generate exam problems for a category, weighted toward weak topics."""
    system = _render(
        _SYS_EXAMINER,
        schema=_SCH_EXAM_PROBLEMS,
        topic_material=_material_block(topic_material),
    )
    weak_section = ""
    if weak_topics:
        topics_list = "\n".join(f"- {t}" for t in weak_topics)
        weak_section = "\n" + _render(_USR_EXAMINER_WEAK, weak_topics_list=topics_list)
    user = _render(
        _USR_EXAMINER,
        category=category,
        n_questions=str(n_questions),
        weak_section=weak_section,
    )
    try:
        raw_output = _timed_chat("generate_exam", system, user, _ExamProblemsResponse)
        parsed = json.loads(raw_output)

        if isinstance(parsed, dict) and "problems" in parsed:
            raw_items = parsed["problems"]
            if not isinstance(raw_items, list):
                logger.warning(
                    "generate_exam: 'problems' key is not a list; got %s",
                    type(raw_items).__name__,
                )
                raw_items = [raw_items]
        elif isinstance(parsed, list):
            logger.warning(
                'generate_exam: LLM returned a bare array instead of {"problems": [...]}'
            )
            raw_items = parsed
        else:
            logger.warning(
                "generate_exam: unexpected top-level type %s; treating as single item",
                type(parsed).__name__,
            )
            raw_items = [parsed]

        problems: list[ExamProblem] = []
        for item in raw_items:
            try:
                problems.append(ExamProblem.model_validate(item))
            except ValidationError as exc:
                logger.warning("generate_exam: skipping malformed item: %s", exc)
        return problems
    except (openai.OpenAIError, json.JSONDecodeError) as exc:
        logger.error("generate_exam failed: %s", type(exc).__name__)
        return []


def _exam_grader_system(topic_material: str) -> str:
    return _render(
        _SYS_EXAM_GRADER,
        schema=_SCH_EXAM_GRADE,
        rubric=_RUB_EXAM_GRADE,
        topic_material=_material_block(topic_material),
    )


def grade_from_text(
    exam_problems: list[ExamProblem],
    answer_text: str,
    topic_material: str = "",
) -> ExamGradeResult:
    """Grade a digitally-submitted exam given extracted answer text."""
    system = _exam_grader_system(topic_material)
    user = _render(
        _USR_EXAM_TEXT,
        problems_block=_problems_block(exam_problems),
        answer_text=answer_text,
    )
    try:
        return ExamGradeResult.model_validate(
            json.loads(_timed_chat("grade_from_text", system, user, ExamGradeResult))
        )
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("grade_from_text failed: %s", type(exc).__name__)
        return ExamGradeResult(
            error=str(exc), summary="Grading failed - please try again."
        )


def grade_from_image(
    exam_problems: list[ExamProblem],
    image_bytes: bytes,
    topic_material: str = "",
) -> ExamGradeResult:
    """Grade a photographed/scanned exam using the model's vision capability."""
    system = _exam_grader_system(topic_material)
    user = _render(_USR_EXAM_IMAGE, problems_block=_problems_block(exam_problems))
    try:
        normalized_bytes, media_type = normalize_image(image_bytes)
        return ExamGradeResult.model_validate(
            json.loads(
                _timed_chat_image(
                    "grade_from_image", system, user, normalized_bytes, media_type
                )
            )
        )
    except (
        openai.OpenAIError,
        json.JSONDecodeError,
        ValidationError,
        ValueError,
    ) as exc:
        logger.error("grade_from_image failed: %s", type(exc).__name__)
        return ExamGradeResult(
            error=str(exc), summary="Grading failed - please try again."
        )


def grade_teach_it_back(
    concept: str,
    audience: str,
    user_explanation: str,
    topic_material: str = "",
) -> TeachItBackResult:
    """Grade a teach-it-back exercise: how well did the user explain concept to audience."""
    system = _render(
        _SYS_TEACH_IT_BACK,
        schema=_SCH_TEACH_IT_BACK,
        rubric=_RUB_TEACH_IT_BACK,
        topic_material=_material_block(topic_material),
    )
    user = _render(
        _USR_TEACH_IT_BACK,
        concept=concept,
        audience=audience,
        user_explanation=user_explanation,
    )

    def _parse(raw: str) -> TeachItBackResult:
        return TeachItBackResult.model_validate(json.loads(raw))

    try:
        return _consistent_grade(
            "grade_teach_it_back", system, user, _parse, TeachItBackResult
        )
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("grade_teach_it_back failed: %s", type(exc).__name__)
        return TeachItBackResult(
            score=0.0, feedback="Grading failed - please try again.", error=str(exc)
        )


def generate_bridge_question(
    node_a_name: str,
    node_b_name: str,
    edge_type: str,
    node_a_description: str = "",
    node_b_description: str = "",
    topic_material: str = "",
) -> BridgeQuestion:
    """Generate a question that requires understanding the edge between two concepts."""
    system = _render(
        _SYS_BRIDGE_QUESTION,
        schema=_SCH_BRIDGE_QUESTION,
        topic_material=_material_block(topic_material),
    )
    user = _render(
        _USR_BRIDGE_QUESTION,
        node_a_name=node_a_name,
        node_b_name=node_b_name,
        edge_type=edge_type,
        node_a_description=node_a_description,
        node_b_description=node_b_description,
    )
    try:
        return BridgeQuestion.model_validate(
            json.loads(_timed_chat("generate_bridge_question", system, user))
        )
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("generate_bridge_question failed: %s", type(exc).__name__)
        return BridgeQuestion(
            question="",
            requires_edge=False,
            edge_type=edge_type,
            error=str(exc),
        )


def generate_wrong_transposition(
    concept: str,
    domain_a: str,
    domain_b: str,
    topic_material: str = "",
) -> str:
    """Generate a plausible-but-wrong application of concept in domain_b.

    Returns the transposition text, or empty string on failure.
    """
    system = _render(
        _SYS_WRONG_TRANSPOSITION,
        schema=_SCH_WRONG_TRANSPOSITION,
        topic_material=_material_block(topic_material),
    )
    user = _render(
        _USR_WRONG_TRANSPOSITION,
        concept=concept,
        domain_a=domain_a,
        domain_b=domain_b,
    )
    try:
        result = WrongTransposition.model_validate(
            json.loads(_timed_chat("generate_wrong_transposition", system, user))
        )
        return result.text
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("generate_wrong_transposition failed: %s", type(exc).__name__)
        return ""


def generate_scaffolded_derivation(
    derivation_text: str,
    topic_material: str = "",
) -> ScaffoldedDerivation:
    """Identify load-bearing steps and return a fill-in-the-blank derivation."""
    system = _render(
        _SYS_SCAFFOLDED_DERIVATION,
        schema=_SCH_SCAFFOLDED_DERIVATION,
        topic_material=_material_block(topic_material),
    )
    user = _render(_USR_SCAFFOLDED_DERIVATION, derivation_text=derivation_text)
    try:
        return ScaffoldedDerivation.model_validate(
            json.loads(_timed_chat("generate_scaffolded_derivation", system, user))
        )
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("generate_scaffolded_derivation failed: %s", type(exc).__name__)
        return ScaffoldedDerivation(prompt="", error=str(exc))


def evaluate_relational_explanation(
    user_text: str,
    node_a: str,
    node_b: str,
    edge_type: str,
    topic_material: str = "",
) -> RelationalGradeResult:
    """Grade a free-form explanation for relational understanding between two concepts."""
    system = _render(
        _SYS_RELATIONAL_GRADER,
        schema=_SCH_RELATIONAL_GRADE,
        rubric=_RUB_RELATIONAL,
        topic_material=_material_block(topic_material),
    )
    user = _render(
        _USR_RELATIONAL_GRADER,
        node_a=node_a,
        node_b=node_b,
        edge_type=edge_type,
        user_text=user_text,
    )

    def _parse(raw: str) -> RelationalGradeResult:
        return RelationalGradeResult.model_validate(json.loads(raw))

    try:
        return _consistent_grade(
            "evaluate_relational_explanation", system, user, _parse, RelationalGradeResult
        )
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("evaluate_relational_explanation failed: %s", type(exc).__name__)
        return RelationalGradeResult(
            correct=False,
            score=0.0,
            feedback="Grading failed - please try again.",
            error=str(exc),
        )
