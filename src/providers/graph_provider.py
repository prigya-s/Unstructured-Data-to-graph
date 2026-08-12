"""
GraphProvider: the abstraction boundary for loading a graph_builder.build_graph()
export into a live graph database, and for reading it back for retrieval.
Every read method here is inherently Gold-only: publish() is the only write
path, fed exclusively by approved content (see docs/architecture/
graph_governance.md), so any implementation of these reads inherits that
guarantee for free - no separate filtering logic is needed at the retrieval
layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class GraphProvider(ABC):
    @abstractmethod
    def publish(self, graph: dict) -> dict:
        """graph: graph_builder.build_graph() output. Returns a stats dict
        of nodes/relationships loaded."""

    @abstractmethod
    def search_chunks(self, query_vector: list[float], top_k: int) -> list[dict]:
        """Vector-similarity search over Chunk embeddings. Returns dicts with
        chunk_id, content, document_id, score, ordered by descending score."""

    @abstractmethod
    def get_mentioned_entities(self, chunk_ids: list[str]) -> list[dict]:
        """Entities mentioned by the given chunks. Returns dicts with
        entity_id, name, entity_type."""

    @abstractmethod
    def get_neighbors(self, entity_ids: list[str], hops: int, limit: int) -> dict:
        """Entities reachable from entity_ids within `hops` relationship
        traversals (approved graph only). Returns {"entities": [...],
        "paths": [...]} where each path describes the hop chain
        (source name, relationship type, target name per hop) for citation
        rendering."""
