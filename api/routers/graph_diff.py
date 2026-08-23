"""
GET /api/graph-diff - one call to compute_graph_diff(repo, storage), shared
by the Graph Impact Analysis (counts) and Graph Difference View (detail
lists) pages, same as the two Streamlit pages already share the single
compute_graph_diff() result. Relationship rows are resolved to entity names
the same way app/pages/graph_difference_view.py's _rel_row() does.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api import deps
from providers.storage_provider import StorageProvider
from review.graph_diff import compute_graph_diff
from review.repository import OntologyRepository

router = APIRouter()


@router.get("/api/graph-diff")
def get_graph_diff(
    repo: OntologyRepository = Depends(deps.get_repository),
    storage: StorageProvider = Depends(deps.get_storage),
) -> dict:
    diff = compute_graph_diff(repo, storage)

    entity_name_by_id = {e.id: e.name for e in repo.get_candidate_entities()}
    baseline_graph = storage.read_graph_export()
    if baseline_graph:
        for e in baseline_graph["nodes"]["entities"]:
            entity_name_by_id.setdefault(e["id"], e["name"])

    def rel_row(r: dict) -> dict:
        return {
            "source": entity_name_by_id.get(r["source"], r["source"]),
            "relationship": r["relationship"],
            "target": entity_name_by_id.get(r["target"], r["target"]),
        }

    return {
        "counts": {
            "new_entities": len(diff.entities_added),
            "new_relationships": len(diff.relationships_added),
            "entities_merged": len(diff.entities_merged),
            "removed_total": len(diff.entities_removed) + len(diff.relationships_removed),
            "entity_count_delta": diff.entity_count_delta,
            "relationship_count_delta": diff.relationship_count_delta,
        },
        "entities_added": diff.entities_added,
        "entities_removed": diff.entities_removed,
        "entities_modified": [
            {
                "name": m["after"]["name"],
                "previous_name": m["before"].get("name", ""),
                "type": m["after"]["type"],
                "previous_type": m["before"].get("type", ""),
            }
            for m in diff.entities_modified
        ],
        "entities_merged": [{"name": m["name"], "merged_into_name": m["merged_into_name"]} for m in diff.entities_merged],
        "relationships_added": [rel_row(r) for r in diff.relationships_added],
        "relationships_removed": [rel_row(r) for r in diff.relationships_removed],
    }
