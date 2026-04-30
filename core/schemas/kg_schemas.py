"""Knowledge graph node and edge schemas."""

from __future__ import annotations

from pydantic import BaseModel

EDGE_TYPE_RELATED = "related"


class Edge(BaseModel):
    """A directed edge in the knowledge graph.

    ``source`` and ``target`` are canonical node names.  ``edge_type``
    starts as EDGE_TYPE_RELATED for all wikilink-derived edges; typed edges
    (precedes, is-a, etc.) are a future enrichment.
    """

    source: str
    target: str
    edge_type: str = EDGE_TYPE_RELATED


class KGNode(BaseModel):
    """A single node in the knowledge graph, derived from a vault note.

    ``name`` is the canonical title of the concept (from frontmatter).
    ``related`` contains wikilink targets found in the note body — all
    edges are treated as undirected "is related" until directionality is
    added later.
    ``source_path`` is the vault-relative path for traceability.
    """

    name: str
    domain: str
    aliases: list[str] = []
    description: str = ""
    tags: list[str] = []
    related: list[str] = []
    source_path: str = ""
