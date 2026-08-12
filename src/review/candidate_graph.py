"""
Silver-layer Candidate Graph: the graph as currently understood by the
extraction + review engine, built from the full candidate set - not gated
on approval.

Reuses graph_builder.build_graph() unmodified. Unlike
ontology_generator.load_approved_for_graph() (approved-only), this includes
every candidate that hasn't been rejected (NEW, PENDING_REVIEW, APPROVED),
with MERGED entities resolved to their canonical survivor via the shared
merge_resolution helpers - the same resolution ontology_generator uses for
the Gold-layer approved view.

No document/chunk nodes are included (the repository doesn't carry raw
document/chunk records) - only entity and relationship nodes, which is all
the Candidate Graph screen renders.
"""

from __future__ import annotations

from graph import graph_builder

from .merge_resolution import build_merge_map, resolve_entity_id
from .models import WorkflowStatus
from .repository import OntologyRepository


def build_candidate_graph(repository: OntologyRepository) -> dict:
    all_entities = repository.get_candidate_entities()
    merge_map = build_merge_map(all_entities)

    live_entities = [
        e
        for e in all_entities
        if e.status not in (WorkflowStatus.REJECTED, WorkflowStatus.MERGED)
    ]

    entities_for_graph = [
        {
            "id": e.id,
            "name": e.name,
            "type": e.entity_type,
            "source_chunk": e.source_chunks[0] if e.source_chunks else "",
        }
        for e in live_entities
    ]
    entity_ids = {e["id"] for e in entities_for_graph}

    mentions_for_graph = [
        {"chunk_id": chunk_id, "entity_id": e.id}
        for e in live_entities
        for chunk_id in e.source_chunks
    ]

    live_relationships = [
        r for r in repository.get_candidate_relationships() if r.status != WorkflowStatus.REJECTED
    ]

    relationships_for_graph = []
    for rel in live_relationships:
        source_id = resolve_entity_id(rel.source_entity, merge_map)
        target_id = resolve_entity_id(rel.target_entity, merge_map)

        if source_id == target_id:
            continue
        if source_id not in entity_ids or target_id not in entity_ids:
            continue

        relationships_for_graph.append(
            {
                "source": source_id,
                "relationship": rel.relationship_type,
                "target": target_id,
                "source_chunk": "candidate_graph",
            }
        )

    return graph_builder.build_graph([], [], entities_for_graph, mentions_for_graph, relationships_for_graph)
