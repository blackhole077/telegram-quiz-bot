"""Topic registry schema."""

from __future__ import annotations

from pydantic import BaseModel


class Topic(BaseModel):
    """A single entry in the topic registry.

    ``name`` matches ``Question.topic`` and is the join key between
    the question pool and the registry.  ``domain`` is the canonical
    grouping used for the practice dropdown and knowledge graph work.
    """

    name: str
    domain: str
