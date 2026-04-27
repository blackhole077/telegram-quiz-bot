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
from collections import defaultdict
from pathlib import Path

import openai
from PIL import Image
from pydantic import ValidationError

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

from core.config import settings
from core.llm_schemas import (
    ExamGradeResult,
    ExamProblem,
    GradeResult,
    LLMBackend,
    TeachItBackResult,
)

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"


# ---------------------------------------------------------------------------
# Template and schema loading (file I/O at import time only)
# ---------------------------------------------------------------------------

def _load_prompt(path: str) -> str:
    return (_DATA_DIR / "prompts" / path).read_text()


def _load_schema(name: str) -> str:
    return (_DATA_DIR / "schemas" / f"{name}.json").read_text().strip()


def _render(template: str, **kwargs: str) -> str:
    return template.format_map(defaultdict(str, **kwargs))


# System prompt templates
_SYS_GRADER = _load_prompt("system/grader.md")
_SYS_EXAMINER = _load_prompt("system/examiner.md")
_SYS_EXAM_GRADER = _load_prompt("system/exam_grader.md")
_SYS_TEACH_IT_BACK = _load_prompt("system/teach_it_back.md")

# User message templates
_USR_GRADER = _load_prompt("user/grader.md")
_USR_EXAMINER = _load_prompt("user/examiner.md")
_USR_EXAMINER_WEAK = _load_prompt("user/examiner_weak_section.md")
_USR_EXAM_TEXT = _load_prompt("user/exam_grader_text.md")
_USR_EXAM_IMAGE = _load_prompt("user/exam_grader_image.md")
_USR_TEACH_IT_BACK = _load_prompt("user/teach_it_back.md")

# Response schemas (injected verbatim into system prompts)
_SCH_GRADE = _load_schema("grade_result")
_SCH_EXAM_PROBLEMS = _load_schema("exam_problems")
_SCH_EXAM_GRADE = _load_schema("exam_grade_result")
_SCH_TEACH_IT_BACK = _load_schema("teach_it_back_result")


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
        self._client = openai.OpenAI(
            base_url=base_url or settings.llm_base_url,
            api_key=api_key or settings.llm_api_key,
        )

    def chat(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
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
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
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
    global _backend
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
    return f"\n\nRelevant background material:\n{topic_material}" if topic_material else ""


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
    system = _render(_SYS_GRADER, schema=_SCH_GRADE, topic_material=_material_block(topic_material))
    user = _render(_USR_GRADER, problem_prompt=problem_prompt, solution_steps=solution_steps, user_answer=user_answer)
    try:
        return GradeResult.model_validate(json.loads(_backend.chat(system, user)))
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("grade_answer failed: %s", exc)
        return GradeResult(correct=False, score=0.0, feedback="Grading failed - please try again.", model_solution="", error=str(exc))


def generate_exam(
    category: str,
    n_questions: int,
    weak_topics: list[str],
    topic_material: str = "",
) -> list[ExamProblem]:
    """Generate exam problems for a category, weighted toward weak topics."""
    system = _render(_SYS_EXAMINER, schema=_SCH_EXAM_PROBLEMS, topic_material=_material_block(topic_material))
    weak_section = ""
    if weak_topics:
        topics_list = "\n".join(f"- {t}" for t in weak_topics)
        weak_section = "\n" + _render(_USR_EXAMINER_WEAK, weak_topics_list=topics_list)
    user = _render(_USR_EXAMINER, category=category, n_questions=str(n_questions), weak_section=weak_section)
    try:
        parsed = json.loads(_backend.chat(system, user))
        items: list[dict] = parsed if isinstance(parsed, list) else parsed.get("problems", parsed.get("questions", []))
        return [ExamProblem.model_validate(item) for item in items]
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("generate_exam failed: %s", exc)
        return []


def _exam_grader_system(topic_material: str) -> str:
    return _render(_SYS_EXAM_GRADER, schema=_SCH_EXAM_GRADE, topic_material=_material_block(topic_material))


def grade_from_text(
    exam_problems: list[ExamProblem],
    answer_text: str,
    topic_material: str = "",
) -> ExamGradeResult:
    """Grade a digitally-submitted exam given extracted answer text."""
    system = _exam_grader_system(topic_material)
    user = _render(_USR_EXAM_TEXT, problems_block=_problems_block(exam_problems), answer_text=answer_text)
    try:
        return ExamGradeResult.model_validate(json.loads(_backend.chat(system, user)))
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("grade_from_text failed: %s", exc)
        return ExamGradeResult(error=str(exc), summary="Grading failed - please try again.")


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
            json.loads(_backend.chat_with_image(system, user, normalized_bytes, media_type))
        )
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        logger.error("grade_from_image failed: %s", exc)
        return ExamGradeResult(error=str(exc), summary="Grading failed - please try again.")


def grade_teach_it_back(
    concept: str,
    audience: str,
    user_explanation: str,
    topic_material: str = "",
) -> TeachItBackResult:
    """Grade a teach-it-back exercise: how well did the user explain concept to audience."""
    system = _render(_SYS_TEACH_IT_BACK, schema=_SCH_TEACH_IT_BACK, topic_material=_material_block(topic_material))
    user = _render(_USR_TEACH_IT_BACK, concept=concept, audience=audience, user_explanation=user_explanation)
    try:
        return TeachItBackResult.model_validate(json.loads(_backend.chat(system, user)))
    except (openai.OpenAIError, json.JSONDecodeError, ValidationError) as exc:
        logger.error("grade_teach_it_back failed: %s", exc)
        return TeachItBackResult(score=0.0, feedback="Grading failed - please try again.", error=str(exc))
