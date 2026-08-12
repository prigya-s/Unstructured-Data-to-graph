from __future__ import annotations

import streamlit as st

from common import get_storage

st.title("Production Graph")
st.caption(
    "Approved-only - this is the Gold-layer graph that is (or will be) live in Neo4j. "
    "Candidate entities and relationships that are still pending review never appear here."
)

storage = get_storage()
graph = storage.read_graph_export()

if not graph:
    st.info(
        "No Production Graph has been published yet. Approve entities on the Entity Review "
        "page, then use the Publish page to generate and load it."
    )
else:
    col1, col2 = st.columns(2)
    col1.metric("Approved Entities", graph["stats"]["entities"])
    col2.metric("Approved Relationships", graph["stats"]["entity_relationships"])

    st.subheader("Entities")
    entities = graph["nodes"]["entities"]
    if entities:
        st.dataframe(
            [{"Name": e["name"], "Type": e["type"]} for e in entities],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No approved entities yet.")

    st.subheader("Relationships")
    entity_name_by_id = {e["id"]: e["name"] for e in entities}
    relationships = graph["relationships"]["entity_relationships"]
    if relationships:
        st.dataframe(
            [
                {
                    "Source": entity_name_by_id.get(r["source"], r["source"]),
                    "Relationship": r["relationship"],
                    "Target": entity_name_by_id.get(r["target"], r["target"]),
                }
                for r in relationships
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No approved relationships yet.")
