"""
PipelineContext: carries the six providers plus whatever in-memory data one
stage hands to the next within a single local run. Mirrors passing data
between Databricks Workflow tasks via tables, while staying in-memory for a
single local `ingest` invocation - each stage additionally persists its
output via the relevant provider's write_*() method for durability and for
separate CLI invocations (publish-ontology, publish-graph) to read back.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.app_config import AppConfig
from providers.approval_provider import ApprovalProvider
from providers.document_source import DocumentSource
from providers.embedding_provider import EmbeddingProvider
from providers.extraction_provider import ExtractionProvider
from providers.graph_provider import GraphProvider
from providers.ontology_provider import OntologyProvider
from providers.storage_provider import StorageProvider


@dataclass
class PipelineContext:
    config: AppConfig
    storage: StorageProvider
    document_source: DocumentSource
    embedding_provider: EmbeddingProvider
    approval_provider: ApprovalProvider
    ontology_provider: OntologyProvider
    graph_provider: GraphProvider
    extraction_provider: ExtractionProvider
    ontology_schema: dict = field(default_factory=dict)

    documents: list = field(default_factory=list)
    markdown_documents: list = field(default_factory=list)
    chunks: list = field(default_factory=list)
    embeddings: list = field(default_factory=list)
    entities: list = field(default_factory=list)
    mentions: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    entities_saved: int = 0
    relationships_saved: int = 0
    candidate_graph: dict | None = None
    ontology_result: dict | None = None
    graph_export: dict | None = None
    publish_stats: dict = field(default_factory=dict)
