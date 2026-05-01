"""Tests for core.learn_service.LearnService.

LearnService owns all LLM calls and exercise state for the learn/exercise
flow. The router should only call service methods and render templates.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.learn_service import LearnService
from core.schemas.llm_schemas import (
    BridgeQuestion,
    GradeResult,
    RelationalGradeResult,
    ScaffoldedDerivation,
    TeachItBackResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bridge_question(
    question: str = "What connects A and B?", error: str = ""
) -> BridgeQuestion:
    result = MagicMock(spec=BridgeQuestion)
    result.question = question
    result.error = error
    return result


def _make_grade_result(
    correct: bool = True,
    score: float = 0.8,
    feedback: str = "Good.",
    model_solution: str = "sol",
) -> GradeResult:
    result = MagicMock(spec=GradeResult)
    result.correct = correct
    result.score = score
    result.feedback = feedback
    result.model_solution = model_solution
    result.error = ""
    return result


def _make_relational_result(
    correct: bool = True, score: float = 0.9
) -> RelationalGradeResult:
    result = MagicMock(spec=RelationalGradeResult)
    result.correct = correct
    result.score = score
    result.feedback = "Well explained."
    result.missing_relational_claims = []
    result.incorrect_relational_claims = []
    result.model_answer = "model"
    result.error = ""
    return result


def _make_derivation(
    prompt: str = "Derive [...]", steps: list[str] | None = None, error: str = ""
) -> ScaffoldedDerivation:
    result = MagicMock(spec=ScaffoldedDerivation)
    result.prompt = prompt
    result.solution_steps = steps or ["step 1", "step 2"]
    result.error = error
    return result


def _make_teach_result(score: float = 0.8) -> TeachItBackResult:
    result = MagicMock(spec=TeachItBackResult)
    result.score = score
    result.feedback = "Good explanation."
    result.missing_concepts = []
    result.analogy_issues = []
    result.model_answer = "model"
    result.error = ""
    return result


def _make_graph(
    node_description: str = "desc", domain: str = "RL", edge_type: str = "related"
):
    graph = MagicMock()
    node = MagicMock()
    node.description = node_description
    node.domain = domain
    graph.get_node.return_value = node
    edge = MagicMock()
    edge.edge_type = edge_type
    graph.get_edge.return_value = edge
    return graph


# ---------------------------------------------------------------------------
# LearnService.start_connect
# ---------------------------------------------------------------------------


class TestLearnServiceStartConnect:
    @patch("core.learn_service.generate_bridge_question")
    @patch("core.learn_service.get_knowledge_graph")
    def test_returns_question_text(self, mock_graph, mock_generate):
        mock_graph.return_value = _make_graph()
        mock_generate.return_value = _make_bridge_question("Why does A relate to B?")

        service = LearnService()
        result = service.start_connect("DQN", "DDPG")

        assert result.generated_content == "Why does A relate to B?"

    @patch("core.learn_service.generate_bridge_question")
    @patch("core.learn_service.get_knowledge_graph")
    def test_stores_exercise_state(self, mock_graph, mock_generate):
        mock_graph.return_value = _make_graph()
        mock_generate.return_value = _make_bridge_question("Q?")

        service = LearnService()
        service.start_connect("DQN", "DDPG")

        assert service.exercise_type == "connect"
        assert service.concept_a == "DQN"
        assert service.concept_b == "DDPG"

    @patch("core.learn_service.generate_bridge_question")
    @patch("core.learn_service.get_knowledge_graph")
    def test_returns_error_when_llm_fails(self, mock_graph, mock_generate):
        mock_graph.return_value = _make_graph()
        mock_generate.return_value = _make_bridge_question(error="LLM timeout")

        service = LearnService()
        result = service.start_connect("DQN", "DDPG")

        assert result.error


# ---------------------------------------------------------------------------
# LearnService.start_debug
# ---------------------------------------------------------------------------


class TestLearnServiceStartDebug:
    @patch("core.learn_service.generate_wrong_transposition")
    @patch("core.learn_service.get_knowledge_graph")
    def test_returns_generated_scenario(self, mock_graph, mock_generate):
        mock_graph.return_value = _make_graph()
        mock_generate.return_value = "Here is a wrong application..."

        service = LearnService()
        result = service.start_debug("DQN", "finance")

        assert result.generated_content == "Here is a wrong application..."

    @patch("core.learn_service.generate_wrong_transposition")
    @patch("core.learn_service.get_knowledge_graph")
    def test_stores_exercise_state(self, mock_graph, mock_generate):
        mock_graph.return_value = _make_graph()
        mock_generate.return_value = "scenario"

        service = LearnService()
        service.start_debug("DQN", "finance")

        assert service.exercise_type == "debug"
        assert service.concept_a == "DQN"
        assert service.domain_b == "finance"


# ---------------------------------------------------------------------------
# LearnService.start_derive
# ---------------------------------------------------------------------------


class TestLearnServiceStartDerive:
    @patch("core.learn_service.generate_scaffolded_derivation")
    @patch("core.learn_service.get_knowledge_graph")
    def test_returns_derivation_prompt(self, mock_graph, mock_generate):
        mock_graph.return_value = _make_graph()
        mock_generate.return_value = _make_derivation("Derive [...]")

        service = LearnService()
        result = service.start_derive("Bellman equation")

        assert result.generated_content == "Derive [...]"
        assert result.solution_steps == ["step 1", "step 2"]

    @patch("core.learn_service.generate_scaffolded_derivation")
    @patch("core.learn_service.get_knowledge_graph")
    def test_stores_exercise_state(self, mock_graph, mock_generate):
        mock_graph.return_value = _make_graph()
        mock_generate.return_value = _make_derivation()

        service = LearnService()
        service.start_derive("Bellman equation")

        assert service.exercise_type == "derive"
        assert service.concept_a == "Bellman equation"


# ---------------------------------------------------------------------------
# LearnService.start_teach
# ---------------------------------------------------------------------------


class TestLearnServiceStartTeach:
    @patch("core.learn_service.get_knowledge_graph")
    def test_stores_teach_state_without_llm_call(self, mock_graph):
        mock_graph.return_value = _make_graph()

        service = LearnService()
        service.start_teach("DQN", "a student")

        assert service.exercise_type == "teach"
        assert service.concept_a == "DQN"
        assert service.audience == "a student"


# ---------------------------------------------------------------------------
# LearnService.grade_connect
# ---------------------------------------------------------------------------


class TestLearnServiceGradeConnect:
    @patch("core.learn_service.evaluate_relational_explanation")
    def test_returns_grade_result(self, mock_grade):
        mock_grade.return_value = _make_relational_result(correct=True, score=0.9)

        service = LearnService()
        service.exercise_type = "connect"
        service.concept_a = "DQN"
        service.concept_b = "DDPG"
        service.edge_type = "extends"

        result = service.grade_connect("They are related because...")

        assert result.correct is True
        assert result.score == pytest.approx(0.9)

    @patch("core.learn_service.evaluate_relational_explanation")
    def test_passes_stored_state_to_llm(self, mock_grade):
        mock_grade.return_value = _make_relational_result()

        service = LearnService()
        service.concept_a = "DQN"
        service.concept_b = "DDPG"
        service.edge_type = "extends"

        service.grade_connect("answer")

        mock_grade.assert_called_once_with("answer", "DQN", "DDPG", "extends")


# ---------------------------------------------------------------------------
# LearnService.grade_debug
# ---------------------------------------------------------------------------


class TestLearnServiceGradeDebug:
    @patch("core.learn_service.grade_answer")
    def test_returns_grade_result(self, mock_grade):
        mock_grade.return_value = _make_grade_result(correct=True)

        service = LearnService()
        service.exercise_type = "debug"
        service.concept_a = "DQN"
        service.domain_b = "finance"
        service.generated_content = "Wrong scenario here."

        result = service.grade_debug("The error is...")

        assert result.correct is True

    @patch("core.learn_service.grade_answer")
    def test_includes_scenario_in_prompt(self, mock_grade):
        mock_grade.return_value = _make_grade_result()

        service = LearnService()
        service.concept_a = "DQN"
        service.domain_b = "finance"
        service.generated_content = "Wrong scenario."

        service.grade_debug("answer")

        call_args = mock_grade.call_args[0]
        assert "Wrong scenario." in call_args[0]


# ---------------------------------------------------------------------------
# LearnService.grade_derive
# ---------------------------------------------------------------------------


class TestLearnServiceGradeDerive:
    @patch("core.learn_service.grade_answer")
    def test_returns_grade_result(self, mock_grade):
        mock_grade.return_value = _make_grade_result(correct=True)

        service = LearnService()
        service.exercise_type = "derive"
        service.generated_content = "Derive [...]"
        service.solution_steps = ["step 1"]

        result = service.grade_derive("My answer.")

        assert result.correct is True


# ---------------------------------------------------------------------------
# LearnService.grade_teach
# ---------------------------------------------------------------------------


class TestLearnServiceGradeTeach:
    @patch("core.learn_service.grade_teach_it_back")
    @patch("core.learn_service.get_knowledge_graph")
    def test_returns_teach_result(self, mock_graph, mock_grade):
        mock_graph.return_value = _make_graph(
            node_description="DQN is an RL algorithm."
        )
        mock_grade.return_value = _make_teach_result(score=0.85)

        service = LearnService()
        service.exercise_type = "teach"
        service.concept_a = "DQN"
        service.audience = "a beginner"

        result = service.grade_teach("DQN is a neural network that...")

        assert result.score == pytest.approx(0.85)
