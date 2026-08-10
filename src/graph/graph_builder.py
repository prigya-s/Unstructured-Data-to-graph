"""
Phase 6: Knowledge Graph JSON generation.

Assembles Document, Chunk and Entity nodes plus HAS_CHUNK, MENTIONS and
ontology (USES/DEPENDS_ON/...) relationships into a single graph JSON
document that neo4j_loader.py can load idempotently.
"""

from __future__ import annotations


def build_graph(
    documents: list[dict],
    chunks: list[dict],
    entities: list[dict],
    mentions: list[dict],
    relationships: list[dict],
) -> dict:
    """documents: [{"document_id","document_name","source_path","markdown_path"}]
    chunks: [{"chunk_id","document","section_path","content","token_count"}]
    entities: [{"id","name","type","source_chunk"}]
    mentions: [{"chunk_id","entity_id"}]
    relationships: [{"source","relationship","target","source_chunk"}]
    """
    document_nodes = [
        {
            "id": doc["document_id"],
            "name": doc["document_name"],
            "source_path": doc["source_path"],
            "markdown_path": doc["markdown_path"],
        }
        for doc in documents
    ]

    chunk_nodes = [
        {
            "id": chunk["chunk_id"],
            "document": chunk["document"],
            "section_path": chunk["section_path"],
            "content": chunk["content"],
            "token_count": chunk["token_count"],
        }
        for chunk in chunks
    ]

    entity_nodes = [
        {
            "id": entity["id"],
            "name": entity["name"],
            "type": entity["type"],
            "source_chunk": entity["source_chunk"],
        }
        for entity in entities
    ]

    has_chunk = [
        {"document_id": chunk["document"], "chunk_id": chunk["chunk_id"]} for chunk in chunks
    ]

    mentions_edges = [
        {"chunk_id": m["chunk_id"], "entity_id": m["entity_id"]} for m in mentions
    ]

    entity_relationships = [
        {
            "source": rel["source"],
            "relationship": rel["relationship"],
            "target": rel["target"],
            "source_chunk": rel["source_chunk"],
        }
        for rel in relationships
    ]

    return {
        "nodes": {
            "documents": document_nodes,
            "chunks": chunk_nodes,
            "entities": entity_nodes,
        },
        "relationships": {
            "has_chunk": has_chunk,
            "mentions": mentions_edges,
            "entity_relationships": entity_relationships,
        },
        "stats": {
            "documents": len(document_nodes),
            "chunks": len(chunk_nodes),
            "entities": len(entity_nodes),
            "has_chunk": len(has_chunk),
            "mentions": len(mentions_edges),
            "entity_relationships": len(entity_relationships),
        },
    }
