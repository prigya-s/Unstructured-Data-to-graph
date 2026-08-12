"""
StorageProvider: the abstraction boundary between pipeline stages and the
bronze/silver/gold lakehouse layout. Every write_*/read_* pair corresponds
to one table contract in src/contracts/schemas.py. Stages never construct a
Path themselves - only a StorageProvider implementation does.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class StorageProvider(ABC):
    # -- bronze -------------------------------------------------------------
    @abstractmethod
    def write_documents(self, records: list[dict]) -> None:
        """RawDocumentRecord rows."""

    @abstractmethod
    def read_documents(self) -> list[dict]:
        ...

    # -- silver ---------------------------------------------------------------
    @abstractmethod
    def write_markdown(self, records: list[dict]) -> None:
        """MarkdownDocumentRecord rows."""

    @abstractmethod
    def read_markdown(self) -> list[dict]:
        ...

    @abstractmethod
    def write_chunks(self, records: list[dict]) -> None:
        """DocumentChunkRecord rows."""

    @abstractmethod
    def read_chunks(self) -> list[dict]:
        ...

    @abstractmethod
    def write_embeddings(self, records: list[dict]) -> None:
        """DocumentEmbeddingRecord rows."""

    @abstractmethod
    def read_embeddings(self) -> list[dict]:
        ...

    # -- gold -----------------------------------------------------------------
    # write_entities/write_relationships hold raw, pre-review extraction
    # output - not yet Silver candidates or Gold approved content. They
    # become Silver once run through review.candidate_builder.build_candidates()
    # into the ApprovalProvider.
    @abstractmethod
    def write_entities(self, entities: list[dict], mentions: list[dict]) -> None:
        """CandidateEntityRecord-shaped raw entities plus their chunk mentions."""

    @abstractmethod
    def read_entities(self) -> tuple[list[dict], list[dict]]:
        ...

    @abstractmethod
    def write_relationships(self, records: list[dict]) -> None:
        ...

    @abstractmethod
    def read_relationships(self) -> list[dict]:
        ...

    @abstractmethod
    def write_approved_entities(self, records: list[dict]) -> None:
        """ApprovedEntityRecord rows."""

    @abstractmethod
    def read_approved_entities(self) -> list[dict]:
        ...

    @abstractmethod
    def write_approved_relationships(self, records: list[dict]) -> None:
        """ApprovedRelationshipRecord rows."""

    @abstractmethod
    def read_approved_relationships(self) -> list[dict]:
        ...

    @abstractmethod
    def write_ontology(self, record: dict) -> None:
        """OntologyRecord."""

    @abstractmethod
    def read_ontology(self) -> dict | None:
        ...

    @abstractmethod
    def write_graph_export(self, record: dict) -> None:
        """Gold-layer Production Graph: graph_builder.build_graph() output
        over approved-only content, persisted for auditability before it is
        loaded into a GraphProvider (Neo4j/Cosmos)."""

    @abstractmethod
    def read_graph_export(self) -> dict | None:
        ...

    # -- silver: candidate graph -----------------------------------------------
    @abstractmethod
    def write_candidate_graph(self, record: dict) -> None:
        """Silver-layer Candidate Graph: graph_builder.build_graph() output
        over the full candidate set (pending + approved, merges resolved) -
        the graph as currently understood by the extraction/review engine,
        not yet gated on approval. Never loaded into a GraphProvider."""

    @abstractmethod
    def read_candidate_graph(self) -> dict | None:
        ...
