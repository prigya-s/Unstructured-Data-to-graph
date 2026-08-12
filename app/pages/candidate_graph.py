from __future__ import annotations

import streamlit as st

from common import get_repo
from review.candidate_graph import build_candidate_graph

st.title("Candidate Graph")
st.caption(
    "Not yet approved - this reflects the extraction engine's current understanding of "
    "your documents, including entities and relationships still pending review."
)

repo = get_repo()

if st.button("Refresh", type="primary"):
    st.session_state["candidate_graph"] = build_candidate_graph(repo)

if "candidate_graph" not in st.session_state:
    st.session_state["candidate_graph"] = build_candidate_graph(repo)

graph = st.session_state["candidate_graph"]

col1, col2 = st.columns(2)
col1.metric("Candidate Entities", graph["stats"]["entities"])
col2.metric("Candidate Relationships", graph["stats"]["entity_relationships"])

st.subheader("Entities")
entities = graph["nodes"]["entities"]
if entities:
    st.dataframe(
        [{"Name": e["name"], "Type": e["type"]} for e in entities],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No candidate entities yet. Run `python src/main.py ingest ./docs` first.")

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
    st.info("No candidate relationships yet.")
