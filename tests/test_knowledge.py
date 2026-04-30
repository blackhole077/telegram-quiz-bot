"""Tests for core/knowledge.py."""

from __future__ import annotations

import json
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token-abc123")
os.environ.setdefault("ALLOWED_USER_ID", "99999")

import pytest

from core.knowledge import KnowledgeGraph
from core.schemas.kg_schemas import Edge, KGNode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_node(
    name: str,
    domain: str = "test",
    aliases: list[str] | None = None,
    related: list[str] | None = None,
) -> KGNode:
    return KGNode(
        name=name,
        domain=domain,
        aliases=aliases or [],
        related=related or [],
        source_path=f"{name}.md",
    )


@pytest.fixture
def small_graph() -> KnowledgeGraph:
    nodes = [
        _make_node("Attention Mechanism", aliases=["Attention"], related=["Transformer"]),
        _make_node("Transformer", related=["Attention Mechanism", "BERT"]),
        _make_node("BERT", aliases=["BERT model"], related=["Transformer"]),
        _make_node("Isolated Concept"),
    ]
    return KnowledgeGraph(nodes)


# ---------------------------------------------------------------------------
# get_node
# ---------------------------------------------------------------------------


class TestGetNode:
    def test_lookup_by_canonical_name(self, small_graph: KnowledgeGraph):
        node = small_graph.get_node("Transformer")
        assert node is not None
        assert node.name == "Transformer"

    def test_lookup_by_alias(self, small_graph: KnowledgeGraph):
        node = small_graph.get_node("Attention")
        assert node is not None
        assert node.name == "Attention Mechanism"

    def test_lookup_by_alias_multiword(self, small_graph: KnowledgeGraph):
        node = small_graph.get_node("BERT model")
        assert node is not None
        assert node.name == "BERT"

    def test_unknown_concept_returns_none(self, small_graph: KnowledgeGraph):
        assert small_graph.get_node("Nonexistent Thing") is None

    def test_empty_string_returns_none(self, small_graph: KnowledgeGraph):
        assert small_graph.get_node("") is None


# ---------------------------------------------------------------------------
# get_neighbors
# ---------------------------------------------------------------------------


class TestGetNeighbors:
    def test_returns_edges_for_connected_node(self, small_graph: KnowledgeGraph):
        edges = small_graph.get_neighbors("Transformer")
        assert len(edges) == 2
        targets = {edge.target for edge in edges}
        assert targets == {"Attention Mechanism", "BERT"}

    def test_edge_source_is_canonical_name(self, small_graph: KnowledgeGraph):
        edges = small_graph.get_neighbors("Attention")
        assert all(edge.source == "Attention Mechanism" for edge in edges)

    def test_edge_type_is_related(self, small_graph: KnowledgeGraph):
        edges = small_graph.get_neighbors("Transformer")
        assert all(edge.edge_type == "related" for edge in edges)

    def test_isolated_node_returns_empty_list(self, small_graph: KnowledgeGraph):
        edges = small_graph.get_neighbors("Isolated Concept")
        assert edges == []

    def test_unknown_concept_returns_empty_list(self, small_graph: KnowledgeGraph):
        edges = small_graph.get_neighbors("Does Not Exist")
        assert edges == []

    def test_returns_list_of_edge_instances(self, small_graph: KnowledgeGraph):
        edges = small_graph.get_neighbors("Transformer")
        assert all(isinstance(edge, Edge) for edge in edges)


# ---------------------------------------------------------------------------
# get_edge
# ---------------------------------------------------------------------------


class TestGetEdge:
    def test_direct_edge_exists(self, small_graph: KnowledgeGraph):
        edge = small_graph.get_edge("Transformer", "BERT")
        assert edge is not None
        assert edge.source == "Transformer"
        assert edge.target == "BERT"
        assert edge.edge_type == "related"

    def test_edge_not_present_returns_none(self, small_graph: KnowledgeGraph):
        edge = small_graph.get_edge("BERT", "Isolated Concept")
        assert edge is None

    def test_unknown_source_returns_none(self, small_graph: KnowledgeGraph):
        assert small_graph.get_edge("Nonexistent", "BERT") is None

    def test_unknown_target_returns_none(self, small_graph: KnowledgeGraph):
        assert small_graph.get_edge("Transformer", "Nonexistent") is None

    def test_source_alias_resolves(self, small_graph: KnowledgeGraph):
        edge = small_graph.get_edge("Attention", "Transformer")
        assert edge is not None
        assert edge.source == "Attention Mechanism"

    def test_edge_is_directional(self, small_graph: KnowledgeGraph):
        # Attention -> Transformer exists; Transformer -> Attention does not in
        # the raw related list (it uses the canonical name "Attention Mechanism")
        edge = small_graph.get_edge("Transformer", "Attention Mechanism")
        assert edge is not None


# ---------------------------------------------------------------------------
# KnowledgeGraph.load (smoke test against real data file)
# ---------------------------------------------------------------------------


class TestLoad:
    def test_load_from_default_path_succeeds(self):
        graph = KnowledgeGraph.load()
        assert len(graph) > 0

    def test_loaded_nodes_have_required_fields(self):
        graph = KnowledgeGraph.load()
        for node in graph.all_nodes():
            assert node.name
            assert node.domain

    def test_load_from_fixture_json(self, tmp_path):
        nodes = [
            _make_node("Alpha", related=["Beta"]),
            _make_node("Beta"),
        ]
        data_file = tmp_path / "nodes.json"
        data_file.write_text(json.dumps([node.model_dump() for node in nodes]))
        graph = KnowledgeGraph.load(data_file)
        assert graph.get_node("Alpha") is not None
        assert graph.get_node("Beta") is not None
