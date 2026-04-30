"""Tests for core/llm.py - all LLM calls are mocked at the backend level."""

from __future__ import annotations

import io
import json
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-abc123")
os.environ.setdefault("ALLOWED_USER_ID", "99999")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:11434/v1")
os.environ.setdefault("LLM_API_KEY", "ollama")
os.environ.setdefault("LLM_MODEL", "qwen2.5-vl:32b")

import base64
from unittest.mock import MagicMock, patch

import openai
import pytest
from PIL import Image

from core.llm import (OpenAIBackend, evaluate_relational_explanation,
                      generate_bridge_question, generate_exam,
                      generate_scaffolded_derivation,
                      generate_wrong_transposition, grade_answer,
                      grade_from_image, grade_from_text, grade_teach_it_back,
                      normalize_image, override_backend)
from core.schemas.llm_schemas import (BridgeQuestion, ExamGradeResult,
                                      ExamProblem, GradeResult,
                                      RelationalGradeResult,
                                      ScaffoldedDerivation, TeachItBackResult)
from tests.conftest import ErrorBackend, MockBackend

# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------


def _make_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(buf, format="JPEG")
    return buf.getvalue()


def _make_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _make_completion(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    completion = MagicMock()
    completion.choices = [choice]
    return completion


# ---------------------------------------------------------------------------
# normalize_image
# ---------------------------------------------------------------------------


class TestNormalizeImage:
    def test_jpeg_passthrough(self):
        jpeg_bytes = _make_jpeg()
        result_bytes, media_type = normalize_image(jpeg_bytes)
        assert media_type == "image/jpeg"
        assert result_bytes == jpeg_bytes

    def test_png_converted_to_jpeg(self):
        png_bytes = _make_png()
        result_bytes, media_type = normalize_image(png_bytes)
        assert media_type == "image/jpeg"
        assert result_bytes != png_bytes
        img = Image.open(io.BytesIO(result_bytes))
        assert img.format == "JPEG"

    def test_invalid_bytes_raises_value_error(self):
        with pytest.raises(ValueError):
            normalize_image(b"this is not an image")


# ---------------------------------------------------------------------------
# OpenAIBackend
# ---------------------------------------------------------------------------


class TestOpenAIBackend:
    def test_chat_with_image_encodes_base64_in_request(self):
        backend = OpenAIBackend()
        mock_create = MagicMock(return_value=_make_completion('{"ok": true}'))
        with patch.object(backend._client.chat.completions, "create", mock_create):
            backend.chat_with_image("sys", "user msg", b"raw-image-bytes")
        messages = mock_create.call_args.kwargs["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        image_block = next(
            b for b in user_msg["content"] if b.get("type") == "image_url"
        )
        url = image_block["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")
        assert base64.b64decode(url.split(",", 1)[1]) == b"raw-image-bytes"


# ---------------------------------------------------------------------------
# grade_answer
# ---------------------------------------------------------------------------


class TestGradeAnswer:
    def test_correct_answer(self):
        payload = json.dumps(
            {
                "correct": True,
                "score": 1.0,
                "feedback": "Great",
                "model_solution": "x=4",
            }
        )
        mock = MockBackend(payload)
        with override_backend(mock):
            result = grade_answer("What is 2+2?", "2+2=4", "4")
        assert isinstance(result, GradeResult)
        assert result.correct is True
        assert result.score == 1.0
        assert result.feedback == "Great"
        assert result.model_solution == "x=4"
        assert result.error == ""

    def test_wrong_answer(self):
        payload = json.dumps(
            {
                "correct": False,
                "score": 0.0,
                "feedback": "Wrong",
                "model_solution": "x=4",
            }
        )
        mock = MockBackend(payload)
        with override_backend(mock):
            result = grade_answer("What is 2+2?", "2+2=4", "5")
        assert result.correct is False
        assert result.score == 0.0

    def test_partial_credit(self):
        payload = json.dumps(
            {
                "correct": False,
                "score": 0.5,
                "feedback": "Partially right",
                "model_solution": "...",
            }
        )
        mock = MockBackend(payload)
        with override_backend(mock):
            result = grade_answer("Derive X", "steps...", "half answer")
        assert result.score == 0.5

    def test_system_prompt_contains_grader_role(self):
        payload = json.dumps(
            {"correct": True, "score": 1.0, "feedback": "ok", "model_solution": "ok"}
        )
        mock = MockBackend(payload)
        with override_backend(mock):
            grade_answer("q", "sol", "ans")
        assert "grader" in mock.last_system.lower()

    def test_problem_and_answer_in_user_message(self):
        payload = json.dumps(
            {"correct": True, "score": 1.0, "feedback": "ok", "model_solution": "ok"}
        )
        mock = MockBackend(payload)
        with override_backend(mock):
            grade_answer(
                "What is entropy?", "H = -sum(p log p)", "it measures uncertainty"
            )
        assert "What is entropy?" in mock.last_user
        assert "H = -sum(p log p)" in mock.last_user
        assert "it measures uncertainty" in mock.last_user

    def test_topic_material_injected_into_system_prompt(self):
        payload = json.dumps(
            {"correct": True, "score": 1.0, "feedback": "ok", "model_solution": "ok"}
        )
        mock = MockBackend(payload)
        with override_backend(mock):
            grade_answer("q", "sol", "ans", topic_material="Shannon entropy context")
        assert "Shannon entropy context" in mock.last_system

    def test_json_parse_failure_returns_graceful_error(self):
        mock = MockBackend("not json at all")
        with override_backend(mock):
            result = grade_answer("q", "sol", "ans")
        assert isinstance(result, GradeResult)
        assert result.correct is False
        assert result.error != ""
        assert "failed" in result.feedback.lower()

    def test_openai_error_returns_graceful_error(self):
        with override_backend(ErrorBackend(openai.OpenAIError("timeout"))):
            result = grade_answer("q", "sol", "ans")
        assert result.correct is False
        assert result.error != ""


# ---------------------------------------------------------------------------
# generate_exam
# ---------------------------------------------------------------------------


class TestGenerateExam:
    def test_returns_exam_problems(self):
        payload = json.dumps(
            [
                {"number": 1, "prompt": "Prove X", "solution": "Because Y"},
                {"number": 2, "prompt": "Solve Z", "solution": "Z=3"},
            ]
        )
        mock = MockBackend(payload)
        with override_backend(mock):
            problems = generate_exam("Linear Algebra", 2, [])
        assert len(problems) == 2
        assert isinstance(problems[0], ExamProblem)
        assert problems[0].number == 1
        assert problems[1].prompt == "Solve Z"

    def test_system_prompt_contains_examiner_role(self):
        payload = json.dumps([{"number": 1, "prompt": "q", "solution": "s"}])
        mock = MockBackend(payload)
        with override_backend(mock):
            generate_exam("Math", 1, [])
        assert "examiner" in mock.last_system.lower()

    def test_weak_topics_included_in_user_message(self):
        payload = json.dumps([{"number": 1, "prompt": "q", "solution": "s"}])
        mock = MockBackend(payload)
        with override_backend(mock):
            generate_exam("RL", 1, ["Q-learning", "policy gradient"])
        assert "Q-learning" in mock.last_user
        assert "policy gradient" in mock.last_user

    def test_no_weak_section_when_topics_empty(self):
        payload = json.dumps([{"number": 1, "prompt": "q", "solution": "s"}])
        mock = MockBackend(payload)
        with override_backend(mock):
            generate_exam("Math", 1, [])
        assert "struggled" not in mock.last_user

    def test_wrapped_json_object_unwrapped(self):
        payload = json.dumps(
            {"problems": [{"number": 1, "prompt": "p", "solution": "s"}]}
        )
        mock = MockBackend(payload)
        with override_backend(mock):
            problems = generate_exam("Math", 1, [])
        assert len(problems) == 1

    def test_openai_error_returns_empty_list(self):
        with override_backend(ErrorBackend(openai.OpenAIError("err"))):
            problems = generate_exam("Math", 3, [])
        assert problems == []


# ---------------------------------------------------------------------------
# grade_from_text
# ---------------------------------------------------------------------------


class TestGradeFromText:
    def _problems(self) -> list[ExamProblem]:
        return [ExamProblem(number=1, prompt="What is 1+1?", solution="2")]

    def test_returns_exam_grade_result(self):
        payload = json.dumps(
            {
                "problems": [{"number": 1, "score": 1.0, "feedback": "Correct"}],
                "total_score": 1.0,
                "summary": "Excellent",
            }
        )
        mock = MockBackend(payload)
        with override_backend(mock):
            result = grade_from_text(self._problems(), "1. 2")
        assert isinstance(result, ExamGradeResult)
        assert result.total_score == 1.0
        assert result.summary == "Excellent"
        assert len(result.problems) == 1

    def test_answer_text_in_user_message(self):
        payload = json.dumps(
            {
                "problems": [{"number": 1, "score": 1.0, "feedback": "ok"}],
                "total_score": 1.0,
                "summary": "Good",
            }
        )
        mock = MockBackend(payload)
        with override_backend(mock):
            grade_from_text(self._problems(), "my answer here")
        assert "my answer here" in mock.last_user

    def test_openai_error_returns_graceful_error(self):
        with override_backend(ErrorBackend(openai.OpenAIError("err"))):
            result = grade_from_text(self._problems(), "some answer")
        assert result.error != ""
        assert "failed" in result.summary.lower()


# ---------------------------------------------------------------------------
# grade_from_image
# ---------------------------------------------------------------------------


class TestGradeFromImage:
    def _problems(self) -> list[ExamProblem]:
        return [ExamProblem(number=1, prompt="What is 1+1?", solution="2")]

    def _ok_payload(self) -> str:
        return json.dumps(
            {
                "problems": [{"number": 1, "score": 1.0, "feedback": "ok"}],
                "total_score": 1.0,
                "summary": "Good",
            }
        )

    def test_returns_grade_result_with_valid_jpeg(self):
        mock = MockBackend(self._ok_payload())
        with override_backend(mock):
            result = grade_from_image(self._problems(), _make_jpeg())
        assert isinstance(result, ExamGradeResult)
        assert result.total_score == 1.0

    def test_png_normalized_to_jpeg_before_backend(self):
        mock = MockBackend(self._ok_payload())
        with override_backend(mock):
            grade_from_image(self._problems(), _make_png())
        assert mock.last_media_type == "image/jpeg"
        assert mock.last_image_bytes is not None

    def test_invalid_image_returns_graceful_error(self):
        mock = MockBackend("{}")
        with override_backend(mock):
            result = grade_from_image(self._problems(), b"not-an-image")
        assert result.error != ""

    def test_openai_error_returns_graceful_error(self):
        with override_backend(ErrorBackend(openai.OpenAIError("err"))):
            result = grade_from_image(self._problems(), _make_jpeg())
        assert result.error != ""


# ---------------------------------------------------------------------------
# grade_teach_it_back
# ---------------------------------------------------------------------------


class TestGradeTeachItBack:
    def _good_payload(self) -> str:
        return json.dumps(
            {
                "score": 0.9,
                "feedback": "Clear and accurate explanation.",
                "missing_concepts": [],
                "analogy_issues": [],
                "model_answer": "Gradient descent minimises the loss by iteratively moving parameters in the direction of steepest decrease.",
            }
        )

    def test_returns_teach_it_back_result(self):
        mock = MockBackend(self._good_payload())
        with override_backend(mock):
            result = grade_teach_it_back(
                "gradient descent",
                "high school student",
                "It's like rolling a ball downhill.",
            )
        assert isinstance(result, TeachItBackResult)
        assert result.score == 0.9
        assert result.feedback == "Clear and accurate explanation."
        assert result.missing_concepts == []
        assert result.analogy_issues == []
        assert result.error == ""

    def test_model_answer_populated(self):
        mock = MockBackend(self._good_payload())
        with override_backend(mock):
            result = grade_teach_it_back("gradient descent", "high school student", "explanation")
        assert result.model_answer != ""

    def test_model_answer_defaults_to_empty_when_absent(self):
        payload = json.dumps({"score": 0.8, "feedback": "ok", "missing_concepts": [], "analogy_issues": []})
        mock = MockBackend(payload)
        with override_backend(mock):
            result = grade_teach_it_back("entropy", "undergrad", "explanation")
        assert result.model_answer == ""

    def test_missing_concepts_populated(self):
        payload = json.dumps(
            {
                "score": 0.5,
                "feedback": "Missed key ideas.",
                "missing_concepts": ["learning rate", "convergence"],
                "analogy_issues": [],
            }
        )
        mock = MockBackend(payload)
        with override_backend(mock):
            result = grade_teach_it_back(
                "gradient descent", "undergrad", "You subtract the gradient."
            )
        assert result.missing_concepts == ["learning rate", "convergence"]

    def test_analogy_issues_populated(self):
        payload = json.dumps(
            {
                "score": 0.6,
                "feedback": "Analogy breaks down.",
                "missing_concepts": [],
                "analogy_issues": [
                    "Rolling-ball analogy implies a unique minimum, which doesn't hold for non-convex losses."
                ],
            }
        )
        mock = MockBackend(payload)
        with override_backend(mock):
            result = grade_teach_it_back(
                "gradient descent",
                "ML engineer",
                "Like rolling a ball to the lowest point.",
            )
        assert len(result.analogy_issues) == 1
        assert "non-convex" in result.analogy_issues[0]

    def test_system_prompt_contains_educator_role(self):
        mock = MockBackend(self._good_payload())
        with override_backend(mock):
            grade_teach_it_back(
                "backpropagation", "high school student", "explanation text"
            )
        assert "educator" in mock.last_system.lower()

    def test_concept_and_audience_in_user_message(self):
        mock = MockBackend(self._good_payload())
        with override_backend(mock):
            grade_teach_it_back("KL divergence", "biology PhD", "explanation text")
        assert "KL divergence" in mock.last_user
        assert "biology PhD" in mock.last_user

    def test_topic_material_injected_into_system_prompt(self):
        mock = MockBackend(self._good_payload())
        with override_backend(mock):
            grade_teach_it_back(
                "entropy",
                "undergrad",
                "explanation",
                topic_material="Shannon 1948 paper context",
            )
        assert "Shannon 1948 paper context" in mock.last_system

    def test_analogy_issues_bare_string_coerced_to_list(self):
        payload = json.dumps({
            "score": 0.6,
            "feedback": "ok",
            "missing_concepts": [],
            "analogy_issues": "The analogy provided is misleading between distributions.",
        })
        mock = MockBackend(payload)
        with override_backend(mock):
            result = grade_teach_it_back("entropy", "undergrad", "explanation")
        assert result.analogy_issues == ["The analogy provided is misleading between distributions."]

    def test_missing_concepts_bare_string_coerced_to_list(self):
        payload = json.dumps({
            "score": 0.5,
            "feedback": "ok",
            "missing_concepts": "convergence criterion",
            "analogy_issues": [],
        })
        mock = MockBackend(payload)
        with override_backend(mock):
            result = grade_teach_it_back("gradient descent", "undergrad", "explanation")
        assert result.missing_concepts == ["convergence criterion"]

    def test_json_parse_failure_returns_graceful_error(self):
        mock = MockBackend("not valid json")
        with override_backend(mock):
            result = grade_teach_it_back("entropy", "undergrad", "explanation")
        assert isinstance(result, TeachItBackResult)
        assert result.score == 0.0
        assert result.error != ""
        assert "failed" in result.feedback.lower()

    def test_openai_error_returns_graceful_error(self):
        with override_backend(ErrorBackend(openai.OpenAIError("timeout"))):
            result = grade_teach_it_back("entropy", "undergrad", "explanation")
        assert result.score == 0.0
        assert result.error != ""


# ---------------------------------------------------------------------------
# OpenAIBackend provider configuration
# ---------------------------------------------------------------------------

_PROVIDER_CONFIGS = [
    pytest.param("https://api.openai.com/v1", "sk-fake-openai", "gpt-4o", id="openai"),
    pytest.param(
        "https://api.anthropic.com/v1", "sk-ant-fake", "claude-opus-4-7", id="anthropic"
    ),
    pytest.param(
        "https://api.deepseek.com/v1",
        "sk-fake-deepseek",
        "deepseek-chat",
        id="deepseek",
    ),
    pytest.param(
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "fake-gemini-key",
        "gemini-2.0-flash",
        id="gemini",
    ),
    pytest.param(
        "https://openrouter.ai/api/v1",
        "sk-or-fake",
        "meta-llama/llama-3.3-70b-instruct",
        id="openrouter",
    ),
    pytest.param(
        "https://api.groq.com/openai/v1",
        "gsk_fake",
        "llama-3.3-70b-versatile",
        id="groq",
    ),
    pytest.param(
        "https://api.mistral.ai/v1",
        "fake-mistral-key",
        "mistral-large-latest",
        id="mistral",
    ),
]


class TestOpenAIBackendConfiguration:
    @pytest.mark.parametrize("base_url,api_key,model", _PROVIDER_CONFIGS)
    def test_constructor_passes_base_url_and_api_key(self, base_url, api_key, model):
        with patch("core.llm.openai.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = (
                _make_completion("{}")
            )
            OpenAIBackend(base_url=base_url, api_key=api_key, model=model)
        mock_cls.assert_called_once_with(base_url=base_url, api_key=api_key)

    @pytest.mark.parametrize("base_url,api_key,model", _PROVIDER_CONFIGS)
    def test_model_name_sent_to_create(self, base_url, api_key, model):
        backend = OpenAIBackend(base_url=base_url, api_key=api_key, model=model)
        mock_create = MagicMock(return_value=_make_completion('{"ok": true}'))
        with patch.object(backend._client.chat.completions, "create", mock_create):
            backend.chat("sys", "user")
        assert mock_create.call_args.kwargs["model"] == model


# ---------------------------------------------------------------------------
# generate_bridge_question
# ---------------------------------------------------------------------------


class TestGenerateBridgeQuestion:
    def _payload(self, question: str = "Why does X require Y?") -> str:
        return json.dumps(
            {"question": question, "requires_edge": True, "edge_type": "related"}
        )

    def test_returns_bridge_question_instance(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            result = generate_bridge_question("Attention Mechanism", "Transformer", "related")
        assert isinstance(result, BridgeQuestion)

    def test_question_text_populated(self):
        mock = MockBackend(self._payload("How does attention enable the Transformer?"))
        with override_backend(mock):
            result = generate_bridge_question("Attention Mechanism", "Transformer", "related")
        assert result.question == "How does attention enable the Transformer?"
        assert result.requires_edge is True
        assert result.error == ""

    def test_node_names_in_user_message(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            generate_bridge_question("Concept Alpha", "Concept Beta", "precedes")
        assert "Concept Alpha" in mock.last_user
        assert "Concept Beta" in mock.last_user
        assert "precedes" in mock.last_user

    def test_node_descriptions_in_user_message_when_provided(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            generate_bridge_question(
                "Alpha",
                "Beta",
                "related",
                node_a_description="desc of alpha",
                node_b_description="desc of beta",
            )
        assert "desc of alpha" in mock.last_user
        assert "desc of beta" in mock.last_user

    def test_topic_material_injected_into_system_prompt(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            generate_bridge_question("A", "B", "related", topic_material="extra context")
        assert "extra context" in mock.last_system

    def test_system_prompt_references_bridge_or_relational(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            generate_bridge_question("A", "B", "related")
        lower_sys = mock.last_system.lower()
        assert "bridge" in lower_sys or "relational" in lower_sys or "connection" in lower_sys

    def test_invalid_json_returns_error_result(self):
        mock = MockBackend("not json")
        with override_backend(mock):
            result = generate_bridge_question("A", "B", "related")
        assert result.error != ""
        assert result.question == ""

    def test_openai_error_returns_error_result(self):
        error_backend = ErrorBackend(openai.APIConnectionError(request=MagicMock()))
        with override_backend(error_backend):
            result = generate_bridge_question("A", "B", "related")
        assert result.error != ""

    def test_edge_type_preserved_on_error(self):
        mock = MockBackend("bad json")
        with override_backend(mock):
            result = generate_bridge_question("A", "B", "precedes")
        assert result.edge_type == "precedes"


# ---------------------------------------------------------------------------
# generate_wrong_transposition
# ---------------------------------------------------------------------------


class TestGenerateWrongTransposition:
    def _payload(self, text: str = "Wrong application here.") -> str:
        return json.dumps({"text": text})

    def test_returns_string(self):
        mock = MockBackend(self._payload("Plausible but wrong."))
        with override_backend(mock):
            result = generate_wrong_transposition("entropy", "information theory", "thermodynamics")
        assert isinstance(result, str)
        assert result == "Plausible but wrong."

    def test_concept_and_domains_in_user_message(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            generate_wrong_transposition("attention", "NLP", "computer vision")
        assert "attention" in mock.last_user
        assert "NLP" in mock.last_user
        assert "computer vision" in mock.last_user

    def test_topic_material_injected_into_system_prompt(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            generate_wrong_transposition("concept", "domain A", "domain B", topic_material="extra")
        assert "extra" in mock.last_system

    def test_system_prompt_mentions_misconception(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            generate_wrong_transposition("concept", "domain A", "domain B")
        assert "misconception" in mock.last_system.lower() or "wrong" in mock.last_system.lower()

    def test_invalid_json_returns_empty_string(self):
        mock = MockBackend("not json")
        with override_backend(mock):
            result = generate_wrong_transposition("concept", "A", "B")
        assert result == ""

    def test_openai_error_returns_empty_string(self):
        error_backend = ErrorBackend(openai.APIConnectionError(request=MagicMock()))
        with override_backend(error_backend):
            result = generate_wrong_transposition("concept", "A", "B")
        assert result == ""


# ---------------------------------------------------------------------------
# generate_scaffolded_derivation
# ---------------------------------------------------------------------------


class TestGenerateScaffoldedDerivation:
    def _payload(self) -> str:
        return json.dumps(
            {
                "prompt": "Step 1. [...] Step 3.",
                "blank_indices": [1],
                "solution_steps": ["Step 1.", "Step 2.", "Step 3."],
            }
        )

    def test_returns_scaffolded_derivation_instance(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            result = generate_scaffolded_derivation("derivation text here")
        assert isinstance(result, ScaffoldedDerivation)

    def test_fields_populated(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            result = generate_scaffolded_derivation("derivation text here")
        assert "[...]" in result.prompt
        assert result.blank_indices == [1]
        assert len(result.solution_steps) == 3
        assert result.error == ""

    def test_derivation_text_in_user_message(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            generate_scaffolded_derivation("my derivation steps")
        assert "my derivation steps" in mock.last_user

    def test_topic_material_injected_into_system_prompt(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            generate_scaffolded_derivation("derivation", topic_material="background")
        assert "background" in mock.last_system

    def test_system_prompt_mentions_load_bearing_or_blanks(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            generate_scaffolded_derivation("some derivation")
        lower_sys = mock.last_system.lower()
        assert "load-bearing" in lower_sys or "blank" in lower_sys or "fill" in lower_sys

    def test_invalid_json_returns_error_result(self):
        mock = MockBackend("not json")
        with override_backend(mock):
            result = generate_scaffolded_derivation("derivation")
        assert result.error != ""
        assert result.prompt == ""

    def test_openai_error_returns_error_result(self):
        error_backend = ErrorBackend(openai.APIConnectionError(request=MagicMock()))
        with override_backend(error_backend):
            result = generate_scaffolded_derivation("derivation")
        assert result.error != ""


# ---------------------------------------------------------------------------
# evaluate_relational_explanation
# ---------------------------------------------------------------------------


class TestEvaluateRelationalExplanation:
    def _payload(
        self,
        correct: bool = True,
        score: float = 0.9,
        missing: list[str] | None = None,
        incorrect: list[str] | None = None,
        model_answer: str = "A strong answer would explain how A enables B by...",
    ) -> str:
        return json.dumps(
            {
                "correct": correct,
                "score": score,
                "feedback": "Good relational explanation.",
                "missing_relational_claims": missing or [],
                "incorrect_relational_claims": incorrect or [],
                "model_answer": model_answer,
            }
        )

    def test_returns_relational_grade_result_instance(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            result = evaluate_relational_explanation(
                "explanation text", "KL Divergence", "Encoder", "related"
            )
        assert isinstance(result, RelationalGradeResult)

    def test_correct_answer_fields(self):
        mock = MockBackend(self._payload(correct=True, score=1.0))
        with override_backend(mock):
            result = evaluate_relational_explanation("text", "A", "B", "related")
        assert result.correct is True
        assert result.score == 1.0
        assert result.error == ""

    def test_partial_credit_with_missing_claims(self):
        mock = MockBackend(
            self._payload(correct=False, score=0.5, missing=["asymmetry of penalty"])
        )
        with override_backend(mock):
            result = evaluate_relational_explanation("partial text", "A", "B", "related")
        assert result.score == 0.5
        assert "asymmetry of penalty" in result.missing_relational_claims

    def test_incorrect_relational_claims_captured(self):
        mock = MockBackend(
            self._payload(correct=False, score=0.2, incorrect=["wrong claim about edge"])
        )
        with override_backend(mock):
            result = evaluate_relational_explanation("text", "A", "B", "related")
        assert "wrong claim about edge" in result.incorrect_relational_claims

    def test_concept_names_and_edge_type_in_user_message(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            evaluate_relational_explanation(
                "student explanation", "Concept Alpha", "Concept Beta", "precedes"
            )
        assert "Concept Alpha" in mock.last_user
        assert "Concept Beta" in mock.last_user
        assert "precedes" in mock.last_user
        assert "student explanation" in mock.last_user

    def test_topic_material_injected_into_system_prompt(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            evaluate_relational_explanation("text", "A", "B", "related", topic_material="ctx")
        assert "ctx" in mock.last_system

    def test_system_prompt_stresses_relational_distinction(self):
        mock = MockBackend(self._payload())
        with override_backend(mock):
            evaluate_relational_explanation("text", "A", "B", "related")
        lower_sys = mock.last_system.lower()
        assert "relational" in lower_sys or "connection" in lower_sys or "relationship" in lower_sys

    def test_invalid_json_returns_error_result(self):
        mock = MockBackend("not json")
        with override_backend(mock):
            result = evaluate_relational_explanation("text", "A", "B", "related")
        assert result.error != ""
        assert result.correct is False

    def test_openai_error_returns_error_result(self):
        error_backend = ErrorBackend(openai.APIConnectionError(request=MagicMock()))
        with override_backend(error_backend):
            result = evaluate_relational_explanation("text", "A", "B", "related")
        assert result.error != ""

    def test_model_answer_populated(self):
        mock = MockBackend(self._payload(model_answer="A strong answer would explain X via Y."))
        with override_backend(mock):
            result = evaluate_relational_explanation("text", "A", "B", "related")
        assert result.model_answer == "A strong answer would explain X via Y."

    def test_model_answer_defaults_to_empty_when_absent(self):
        payload = json.dumps({
            "correct": True, "score": 1.0, "feedback": "ok",
            "missing_relational_claims": [], "incorrect_relational_claims": [],
        })
        mock = MockBackend(payload)
        with override_backend(mock):
            result = evaluate_relational_explanation("text", "A", "B", "related")
        assert result.model_answer == ""

    def test_missing_relational_claims_bare_string_coerced_to_list(self):
        payload = json.dumps({
            "correct": False, "score": 0.4, "feedback": "ok",
            "missing_relational_claims": "asymmetry of the penalty term",
            "incorrect_relational_claims": [],
        })
        mock = MockBackend(payload)
        with override_backend(mock):
            result = evaluate_relational_explanation("text", "A", "B", "related")
        assert result.missing_relational_claims == ["asymmetry of the penalty term"]

    def test_incorrect_relational_claims_bare_string_coerced_to_list(self):
        payload = json.dumps({
            "correct": False, "score": 0.3, "feedback": "ok",
            "missing_relational_claims": [],
            "incorrect_relational_claims": "the penalty is symmetric",
        })
        mock = MockBackend(payload)
        with override_backend(mock):
            result = evaluate_relational_explanation("text", "A", "B", "related")
        assert result.incorrect_relational_claims == ["the penalty is symmetric"]
