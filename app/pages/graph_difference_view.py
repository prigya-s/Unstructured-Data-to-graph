from __future__ import annotations

import streamlit as st

from common import get_repo, get_storage
from review.graph_diff import compute_graph_diff

st.title("Graph Difference View")
st.caption(
    "Current Production Graph -> Proposed Graph if all pending entities and relationships "
    "were approved."
)

repo = get_repo()
storage = get_storage()
diff = compute_graph_diff(repo, storage)

entity_name_by_id = {e.id: e.name for e in repo.get_candidate_entities()}
baseline_graph = storage.read_graph_export()
if baseline_graph:
    for e in baseline_graph["nodes"]["entities"]:
        entity_name_by_id.setdefault(e["id"], e["name"])


def _rel_row(r: dict) -> dict:
    return {
        "Source": entity_name_by_id.get(r["source"], r["source"]),
        "Relationship": r["relationship"],
        "Target": entity_name_by_id.get(r["target"], r["target"]),
    }


st.subheader("Added Entities")
if diff.entities_added:
    st.dataframe(
        [{"Name": e["name"], "Type": e["type"]} for e in diff.entities_added],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No new entities.")

st.subheader("Removed Entities")
if diff.entities_removed:
    st.dataframe(
        [{"Name": e["name"], "Type": e["type"]} for e in diff.entities_removed],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No removed entities.")

st.subheader("Modified Entities")
if diff.entities_modified:
    st.dataframe(
        [
            {
                "Name": m["after"]["name"],
                "Previous Name": m["before"].get("name", ""),
                "Type": m["after"]["type"],
                "Previous Type": m["before"].get("type", ""),
            }
            for m in diff.entities_modified
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No modified entities.")

st.subheader("Merged Entities")
if diff.entities_merged:
    st.dataframe(
        [{"Name": m["name"], "Merged Into": m["merged_into_name"]} for m in diff.entities_merged],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No entities merged since the last publish.")

st.divider()

st.subheader("Added Relationships")
if diff.relationships_added:
    st.dataframe(
        [_rel_row(r) for r in diff.relationships_added],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No new relationships.")

st.subheader("Removed Relationships")
if diff.relationships_removed:
    st.dataframe(
        [_rel_row(r) for r in diff.relationships_removed],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No removed relationships.")
