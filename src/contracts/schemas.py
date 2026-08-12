"""
Table contracts for the bronze/silver/gold lakehouse layout.

These dataclasses document the exact row shape written at each layer -
they are not a new serialization framework. Field names/types are traced
directly from the existing business-logic functions that produce them
(docling_parser.extract_all, semantic_chunker.chunk_markdown,
entity_extractor.extract_entities, relationship_extractor.extract_relationships,
review.models.CandidateEntity/CandidateRelationship.to_dict(),
review.ontology_generator.generate_approved_ontology). LocalStorageProvider
writes plain dicts matching these shapes; a future Delta-backed
StorageProvider would define one Delta table per contract with the same
columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RawDocumentRecord:
    """bronze/raw_documents - one row per source file discovered by a DocumentSource."""

    document_id: str
    document_name: str
    source_path: str
    ingested_at: str


@dataclass
class MarkdownDocumentRecord:
    """silver/markdown - docling_parser.extract_all() output shape."""

    document_id: str
    document_name: str
    source_path: str
    markdown_path: str
    markdown: str


@dataclass
class DocumentChunkRecord:
    """silver/chunks - semantic_chunker.chunk_markdown() output shape."""

    chunk_id: str
    document: str
    section_path: str
    content: str
    token_count: int


@dataclass
class DocumentEmbeddingRecord:
    """silver/embeddings - embedding_vector/embedding_model are None under
    LocalEmbeddingProvider's no-op pass-through; a real embedding provider
    populates both."""

    chunk_id: str
    document: str
    embedding_vector: list[float] | None = None
    embedding_model: str | None = None


@dataclass
class CandidateEntityRecord:
    """silver/entities - mirrors review.models.CandidateEntity.to_dict().
    Candidate (pre-approval) rows; promoted to Gold only via
    ApprovedEntityRecord once approved."""

    id: str
    name: str
    entity_type: str
    definition: str
    business_meaning: str
    confidence_score: float
    status: str
    evidence: list[str] = field(default_factory=list)
    source_documents: list[str] = field(default_factory=list)
    source_chunks: list[str] = field(default_factory=list)
    possible_meanings: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    reviewer: str | None = None
    review_timestamp: str | None = None
    merged_into: str | None = None


@dataclass
class CandidateRelationshipRecord:
    """silver/relationships - mirrors review.models.CandidateRelationship.to_dict().
    Candidate (pre-approval) rows; promoted to Gold only via
    ApprovedRelationshipRecord once approved."""

    id: str
    source_entity: str
    relationship_type: str
    target_entity: str
    confidence_score: float
    status: str
    evidence: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    reviewer: str | None = None
    review_timestamp: str | None = None


@dataclass
class ApprovedEntityRecord:
    """gold/approved_entities - mirrors ontology_generator.generate_approved_ontology()'s entities_out row shape."""

    id: str
    name: str
    category: str
    definition: str
    business_meaning: str
    confidence_score: float
    source_documents: list[str] = field(default_factory=list)


@dataclass
class ApprovedRelationshipRecord:
    """gold/approved_relationships - mirrors ontology_generator.generate_approved_ontology()'s relationships_out row shape."""

    id: str
    source_entity: str
    source_name: str
    relationship_type: str
    target_entity: str
    target_name: str
    confidence_score: float


@dataclass
class OntologyRecord:
    """gold/ontology - mirrors ontology_generator.generate_approved_ontology()'s full output shape."""

    generated_at: str
    entities: list[ApprovedEntityRecord] = field(default_factory=list)
    relationships: list[ApprovedRelationshipRecord] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


@dataclass
class RawEntityRecord:
    """gold/entities (entities.json) - entity_extractor.extract_entities() entity shape,
    pre-review (not yet a CandidateEntityRecord)."""

    id: str
    name: str
    type: str
    source_chunk: str


@dataclass
class EntityMentionRecord:
    """gold/entities (mentions.json) - one row per (chunk, entity) pair."""

    chunk_id: str
    entity_id: str


@dataclass
class RawRelationshipRecord:
    """gold/relationships - relationship_extractor.extract_relationships() output shape,
    pre-review (not yet a CandidateRelationshipRecord)."""

    source: str
    relationship: str
    target: str
    source_chunk: str


# Registry driving a schema-derived storage implementation (see
# providers/_delta_sql.py): logical table name -> (dataclass, primary-key
# column tuple). Every StorageProvider write_*/read_* pair maps to exactly
# one entry here (write_entities/write_ontology/write_graph_export touch
# two tables each). This is the single source of truth a Delta-backed or
# Volumes-backed StorageProvider implementation is generated from - adding
# a column here is the only change needed to add one to every backend.
TABLE_REGISTRY: dict[str, tuple[type, tuple[str, ...]]] = {
    "raw_documents": (RawDocumentRecord, ("document_id",)),
    "markdown": (MarkdownDocumentRecord, ("document_id",)),
    "chunks": (DocumentChunkRecord, ("chunk_id",)),
    "embeddings": (DocumentEmbeddingRecord, ("chunk_id",)),
    "entities": (RawEntityRecord, ("id",)),
    "mentions": (EntityMentionRecord, ("chunk_id", "entity_id")),
    "relationships": (RawRelationshipRecord, ("source", "relationship", "target")),
    "approved_entities": (ApprovedEntityRecord, ("id",)),
    "approved_relationships": (ApprovedRelationshipRecord, ("id",)),
    "candidate_entities": (CandidateEntityRecord, ("id",)),
    "candidate_relationships": (CandidateRelationshipRecord, ("id",)),
}

# Single-document ("blob") tables: unlike TABLE_REGISTRY's row-per-business
# -record tables, these hold exactly one JSON document per deployment
# (the latest ontology publish / graph export / candidate graph) - see
# providers/_delta_sql.py BlobStore, which stores each as a single row keyed
# by a constant id. "graph_export" is the Gold-layer Production Graph;
# "candidate_graph" is the Silver-layer Candidate Graph.
BLOB_TABLES = ("ontology", "graph_export", "candidate_graph")
