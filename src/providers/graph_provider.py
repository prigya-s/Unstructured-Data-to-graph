"""
GraphProvider: the abstraction boundary for loading a graph_builder.build_graph()
export into a live graph database, and for reading it back for retrieval.
No business logic outside this module's implementations should import a
graph-database driver class directly.

Two write paths, kept deliberately separate:
- build_production_graph(): the only path that writes the Gold layer
  (:Entity/:Chunk/:Document + the whitelisted ontology relationship types).
  Every read method below is inherently Gold-only, since this is the sole
  producer of that data (see docs/architecture/graph_governance.md) - no
  separate filtering logic is needed at the retrieval layer.
- build_candidate_graph(): writes the Silver layer (pending/candidate
  entities and relationships) under distinct labels
  (:CandidateEntity / :CANDIDATE_RELATIONSHIP) so it can live in the same
  database as the Gold layer without retrieval ever matching it - none of
  search_chunks/get_mentioned_entities/get_neighbors reference these labels.

save_entity()/save_relationship()/save_chunk() are the batched building
blocks build_production_graph() (and implementations' internals) are built
from - always pass a full list to get one UNWIND-batched write, never call
these in a per-row loop.

search_chunks()/get_mentioned_entities()/get_neighbors() stay as specific,
named retrieval methods (GraphRAG's retrieval layer depends on them by
name). query_graph() is a separate, generic parameterized read-only escape
hatch for ad hoc lookups that don't warrant their own named method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class GraphProvider(ABC):
    @abstractmethod
    def connect(self) -> None:
        """Establishes (or verifies, if already established) connectivity
        to the graph database, with retry on transient connection errors.
        Idempotent - safe to call more than once."""

    @abstractmethod
    def create_constraints(self) -> None:
        """Idempotently ensures all required uniqueness constraints exist
        (Document/Chunk/Entity/CandidateEntity id). Safe to call every run."""

    @abstractmethod
    def create_indexes(self) -> None:
        """Idempotently ensures all required indexes exist (e.g. the chunk
        embedding vector index). Safe to call every run, including before
        any chunk has been loaded."""

    @abstractmethod
    def save_entity(self, entities: list[dict]) -> int:
        """Batched upsert of Entity nodes ({"id","name","type","source_chunk"}).
        Returns the number of entities written."""

    @abstractmethod
    def save_relationship(self, relationships: list[dict]) -> int:
        """Batched upsert of ontology relationships between existing Entity
        nodes ({"source","relationship","target","source_chunk"}). Returns
        the number of relationships written."""

    @abstractmethod
    def save_chunk(self, chunks: list[dict]) -> int:
        """Batched upsert of Chunk nodes ({"id","document","section_path",
        "content","token_count","embedding"}). Returns the number of chunks
        written."""

    @abstractmethod
    def build_candidate_graph(self, graph: dict) -> dict:
        """graph: review.candidate_graph.build_candidate_graph() output
        (entities/relationships only, no document/chunk nodes). Fully
        refreshes the Silver-tier :CandidateEntity/:CANDIDATE_RELATIONSHIP
        subgraph for this run (clears then reloads) so approve/reject/merge
        transitions since the last run are reflected. Returns a stats dict."""

    @abstractmethod
    def build_production_graph(self, graph: dict) -> dict:
        """graph: graph_builder.build_graph() output. Orchestrates
        create_constraints() + create_indexes() + save_chunk()/save_entity()/
        save_relationship() (plus document/has_chunk/mentions edges) for the
        Gold layer. Returns a stats dict of nodes/relationships loaded."""

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

    @abstractmethod
    def get_linked_documents(self, document_ids: list[str], hops: int, limit: int) -> dict:
        """Documents reachable from document_ids within `hops` LEADS_TO
        traversals - the Document-level, forward-only counterpart to
        get_neighbors (decision-tree "what happens next", not entity
        relationships). Returns {"documents": [...], "paths": [...]} where
        each path carries the answer_label(s) along the hop chain, for
        rendering a "next steps" section."""

    @abstractmethod
    def query_graph(self, cypher: str, params: dict | None = None) -> list[dict]:
        """Generic parameterized, read-only escape hatch for ad hoc queries
        that don't warrant a dedicated method. Not used by any retrieval
        path today."""

    @abstractmethod
    def close(self) -> None:
        """Releases the underlying connection/driver, if one was opened."""
