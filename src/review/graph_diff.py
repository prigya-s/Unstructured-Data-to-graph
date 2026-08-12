"""
Graph Change Analysis: what changes in the Gold-layer Production Graph if
every currently-pending entity/relationship were approved.

Current Production Graph (baseline) = StorageProvider.read_graph_export()
(the last published Gold graph; an empty graph if never published).

Proposed Graph = the hypothetical result of approving everything not yet
rejected: entities with status in {APPROVED, PENDING_REVIEW, NEW}, with
MERGED entities resolved to their canonical survivor via the shared
merge_resolution helpers (same resolution used by ontology_generator and
candidate_graph).

This one function backs both the Graph Impact Analysis screen (summary
counts) and the Graph Difference View screen (the same object's detail
lists) - there is no second diff implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from providers.storage_provider import StorageProvider

from .merge_resolution import build_merge_map, resolve_entity_id
from .models import WorkflowStatus
from .repository import OntologyRepository

_LIVE_STATUSES = (WorkflowStatus.APPROVED, WorkflowStatus.PENDING_REVIEW, WorkflowStatus.NEW)


@dataclass
class GraphDiff:
    entities_added: list[dict] = field(default_factory=list)
    entities_removed: list[dict] = field(default_factory=list)
    entities_modified: list[dict] = field(default_factory=list)
    entities_merged: list[dict] = field(default_factory=list)
    relationships_added: list[dict] = field(default_factory=list)
    relationships_removed: list[dict] = field(default_factory=list)

    @property
    def entity_count_delta(self) -> int:
        return len(self.entities_added) - len(self.entities_removed) - len(self.entities_merged)

    @property
    def relationship_count_delta(self) -> int:
        return len(self.relationships_added) - len(self.relationships_removed)


def compute_graph_diff(repository: OntologyRepository, storage: StorageProvider) -> GraphDiff:
    baseline = storage.read_graph_export()
    baseline_entities: dict[str, dict] = {}
    baseline_relationship_keys: dict[tuple[str, str, str], dict] = {}
    if baseline:
        baseline_entities = {e["id"]: e for e in baseline["nodes"]["entities"]}
        baseline_relationship_keys = {
            (r["source"], r["relationship"], r["target"]): r
            for r in baseline["relationships"]["entity_relationships"]
        }

    all_entities = repository.get_candidate_entities()
    merge_map = build_merge_map(all_entities)

    live_entities = [e for e in all_entities if e.status in _LIVE_STATUSES]
    proposed_entities = {
        e.id: {"id": e.id, "name": e.name, "type": e.entity_type} for e in live_entities
    }

    entities_merged = [
        {
            "id": e.id,
            "name": e.name,
            "merged_into": merge_map[e.id],
            "merged_into_name": proposed_entities.get(merge_map[e.id], {}).get("name", merge_map[e.id]),
        }
        for e in all_entities
        if e.status == WorkflowStatus.MERGED and e.id in merge_map and e.id in baseline_entities
    ]
    merged_away_ids = {m["id"] for m in entities_merged}

    baseline_ids = set(baseline_entities.keys())
    proposed_ids = set(proposed_entities.keys())

    entities_added = [proposed_entities[eid] for eid in sorted(proposed_ids - baseline_ids)]
    entities_removed = [
        baseline_entities[eid]
        for eid in sorted(baseline_ids - proposed_ids)
        if eid not in merged_away_ids
    ]
    entities_modified = []
    for eid in sorted(baseline_ids & proposed_ids):
        before = baseline_entities[eid]
        after = proposed_entities[eid]
        if before.get("name") != after["name"] or before.get("type") != after["type"]:
            entities_modified.append({"id": eid, "before": before, "after": after})

    live_relationships = [r for r in repository.get_candidate_relationships() if r.status in _LIVE_STATUSES]
    proposed_relationship_keys: dict[tuple[str, str, str], dict] = {}
    for rel in live_relationships:
        source_id = resolve_entity_id(rel.source_entity, merge_map)
        target_id = resolve_entity_id(rel.target_entity, merge_map)
        if source_id == target_id:
            continue
        if source_id not in proposed_entities or target_id not in proposed_entities:
            continue
        key = (source_id, rel.relationship_type, target_id)
        proposed_relationship_keys[key] = {
            "source": source_id,
            "relationship": rel.relationship_type,
            "target": target_id,
        }

    baseline_rel_set = set(baseline_relationship_keys.keys())
    proposed_rel_set = set(proposed_relationship_keys.keys())

    relationships_added = [proposed_relationship_keys[k] for k in sorted(proposed_rel_set - baseline_rel_set)]
    relationships_removed = [baseline_relationship_keys[k] for k in sorted(baseline_rel_set - proposed_rel_set)]

    return GraphDiff(
        entities_added=entities_added,
        entities_removed=entities_removed,
        entities_modified=entities_modified,
        entities_merged=entities_merged,
        relationships_added=relationships_added,
        relationships_removed=relationships_removed,
    )
