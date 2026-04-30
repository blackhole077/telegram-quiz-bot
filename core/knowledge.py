"""Knowledge graph backed by data/kg_nodes.json.

Loads the pre-built node list once and exposes graph traversal helpers
used by the constructive exercise layer.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.schemas.kg_schemas import EDGE_TYPE_RELATED, Edge, KGNode

_DEFAULT_PATH = Path(__file__).parent.parent / "data" / "kg_nodes.json"


class KnowledgeGraph:
    """In-memory knowledge graph over a list of KGNodes."""

    def __init__(self, nodes: list[KGNode]) -> None:
        self._nodes: dict[str, KGNode] = {}
        self._alias_index: dict[str, str] = {}

        for node in nodes:
            self._nodes[node.name] = node
            for alias in node.aliases:
                self._alias_index[alias] = node.name

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def _canonical(self, concept: str) -> str | None:
        """Resolve concept name or alias to canonical node name."""
        if concept in self._nodes:
            return concept
        return self._alias_index.get(concept)

    def get_node(self, concept: str) -> KGNode | None:
        canonical = self._canonical(concept)
        return self._nodes.get(canonical) if canonical else None

    # ------------------------------------------------------------------
    # Graph traversal
    # ------------------------------------------------------------------

    def get_neighbors(self, concept: str) -> list[Edge]:
        """Return all edges leaving ``concept`` (undirected, type=related)."""
        node = self.get_node(concept)
        if node is None:
            return []
        canonical = self._canonical(concept)
        return [
            Edge(source=canonical, target=related_name, edge_type=EDGE_TYPE_RELATED)
            for related_name in node.related
        ]

    def get_edge(self, node_a: str, node_b: str) -> Edge | None:
        """Return the edge from ``node_a`` to ``node_b``, or None."""
        node = self.get_node(node_a)
        if node is None:
            return None
        canonical_a = self._canonical(node_a)
        canonical_b = self._canonical(node_b)

        for related_name in node.related:
            related_canonical = self._canonical(related_name) or related_name
            if related_canonical == canonical_b or related_name == node_b:
                return Edge(
                    source=canonical_a, target=related_name, edge_type=EDGE_TYPE_RELATED
                )
        return None

    def all_nodes(self) -> list[KGNode]:
        return list(self._nodes.values())

    def __len__(self) -> int:
        return len(self._nodes)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path = _DEFAULT_PATH) -> KnowledgeGraph:
        nodes = [KGNode.model_validate(entry) for entry in json.loads(path.read_text())]
        return cls(nodes)


_graph: KnowledgeGraph | None = None  # pylint: disable=invalid-name


def get_knowledge_graph(path: Path = _DEFAULT_PATH) -> KnowledgeGraph:
    """Return the module-level KnowledgeGraph, loading once on first call."""
    global _graph  # pylint: disable=global-statement
    if _graph is None:
        _graph = KnowledgeGraph.load(path)
    return _graph
