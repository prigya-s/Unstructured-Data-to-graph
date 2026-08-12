from __future__ import annotations

import streamlit as st

from common import (
    add_history,
    entity_display_name,
    format_confidence,
    get_logger,
    get_repo,
    now_iso,
    reviewer_name,
    status_label,
)
from review import WorkflowStatus

logger = get_logger()

st.title("Relationships")
st.caption("Review how entities relate to each other, e.g. one service depending on another.")

repo = get_repo()
reviewer = reviewer_name()
entities_by_id = {e.id: e for e in repo.get_candidate_entities()}
all_relationships = repo.get_candidate_relationships()


def _is_publish_ready(entity_id: str) -> bool:
    entity = entities_by_id.get(entity_id)
    if entity is None:
        return False
    if entity.status == WorkflowStatus.APPROVED:
        return True
    if entity.status == WorkflowStatus.MERGED and entity.merged_into:
        canonical = entities_by_id.get(entity.merged_into)
        return canonical is not None and canonical.status == WorkflowStatus.APPROVED
    return False

with st.sidebar:
    st.subheader("Filters")
    status_options = sorted({r.status for r in all_relationships}, key=lambda s: s.value)
    selected_statuses = st.multiselect(
        "Status", options=status_options, default=status_options, format_func=status_label
    )
    type_options = sorted({r.relationship_type for r in all_relationships})
    selected_types = st.multiselect("Relationship Type", options=type_options, default=type_options)

filtered = [
    r for r in all_relationships if r.status in selected_statuses and r.relationship_type in selected_types
]

st.write(f"Showing {len(filtered)} of {len(all_relationships)} relationships.")

if not filtered:
    st.info("No relationships match the current filters.")

for rel in filtered:
    source_name = entity_display_name(rel.source_entity, entities_by_id)
    target_name = entity_display_name(rel.target_entity, entities_by_id)
    header = f"{source_name}  →  {rel.relationship_type}  →  {target_name}  ·  {status_label(rel.status)}"
    with st.expander(header):
        left, right = st.columns([2, 1])

        with left:
            st.markdown("**Relationship**")
            new_relationship_type = st.text_input(
                "Relationship",
                value=rel.relationship_type,
                key=f"reltype_{rel.id}",
                label_visibility="collapsed",
            )
            st.markdown(f"**Source Term:** {source_name}")
            st.markdown(f"**Target Term:** {target_name}")
            if rel.evidence:
                st.markdown("**Evidence from Source Documents**")
                for snippet in rel.evidence:
                    st.markdown(f"> {snippet}")
            if rel.status == WorkflowStatus.APPROVED and not (
                _is_publish_ready(rel.source_entity) and _is_publish_ready(rel.target_entity)
            ):
                st.warning(
                    "This relationship is approved but will not be published yet - both "
                    f"'{source_name}' and '{target_name}' must also be approved entities."
                )

        with right:
            st.metric("Confidence", format_confidence(rel.confidence_score))
            st.markdown(f"**Status:** {status_label(rel.status)}")

            comment = st.text_input("Comment (optional)", key=f"comment_{rel.id}")

            if st.button("Save Changes", key=f"save_{rel.id}"):
                rel.relationship_type = new_relationship_type
                add_history(rel, reviewer, "edit", comment or "Relationship type updated.")
                repo.save_candidate_relationship(rel)
                st.rerun()

            if rel.status != WorkflowStatus.APPROVED:
                if st.button("Approve", key=f"approve_{rel.id}", type="primary"):
                    rel.status = WorkflowStatus.APPROVED
                    rel.reviewer = reviewer
                    rel.review_timestamp = now_iso()
                    add_history(rel, reviewer, "approve", comment or None)
                    repo.save_candidate_relationship(rel)
                    logger.info("Relationship %s approved by %s", rel.id, reviewer)
                    st.rerun()

            if rel.status != WorkflowStatus.REJECTED:
                if st.button("Reject", key=f"reject_{rel.id}"):
                    rel.status = WorkflowStatus.REJECTED
                    rel.reviewer = reviewer
                    rel.review_timestamp = now_iso()
                    add_history(rel, reviewer, "reject", comment or None)
                    repo.save_candidate_relationship(rel)
                    logger.info("Relationship %s rejected by %s", rel.id, reviewer)
                    st.rerun()

            if rel.history:
                st.markdown("**History**")
                for h in reversed(rel.history):
                    comment_text = f" - {h.comment}" if h.comment else ""
                    st.caption(f"{h.timestamp} · {h.reviewer} · {h.action}{comment_text}")
