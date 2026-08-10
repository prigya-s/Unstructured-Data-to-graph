from __future__ import annotations

import streamlit as st

from common import STATUS_ORDER, get_repo, status_label
from review import WorkflowStatus

st.title("Dashboard")

repo = get_repo()
entities = repo.get_candidate_entities()
relationships = repo.get_candidate_relationships()

source_documents = {doc for e in entities for doc in e.source_documents}

st.subheader("Overview")
cols = st.columns(3)
cols[0].metric("Documents Processed", len(source_documents))
cols[1].metric("Candidate Business Concepts", len(entities))
cols[2].metric("Candidate Relationships", len(relationships))

cols = st.columns(3)
cols[0].metric("Approved Concepts", sum(1 for e in entities if e.status == WorkflowStatus.APPROVED))
cols[1].metric("Approved Relationships", sum(1 for r in relationships if r.status == WorkflowStatus.APPROVED))
cols[2].metric(
    "Rejected Concepts",
    sum(1 for e in entities if e.status == WorkflowStatus.REJECTED)
    + sum(1 for r in relationships if r.status == WorkflowStatus.REJECTED),
)

pending_ambiguous = [
    e
    for e in entities
    if e.possible_meanings and e.status not in (WorkflowStatus.APPROVED, WorkflowStatus.REJECTED, WorkflowStatus.MERGED)
]
if pending_ambiguous:
    st.warning(
        f"{len(pending_ambiguous)} concept(s) have more than one possible meaning and need "
        "attention on the Ambiguity Resolution page."
    )

st.subheader("Concepts by Category and Status")
if entities:
    categories = sorted({e.entity_type for e in entities})
    rows = []
    for category in categories:
        row = {"Category": category}
        for status in STATUS_ORDER:
            row[status_label(status)] = sum(
                1 for e in entities if e.entity_type == category and e.status == status
            )
        rows.append(row)
    st.dataframe(rows, use_container_width=True, hide_index=True)
else:
    st.info("No candidate concepts yet. Run `python src/main.py ingest ./docs` first.")

st.subheader("Recent Activity")
history_rows = []
for entity in entities:
    for entry in entity.history:
        history_rows.append(
            {
                "Timestamp": entry.timestamp,
                "Concept/Relationship": entity.name,
                "Action": entry.action,
                "Reviewer": entry.reviewer,
                "Comment": entry.comment or "",
            }
        )
for rel in relationships:
    for entry in rel.history:
        history_rows.append(
            {
                "Timestamp": entry.timestamp,
                "Concept/Relationship": f"{rel.source_entity} -> {rel.target_entity}",
                "Action": entry.action,
                "Reviewer": entry.reviewer,
                "Comment": entry.comment or "",
            }
        )

history_rows.sort(key=lambda r: r["Timestamp"], reverse=True)
if history_rows:
    st.dataframe(history_rows[:10], use_container_width=True, hide_index=True)
else:
    st.info("No review activity yet.")
