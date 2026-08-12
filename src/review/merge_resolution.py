"""
Shared merge-resolution helpers.

Extracted from ontology_generator.py so candidate_graph.py and graph_diff.py
can resolve MERGED entities to their canonical survivor the same way the
approved-ontology path already does, without duplicating the logic.
"""

from __future__ import annotations

import logging

from .models import CandidateEntity, WorkflowStatus

logger = logging.getLogger("kg_local.merge_resolution")


def build_merge_map(entities: list[CandidateEntity]) -> dict[str, str]:
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


def resolve_entity_id(entity_id: str, merge_map: dict[str, str]) -> str:
    if entity_id in merge_map:
        resolved = merge_map[entity_id]
        if resolved in merge_map:
            logger.warning("Merge chain detected for %s -> %s; not following further", entity_id, resolved)
        return resolved
    return entity_id
