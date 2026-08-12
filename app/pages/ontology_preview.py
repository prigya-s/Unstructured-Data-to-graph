from __future__ import annotations

import streamlit as st

from common import get_repo
from review import WorkflowStatus
from review.ontology_generator import generate_approved_ontology

st.title("Ontology Preview")
st.caption("This is what will be published as the shared business ontology - only approved entities and relationships appear here.")

repo = get_repo()
entities = repo.get_candidate_entities()
relationships = repo.get_candidate_relationships()

pending_count = sum(
    1 for e in entities if e.status in (WorkflowStatus.NEW, WorkflowStatus.PENDING_REVIEW)
) + sum(1 for r in relationships if r.status in (WorkflowStatus.NEW, WorkflowStatus.PENDING_REVIEW))

if pending_count:
    st.warning(f"{pending_count} entity(ies)/relationship(s) are still pending review and will not be included below.")

if st.button("Regenerate Preview", type="primary"):
    st.session_state["ontology_preview"] = generate_approved_ontology(repo)

if "ontology_preview" not in st.session_state:
    st.session_state["ontology_preview"] = generate_approved_ontology(repo)

ontology = st.session_state["ontology_preview"]

st.caption(f"Last generated: {ontology['generated_at']}")

col1, col2 = st.columns(2)
col1.metric("Approved Entities", ontology["stats"]["total_entities"])
col2.metric("Approved Relationships", ontology["stats"]["total_relationships"])

tab1, tab2, tab3 = st.tabs(["Entities", "Relationships", "Full Details"])

with tab1:
    if ontology["entities"]:
        st.dataframe(
            [
                {
                    "Entity Name": e["name"],
                    "Category": e["category"],
                    "Definition": e["definition"],
                    "Confidence": f"{round(e['confidence_score'] * 100)}%",
                    "Source Documents": ", ".join(e["source_documents"]),
                }
                for e in ontology["entities"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No approved entities yet.")

with tab2:
    if ontology["relationships"]:
        st.dataframe(
            [
                {
                    "Source Term": r["source_name"],
                    "Relationship": r["relationship_type"],
                    "Target Term": r["target_name"],
                    "Confidence": f"{round(r['confidence_score'] * 100)}%",
                }
                for r in ontology["relationships"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No approved relationships yet.")

with tab3:
    st.json(ontology)
