from __future__ import annotations

import streamlit as st

from common import add_history, format_confidence, get_logger, get_repo, now_iso, reviewer_name, status_label
from review import WorkflowStatus

logger = get_logger()

st.title("Entity Review")
st.caption("Review the entities found in your documents. Approve the ones that belong in "
           "the shared business glossary, reject the ones that don't, and merge duplicates.")

repo = get_repo()
reviewer = reviewer_name()
all_entities = repo.get_candidate_entities()

with st.sidebar:
    st.subheader("Filters")
    status_options = sorted({e.status for e in all_entities}, key=lambda s: s.value)
    selected_statuses = st.multiselect(
        "Status",
        options=status_options,
        default=status_options,
        format_func=status_label,
    )
    category_options = sorted({e.entity_type for e in all_entities})
    selected_categories = st.multiselect("Category", options=category_options, default=category_options)

filtered = [
    e for e in all_entities if e.status in selected_statuses and e.entity_type in selected_categories
]

st.write(f"Showing {len(filtered)} of {len(all_entities)} entities.")

approved_entities = [e for e in all_entities if e.status == WorkflowStatus.APPROVED]

if not filtered:
    st.info("No entities match the current filters.")

for entity in filtered:
    header = f"{entity.name}  ·  {entity.entity_type}  ·  {status_label(entity.status)}"
    with st.expander(header):
        left, right = st.columns([2, 1])

        with left:
            st.markdown("**Suggested Definition**")
            new_definition = st.text_area(
                "Definition", value=entity.definition, key=f"def_{entity.id}", label_visibility="collapsed"
            )
            st.markdown("**Business Meaning**")
            new_meaning = st.text_area(
                "Business Meaning",
                value=entity.business_meaning,
                key=f"meaning_{entity.id}",
                label_visibility="collapsed",
            )
            if entity.possible_meanings:
                st.markdown(f"**Related Terms / Possible Meanings:** {', '.join(entity.possible_meanings)}")
            if entity.evidence:
                st.markdown("**Evidence from Source Documents**")
                for snippet in entity.evidence:
                    st.markdown(f"> {snippet}")
            if entity.source_documents:
                st.markdown(f"**Source Documents:** {', '.join(entity.source_documents)}")

        with right:
            st.metric("Confidence Score", format_confidence(entity.confidence_score))
            st.markdown(f"**Status:** {status_label(entity.status)}")
            if entity.reviewer:
                st.markdown(f"**Last reviewed by:** {entity.reviewer}")

            comment = st.text_input("Comment (optional)", key=f"comment_{entity.id}")

            if st.button("Save Definition Changes", key=f"save_{entity.id}"):
                entity.definition = new_definition
                entity.business_meaning = new_meaning
                add_history(entity, reviewer, "edit", comment or "Definition/business meaning updated.")
                repo.save_candidate_entity(entity)
                st.rerun()

            if entity.status != WorkflowStatus.APPROVED:
                if st.button("Approve", key=f"approve_{entity.id}", type="primary"):
                    entity.status = WorkflowStatus.APPROVED
                    entity.reviewer = reviewer
                    entity.review_timestamp = now_iso()
                    add_history(entity, reviewer, "approve", comment or None)
                    repo.save_candidate_entity(entity)
                    logger.info("Entity %s approved by %s", entity.id, reviewer)
                    st.rerun()

            if entity.status != WorkflowStatus.REJECTED:
                if st.button("Reject", key=f"reject_{entity.id}"):
                    entity.status = WorkflowStatus.REJECTED
                    entity.reviewer = reviewer
                    entity.review_timestamp = now_iso()
                    add_history(entity, reviewer, "reject", comment or None)
                    repo.save_candidate_entity(entity)
                    logger.info("Entity %s rejected by %s", entity.id, reviewer)
                    st.rerun()

            merge_targets = [e for e in approved_entities if e.id != entity.id]
            if merge_targets and entity.status != WorkflowStatus.MERGED:
                target_name = st.selectbox(
                    "Merge With Existing Entity",
                    options=["-- select an entity --"] + [t.name for t in merge_targets],
                    key=f"merge_target_{entity.id}",
                )
                if target_name != "-- select an entity --" and st.button(
                    "Confirm Merge", key=f"merge_{entity.id}"
                ):
                    target = next(t for t in merge_targets if t.name == target_name)
                    entity.merged_into = target.id
                    entity.status = WorkflowStatus.MERGED
                    add_history(entity, reviewer, "merge", f"Merged into '{target.name}'.")
                    repo.save_candidate_entity(entity)
                    logger.info("Entity %s merged into %s by %s", entity.id, target.id, reviewer)
                    st.rerun()

            if entity.history:
                st.markdown("**History**")
                for h in reversed(entity.history):
                    comment = f" - {h.comment}" if h.comment else ""
                    st.caption(f"{h.timestamp} · {h.reviewer} · {h.action}{comment}")
