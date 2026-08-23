"""
GraphRAG retrieval pipeline: User Query -> embed -> vector search over Chunk
embeddings -> mentioned entities -> graph expansion (approved graph only) ->
assembled context + citations.

Pure orchestration over the EmbeddingProvider/GraphProvider abstractions
already used by the ingest pipeline - mirrors how src/review/*.py is a set
of pure functions over injected repositories. Never touches ApprovalProvider
or OntologyProvider's candidate-side methods: only GraphProvider, which is
Gold-only by construction (see docs/architecture/graph_governance.md and the
docstring on GraphProvider itself) - Candidate Graph data can never reach an
answer through this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config.app_config import AppConfig


@dataclass
class RetrievalResult:
    chunks: list[dict] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    graph_paths: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.chunks


def embed_query(embedding_provider, query: str) -> list[float]:
    records = embedding_provider.embed_chunks(
        [{"chunk_id": "__query__", "document": "__query__", "content": query}]
    )
    return records[0]["embedding_vector"]


def _format_path(path: dict) -> str:
    hops = " -> ".join(path["relationship_types"]) if path["relationship_types"] else "related to"
    return f"{path['source_name']} {hops} {path['target_name']}"


def _format_next_step(path: dict) -> str:
    labels = [label for label in path.get("answer_labels") or [] if label]
    if labels:
        condition = " -> ".join(labels)
        return f"If {condition}: see {path['target_name']}"
    return f"{path['source_name']} leads to {path['target_name']}"


def retrieve_context(
    query: str,
    embedding_provider,
    graph_provider,
    config: AppConfig,
) -> RetrievalResult:
    query_vector = embed_query(embedding_provider, query)

    chunks = graph_provider.search_chunks(query_vector, config.retrieval.top_k_chunks)
    if not chunks:
        return RetrievalResult()

    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    entities = graph_provider.get_mentioned_entities(chunk_ids)

    graph_paths: list[str] = []
    if entities:
        entity_ids = [entity["entity_id"] for entity in entities]
        neighbors = graph_provider.get_neighbors(
            entity_ids, config.retrieval.graph_expansion_hops, config.retrieval.max_neighbors
        )
        entities = entities + neighbors["entities"]
        graph_paths = [_format_path(path) for path in neighbors["paths"]]

    citations = [
        {"chunk_id": chunk["chunk_id"], "document_id": chunk["document_id"]} for chunk in chunks
    ]

    document_ids = list({chunk["document_id"] for chunk in chunks})
    linked = graph_provider.get_linked_documents(
        document_ids, config.retrieval.page_link_hops, config.retrieval.max_neighbors
    )
    next_steps = [_format_next_step(path) for path in linked["paths"]]

    return RetrievalResult(
        chunks=chunks,
        entities=entities,
        graph_paths=graph_paths,
        citations=citations,
        next_steps=next_steps,
    )


def format_context_for_llm(result: RetrievalResult) -> str:
    """Renders a RetrievalResult as plain text to prepend to the user's
    question before it reaches the LLM. Business-friendly language only -
    never "node"/"edge"/"cypher"/"ontology class" (see app/common.py).

    Chunk content originates from ingested documents, not from the operator
    or the LLM, so it is wrapped in explicit untrusted-data delimiters -
    defense against indirect prompt injection via document content that
    contains instruction-like text. See INSTRUCTIONS in
    src/agents/graphrag_agent.py, which tells the LLM never to follow
    directives found inside these markers."""
    if result.is_empty:
        return "No approved knowledge graph content was found for this query."

    lines = ["Relevant excerpts from approved documents:"]
    for chunk in result.chunks:
        lines.append(
            f"- (chunk {chunk['chunk_id']} from document {chunk['document_id']}): "
            f"<<<BEGIN_UNTRUSTED_DOCUMENT_EXCERPT>>>{chunk['content']}<<<END_UNTRUSTED_DOCUMENT_EXCERPT>>>"
        )

    if result.entities:
        lines.append("\nRelated entities mentioned:")
        for entity in result.entities:
            lines.append(f"- {entity['name']} ({entity['entity_type']})")

    if result.graph_paths:
        lines.append("\nRelationships between these entities:")
        for path in result.graph_paths:
            lines.append(f"- {path}")

    if result.next_steps:
        lines.append("\nNext steps in this process:")
        for step in result.next_steps:
            lines.append(f"- {step}")

    return "\n".join(lines)
