"""
Ontology Generation stage.

Reads ONLY approved concepts/relationships from an OntologyRepository,
resolves MERGED entities to their surviving (canonical) entity, and
produces:
  - a business-friendly ontology artifact (generate_approved_ontology), and
  - the graph_builder-ready (entities, mentions, relationships) tuple used
    by publisher.publish_graph (load_approved_for_graph).

Critical rule enforced here: rejected, pending, new, or merged-away
concepts are never included in either output.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .models import CandidateEntity, CandidateRelationship, WorkflowStatus
from .repository import OntologyRepository

logger = logging.getLogger("kg_local.ontology_generator")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUT_PATH = _PROJECT_ROOT / "output" / "review" / "approved_ontology.json"


def _build_merge_map(entities: list[CandidateEntity]) -> dict[str, str]:
    """{merged_entity_id: canonical_entity_id} for entities merged into an
    approved survivor. Entries pointing at a non-approved survivor are
    dropped with a warning (the merge target must itself be approved)."""
    approved_ids = {e.id for e in entities if e.status == WorkflowStatus.APPROVED}
    merge_map: dict[str, str] = {}
    for entity in entities:
        if entity.status != WorkflowStatus.MERGED or not entity.merged_into:
            continue
        if entity.merged_into not in approved_ids:
            logger.warning(
                "Entity %s is merged into %s, which is not approved - skipping merge resolution",
                entity.id,
                entity.merged_into,
            )
            continue
        merge_map[entity.id] = entity.merged_into
    return merge_map


def _resolve_entity_id(entity_id: str, merge_map: dict[str, str]) -> str:
    if entity_id in merge_map:
        resolved = merge_map[entity_id]
        if resolved in merge_map:
            logger.warning("Merge chain detected for %s -> %s; not following further", entity_id, resolved)
        return resolved
    return entity_id


def generate_approved_ontology(
    repository: OntologyRepository,
    output_path: Path | None = None,
) -> dict:
    output_path = output_path or _DEFAULT_OUTPUT_PATH

    all_entities = repository.get_candidate_entities()
    approved_entities = [e for e in all_entities if e.status == WorkflowStatus.APPROVED]
    entity_by_id = {e.id: e for e in approved_entities}
    merge_map = _build_merge_map(all_entities)

    approved_relationships = [
        r for r in repository.get_candidate_relationships() if r.status == WorkflowStatus.APPROVED
    ]

    entities_out = [
        {
            "id": e.id,
            "name": e.name,
            "category": e.entity_type,
            "definition": e.definition,
            "business_meaning": e.business_meaning,
            "confidence_score": e.confidence_score,
            "source_documents": e.source_documents,
        }
        for e in approved_entities
    ]

    relationships_out = []
    for rel in approved_relationships:
        source_id = _resolve_entity_id(rel.source_entity, merge_map)
        target_id = _resolve_entity_id(rel.target_entity, merge_map)

        if source_id == target_id:
            continue
        if source_id not in entity_by_id or target_id not in entity_by_id:
            continue

        relationships_out.append(
            {
                "id": rel.id,
                "source_entity": source_id,
                "source_name": entity_by_id[source_id].name,
                "relationship_type": rel.relationship_type,
                "target_entity": target_id,
                "target_name": entity_by_id[target_id].name,
                "confidence_score": rel.confidence_score,
            }
        )

    by_category: dict[str, int] = {}
    for e in entities_out:
        by_category[e["category"]] = by_category.get(e["category"], 0) + 1

    by_relationship_type: dict[str, int] = {}
    for r in relationships_out:
        by_relationship_type[r["relationship_type"]] = by_relationship_type.get(r["relationship_type"], 0) + 1

    ontology = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entities": entities_out,
        "relationships": relationships_out,
        "stats": {
            "total_entities": len(entities_out),
            "total_relationships": len(relationships_out),
            "by_category": by_category,
            "by_relationship_type": by_relationship_type,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(ontology, indent=2), encoding="utf-8")
    return ontology


def load_approved_for_graph(
    repository: OntologyRepository,
    all_mentions: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Returns (entities, mentions, relationships) shaped for
    graph_builder.build_graph - approved-only, with MERGED entities
    resolved to their canonical survivor."""
    all_entities = repository.get_candidate_entities()
    approved_entities = [e for e in all_entities if e.status == WorkflowStatus.APPROVED]
    approved_ids = {e.id for e in approved_entities}
    merge_map = _build_merge_map(all_entities)

    entities_for_graph = [
        {
            "id": e.id,
            "name": e.name,
            "type": e.entity_type,
            "source_chunk": e.source_chunks[0] if e.source_chunks else "",
        }
        for e in approved_entities
    ]

    mentions_for_graph = [m for m in all_mentions if m["entity_id"] in approved_ids]

    approved_relationships = [
        r for r in repository.get_candidate_relationships() if r.status == WorkflowStatus.APPROVED
    ]

    relationships_for_graph = []
    for rel in approved_relationships:
        source_id = _resolve_entity_id(rel.source_entity, merge_map)
        target_id = _resolve_entity_id(rel.target_entity, merge_map)

        if source_id == target_id:
            continue
        if source_id not in approved_ids or target_id not in approved_ids:
            continue

        relationships_for_graph.append(
            {
                "source": source_id,
                "relationship": rel.relationship_type,
                "target": target_id,
                "source_chunk": "approved_ontology",
            }
        )

    return entities_for_graph, mentions_for_graph, relationships_for_graph
