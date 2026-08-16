"""
Phase 6: Knowledge Graph JSON generation.

Assembles Document, Chunk and Entity nodes plus HAS_CHUNK, MENTIONS and
ontology (USES/DEPENDS_ON/...) relationships into a single graph JSON
document that neo4j_loader.py can load idempotently.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("kg_local.graph_builder")

# Matches MYDET's in-text decision links, e.g.
# "smallblueAn adulthttps://.../pages/289079456/MD1.50+-+Q19smallblueA child..."
# - "smallblue" is the macro-render artifact immediately preceding each
# link's answer label; the label runs up to the URL, and the URL's slug
# runs up to the next such link (or whitespace/end of text). Both captures
# are non-greedy and bounded by the lookahead so consecutive back-to-back
# links (no separator between them) split correctly.
_PAGE_LINK_RE = re.compile(
    r"smallblue(?P<label>.*?)(?P<url>https://\S+?/pages/(?P<page_id>\d+)/\S*?)(?=smallblue|\s|$)"
)


def _extract_page_links(documents: list[dict]) -> tuple[list[dict], int]:
    """Parse MYDET's literal in-text hyperlinks into Document->Document
    decision edges. Returns (links, dropped_external_count).

    Confluence page IDs embedded in these URLs are exactly the document_id
    values used throughout this system (confluence_export_source.py), so
    resolving a link target is a straight lookup against the known
    document set - no separate ID-mapping step needed. Links to pages
    outside the ingested corpus are dropped (and counted) rather than
    loaded as dangling edges."""
    # Keyed by string form so this resolves correctly regardless of whether
    # document_id happens to be stored as a str or an int in the source
    # JSON; the value preserves the original type so the emitted target_id
    # matches the type already used for that Document node's id property.
    known_ids_by_str = {str(doc["document_id"]): doc["document_id"] for doc in documents}
    links: list[dict] = []
    dropped = 0

    for doc in documents:
        markdown = doc.get("markdown") or ""
        for match in _PAGE_LINK_RE.finditer(markdown):
            raw_target_id = match.group("page_id")
            target_id = known_ids_by_str.get(raw_target_id)
            if target_id is None:
                dropped += 1
                logger.warning(
                    "graph_operation operation=page_link status=dropped_external "
                    "source_id=%s target_id=%s",
                    doc["document_id"], raw_target_id,
                )
                continue
            # Cypher MERGE can't key on a null relationship property, so an
            # unlabeled link (rare - two links with no text between them)
            # gets "" rather than None.
            label = match.group("label").strip()
            links.append(
                {
                    "source_id": doc["document_id"],
                    "target_id": target_id,
                    "answer_label": label,
                }
            )

    return links, dropped


def build_graph(
    documents: list[dict],
    chunks: list[dict],
    entities: list[dict],
    mentions: list[dict],
    relationships: list[dict],
) -> dict:
    """documents: [{"document_id","document_name","source_path","markdown_path"}]
    chunks: [{"chunk_id","document","section_path","content","token_count",
              "embedding" (optional, list[float] | None)}]
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
            "space_key": doc.get("space_key"),
            "version": doc.get("version"),
            "content_hash": doc.get("content_hash"),
            "parent_page_id": doc.get("parent_page_id"),
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
            "embedding": chunk.get("embedding"),
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

    # Page-tree lineage/provenance, not a semantic entity relationship - kept
    # as its own relationship list so it loads under a distinct, retrieval-
    # blind relationship type (see neo4j_loader.load_page_hierarchy).
    page_hierarchy = [
        {"child_id": doc["document_id"], "parent_id": doc["parent_page_id"]}
        for doc in documents
        if doc.get("parent_page_id")
    ]

    # In-text decision-tree links (e.g. "An adult" -> Q19, "A child" -> Q33).
    # Document-to-Document and structural like page_hierarchy above, not a
    # semantic entity relationship - see neo4j_loader.load_page_links.
    page_links, page_links_dropped_external = _extract_page_links(documents)

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
            "page_hierarchy": page_hierarchy,
            "page_links": page_links,
        },
        "stats": {
            "documents": len(document_nodes),
            "chunks": len(chunk_nodes),
            "entities": len(entity_nodes),
            "has_chunk": len(has_chunk),
            "mentions": len(mentions_edges),
            "entity_relationships": len(entity_relationships),
            "page_hierarchy": len(page_hierarchy),
            "page_links": len(page_links),
            "page_links_dropped_external": page_links_dropped_external,
        },
    }
