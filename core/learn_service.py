"""LearnService: business logic for the learn/exercise flow.

Owns all LLM calls and per-exercise state. The web router calls these methods
and renders templates from the returned data; it does not invoke LLM functions
directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.knowledge import get_knowledge_graph
from core.llm import (
    evaluate_relational_explanation,
    generate_bridge_question,
    generate_scaffolded_derivation,
    generate_wrong_transposition,
    grade_answer,
    grade_teach_it_back,
)
from core.schemas.llm_schemas import (
    GradeResult,
    RelationalGradeResult,
    TeachItBackResult,
)


@dataclass
class ExerciseStart:
    """Data returned after generating a new exercise."""

    generated_content: str = ""
    solution_steps: list[str] = field(default_factory=list)
    error: str = ""


class LearnService:  # pylint: disable=too-many-instance-attributes
    """Manages one user's learn-mode exercise session."""

    def __init__(self) -> None:
        self.exercise_type: str = ""
        self.concept_a: str = ""
        self.concept_b: str = ""
        self.edge_type: str = ""
        self.domain_b: str = ""
        self.audience: str = ""
        self.generated_content: str = ""
        self.solution_steps: list[str] = []

    def start_connect(self, concept_a: str, concept_b: str) -> ExerciseStart:
        """Generate a bridge-question exercise connecting two concepts."""
        graph = get_knowledge_graph()
        node_a = graph.get_node(concept_a)
        node_b = graph.get_node(concept_b)
        edge = graph.get_edge(concept_a, concept_b)
        edge_type = edge.edge_type if edge else "related"

        result = generate_bridge_question(
            concept_a,
            concept_b,
            edge_type,
            node_a.description if node_a else "",
            node_b.description if node_b else "",
            node_a.description if node_a else "",
        )

        if result.error:
            return ExerciseStart(error=result.error)

        self.exercise_type = "connect"
        self.concept_a = concept_a
        self.concept_b = concept_b
        self.edge_type = edge_type
        self.generated_content = result.question

        return ExerciseStart(generated_content=result.question)

    def start_debug(self, concept_a: str, domain_b: str) -> ExerciseStart:
        """Generate a wrong-transposition scenario for the student to debug."""
        graph = get_knowledge_graph()
        node_a = graph.get_node(concept_a)
        domain_a = node_a.domain if node_a else "the source domain"
        topic_material = node_a.description if node_a else ""

        result_text = generate_wrong_transposition(
            concept_a, domain_a, domain_b, topic_material
        )

        if not result_text:
            return ExerciseStart(error="Failed to generate scenario.")

        self.exercise_type = "debug"
        self.concept_a = concept_a
        self.domain_b = domain_b
        self.edge_type = domain_a
        self.generated_content = result_text

        return ExerciseStart(generated_content=result_text)

    def start_derive(self, concept_a: str) -> ExerciseStart:
        """Generate a scaffolded derivation with blanks for the student to fill."""
        graph = get_knowledge_graph()
        node_a = graph.get_node(concept_a)
        source_text = node_a.description if node_a and node_a.description else concept_a
        topic_material = node_a.description if node_a else ""

        result = generate_scaffolded_derivation(source_text, topic_material)

        if result.error or not result.prompt:
            return ExerciseStart(error=result.error or "Failed to generate derivation.")

        self.exercise_type = "derive"
        self.concept_a = concept_a
        self.generated_content = result.prompt
        self.solution_steps = result.solution_steps

        return ExerciseStart(
            generated_content=result.prompt,
            solution_steps=result.solution_steps,
        )

    def start_teach(self, concept_a: str, audience: str) -> ExerciseStart:
        """Set up a teach-it-back exercise (no LLM call at start)."""
        self.exercise_type = "teach"
        self.concept_a = concept_a
        self.audience = audience
        return ExerciseStart()

    def grade_connect(self, answer: str) -> RelationalGradeResult:
        """Grade a student's explanation of the connection between two concepts."""
        return evaluate_relational_explanation(
            answer, self.concept_a, self.concept_b, self.edge_type
        )

    def grade_debug(self, answer: str) -> GradeResult:
        """Grade a student's identification of the error in a wrong-transposition scenario."""
        problem_prompt = (
            f"The following is a plausible but incorrect application of "
            f"'{self.concept_a}' in the domain of '{self.domain_b}'. "
            f"Identify what is wrong and explain the correct application:\n\n"
            f"{self.generated_content}"
        )
        return grade_answer(problem_prompt, "", answer)

    def grade_derive(self, answer: str) -> GradeResult:
        """Grade a student's fill-in-the-blank answers for a scaffolded derivation."""
        solution_text = "\n".join(
            f"{idx}. {step}" for idx, step in enumerate(self.solution_steps)
        )
        return grade_answer(self.generated_content, solution_text, answer)

    def grade_teach(self, answer: str) -> TeachItBackResult:
        """Grade a teach-it-back explanation."""
        graph = get_knowledge_graph()
        node = graph.get_node(self.concept_a)
        topic_material = node.description if node else ""
        return grade_teach_it_back(
            self.concept_a, self.audience, answer, topic_material
        )
