"""Proves CRITICAL 1's fix: stages 2-7 read their inputs from StorageProvider
rather than trusting a prior stage's in-memory ctx.<field>. Every test below
constructs a *fresh* PipelineContext (ctx.<field> at its dataclass default -
empty list/tuple, exactly as if this were a separate Databricks Workflow
task with no shared Python heap) and seeds only the fake StorageProvider -
if a stage regressed to reading ctx.<field> instead, it would process
nothing and every assertion here would fail."""

from __future__ import annotations

from config.app_config import AppConfig
from pipeline.context import PipelineContext
from pipeline.stages import (
    approval_stage,
    chunking_stage,
    entity_extraction_stage,
    extraction_stage,
    relationship_extraction_stage,
)
from pipeline.stages.approval_stage import ApprovalStage
from pipeline.stages.candidate_graph_stage import CandidateGraphStage
from pipeline.stages.chunking_stage import ChunkingStage
from pipeline.stages.embedding_stage import EmbeddingStage
from pipeline.stages.entity_extraction_stage import EntityExtractionStage
from pipeline.stages.extraction_stage import ExtractionStage
from pipeline.stages.relationship_extraction_stage import RelationshipExtractionStage
from providers.storage_provider import StorageProvider


class FakeStorageProvider(StorageProvider):
    def __init__(self, **seed) -> None:
        self._documents = seed.get("documents", [])
        self._markdown = seed.get("markdown", [])
        self._chunks = seed.get("chunks", [])
        self._embeddings = seed.get("embeddings", [])
        self._entities = seed.get("entities", ([], []))
        self._relationships = seed.get("relationships", [])
        self._approved_entities = seed.get("approved_entities", [])
        self._approved_relationships = seed.get("approved_relationships", [])
        self._ontology = seed.get("ontology")
        self._graph_export = seed.get("graph_export")
        self._candidate_graph = seed.get("candidate_graph")
        self.written: dict = {}

    def write_documents(self, records):
        self.written["documents"] = records

    def read_documents(self):
        return self._documents

    def write_markdown(self, records):
        self.written["markdown"] = records

    def read_markdown(self):
        return self._markdown

    def write_chunks(self, records):
        self.written["chunks"] = records

    def read_chunks(self):
        return self._chunks

    def write_embeddings(self, records):
        self.written["embeddings"] = records

    def read_embeddings(self):
        return self._embeddings

    def write_entities(self, entities, mentions):
        self.written["entities"] = (entities, mentions)

    def read_entities(self):
        return self._entities

    def write_relationships(self, records):
        self.written["relationships"] = records

    def read_relationships(self):
        return self._relationships

    def write_approved_entities(self, records):
        self.written["approved_entities"] = records

    def read_approved_entities(self):
        return self._approved_entities

    def write_approved_relationships(self, records):
        self.written["approved_relationships"] = records

    def read_approved_relationships(self):
        return self._approved_relationships

    def write_ontology(self, record):
        self.written["ontology"] = record

    def read_ontology(self):
        return self._ontology

    def write_graph_export(self, record):
        self.written["graph_export"] = record

    def read_graph_export(self):
        return self._graph_export

    def write_candidate_graph(self, record):
        self.written["candidate_graph"] = record

    def read_candidate_graph(self):
        return self._candidate_graph


def _fresh_ctx(storage, **providers_) -> PipelineContext:
    return PipelineContext(
        config=AppConfig(),
        storage=storage,
        document_source=providers_.get("document_source"),
        embedding_provider=providers_.get("embedding_provider"),
        approval_provider=providers_.get("approval_provider"),
        ontology_provider=providers_.get("ontology_provider"),
        graph_provider=providers_.get("graph_provider"),
        ontology_schema=providers_.get("ontology_schema", {}),
    )


class FakeDocumentSource:
    def read_document(self, doc_ref):
        return f"/fake/{doc_ref['document_id']}"

    def list_documents(self):
        raise AssertionError("ExtractionStage must not call list_documents()")


def test_extraction_stage_reads_from_storage_not_ctx(monkeypatch):
    monkeypatch.setattr(extraction_stage.docling_parser, "convert_to_markdown", lambda path: f"# {path}")
    storage = FakeStorageProvider(
        documents=[{"document_id": "d1", "document_name": "d1.txt", "source_path": "d1.txt"}]
    )
    ctx = _fresh_ctx(storage, document_source=FakeDocumentSource())
    assert ctx.documents == []

    result = ExtractionStage().run(ctx)

    assert [d["document_id"] for d in result.markdown_documents] == ["d1"]
    assert storage.written["markdown"] == result.markdown_documents


def test_chunking_stage_reads_from_storage_not_ctx(monkeypatch):
    monkeypatch.setattr(
        chunking_stage.semantic_chunker,
        "chunk_markdown",
        lambda markdown, document_id: [{"chunk_id": f"{document_id}-0", "content": markdown, "document": document_id}],
    )
    storage = FakeStorageProvider(
        markdown=[{"document_id": "d1", "document_name": "d1.txt", "source_path": "d1.txt", "markdown_path": "", "markdown": "hello"}]
    )
    ctx = _fresh_ctx(storage)
    assert ctx.chunks == []

    result = ChunkingStage().run(ctx)

    assert [c["chunk_id"] for c in result.chunks] == ["d1-0"]
    assert storage.written["chunks"] == result.chunks


class FakeEmbeddingProvider:
    def __init__(self, embeddings):
        self._embeddings = embeddings
        self.received_chunks = None

    def embed_chunks(self, chunks):
        self.received_chunks = chunks
        return self._embeddings


def test_embedding_stage_reads_from_storage_not_ctx():
    chunks = [{"chunk_id": "c1", "content": "hello", "document": "d1"}]
    embedding_provider = FakeEmbeddingProvider([{"chunk_id": "c1", "embedding_vector": None}])
    storage = FakeStorageProvider(chunks=chunks)
    ctx = _fresh_ctx(storage, embedding_provider=embedding_provider)
    assert ctx.chunks == []

    result = EmbeddingStage().run(ctx)

    assert embedding_provider.received_chunks == chunks
    assert result.embeddings == embedding_provider._embeddings
    assert storage.written["embeddings"] == result.embeddings


def test_entity_extraction_stage_reads_from_storage_not_ctx(monkeypatch):
    received = {}

    def fake_extract_entities(chunks, schema):
        received["chunks"] = chunks
        received["schema"] = schema
        return ([{"id": "e1", "type": "System", "name": "Foo"}], [{"entity_id": "e1", "chunk_id": "c1"}])

    monkeypatch.setattr(entity_extraction_stage.entity_extractor, "extract_entities", fake_extract_entities)

    chunks = [{"chunk_id": "c1", "content": "hello", "document": "d1"}]
    storage = FakeStorageProvider(chunks=chunks)
    ctx = _fresh_ctx(storage, ontology_schema={"types": ["System"]})
    assert ctx.chunks == [] and ctx.entities == []

    result = EntityExtractionStage().run(ctx)

    assert received["chunks"] == chunks
    assert received["schema"] == {"types": ["System"]}
    assert result.entities == [{"id": "e1", "type": "System", "name": "Foo"}]
    assert storage.written["entities"] == (result.entities, result.mentions)


def test_relationship_extraction_stage_reads_from_storage_not_ctx(monkeypatch):
    received = {}

    def fake_extract_relationships(chunks, entities, mentions, schema):
        received.update(chunks=chunks, entities=entities, mentions=mentions, schema=schema)
        return [{"source": "e1", "relationship": "USES", "target": "e2", "source_chunk": "c1"}]

    monkeypatch.setattr(
        relationship_extraction_stage.relationship_extractor,
        "extract_relationships",
        fake_extract_relationships,
    )

    chunks = [{"chunk_id": "c1", "content": "hello", "document": "d1"}]
    entities = [{"id": "e1", "type": "System", "name": "Foo"}]
    mentions = [{"entity_id": "e1", "chunk_id": "c1"}]
    storage = FakeStorageProvider(chunks=chunks, entities=(entities, mentions))
    ctx = _fresh_ctx(storage)
    assert ctx.chunks == [] and ctx.entities == [] and ctx.mentions == []

    result = RelationshipExtractionStage().run(ctx)

    assert received["chunks"] == chunks
    assert received["entities"] == entities
    assert received["mentions"] == mentions
    assert result.relationships == [{"source": "e1", "relationship": "USES", "target": "e2", "source_chunk": "c1"}]
    assert storage.written["relationships"] == result.relationships


def test_approval_stage_reads_from_storage_not_ctx(monkeypatch):
    received = {}

    def fake_build_candidates(entities, mentions, relationships, chunks, repository):
        received.update(entities=entities, mentions=mentions, relationships=relationships, chunks=chunks, repository=repository)
        return (1, 1)

    monkeypatch.setattr(approval_stage, "build_candidates", fake_build_candidates)

    entities = [{"id": "e1", "type": "System", "name": "Foo"}]
    mentions = [{"entity_id": "e1", "chunk_id": "c1"}]
    relationships = [{"source": "e1", "relationship": "USES", "target": "e2", "source_chunk": "c1"}]
    chunks = [{"chunk_id": "c1", "content": "hello", "document": "d1"}]
    storage = FakeStorageProvider(entities=(entities, mentions), relationships=relationships, chunks=chunks)
    approval_provider = object()
    ctx = _fresh_ctx(storage, approval_provider=approval_provider)
    assert ctx.entities == [] and ctx.relationships == [] and ctx.chunks == []

    result = ApprovalStage().run(ctx)

    assert received["entities"] == entities
    assert received["mentions"] == mentions
    assert received["relationships"] == relationships
    assert received["chunks"] == chunks
    assert received["repository"] is approval_provider
    assert result.entities_saved == 1
    assert result.relationships_saved == 1


class FakeApprovalProvider:
    def __init__(self, entities, relationships) -> None:
        self._entities = entities
        self._relationships = relationships

    def get_candidate_entities(self):
        return self._entities

    def get_candidate_relationships(self):
        return self._relationships


def test_candidate_graph_stage_reads_from_approval_provider_not_ctx():
    from review.models import CandidateEntity, CandidateRelationship, WorkflowStatus

    entities = [
        CandidateEntity(
            id="e1", name="Foo", entity_type="System", definition="d", business_meaning="b",
            confidence_score=1.0, status=WorkflowStatus.APPROVED,
        ),
        CandidateEntity(
            id="e2", name="Bar", entity_type="System", definition="d", business_meaning="b",
            confidence_score=1.0, status=WorkflowStatus.PENDING_REVIEW,
        ),
    ]
    relationships = [
        CandidateRelationship(
            id="rel1", source_entity="e1", relationship_type="USES", target_entity="e2",
            confidence_score=1.0, status=WorkflowStatus.PENDING_REVIEW,
        )
    ]
    storage = FakeStorageProvider()
    approval_provider = FakeApprovalProvider(entities, relationships)
    ctx = _fresh_ctx(storage, approval_provider=approval_provider)
    assert ctx.candidate_graph is None

    result = CandidateGraphStage().run(ctx)

    assert result.candidate_graph["stats"]["entities"] == 2
    assert result.candidate_graph["stats"]["entity_relationships"] == 1
    assert storage.written["candidate_graph"] == result.candidate_graph
