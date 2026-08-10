from __future__ import annotations

import streamlit as st

from common import add_history, get_repo, now_iso, reviewer_name
from review import WorkflowStatus

st.title("Ambiguity Resolution")
st.caption(
    "Some business terms can mean more than one thing. Pick the meaning that applies here so "
    "reviewers downstream see the right definition."
)

repo = get_repo()
reviewer = reviewer_name()

entities = repo.get_candidate_entities()
ambiguous = [
    e
    for e in entities
    if e.possible_meanings
    and e.status not in (WorkflowStatus.APPROVED, WorkflowStatus.REJECTED, WorkflowStatus.MERGED)
]

if not ambiguous:
    st.success("No ambiguous concepts require resolution right now.")

for entity in ambiguous:
    with st.container(border=True):
        st.subheader(entity.name)
        st.markdown(f"**Category:** {entity.entity_type}")
        if entity.evidence:
            st.markdown("**Evidence from Source Documents**")
            for snippet in entity.evidence:
                st.markdown(f"> {snippet}")

        st.markdown("**Possible Interpretations**")
        options = list(entity.possible_meanings) + ["None of the above - I will describe it myself"]
        choice = st.radio(
            "Select the meaning that applies", options=options, key=f"meaning_{entity.id}"
        )

        custom_meaning = ""
        if choice == options[-1]:
            custom_meaning = st.text_input("Describe the meaning", key=f"custom_{entity.id}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Confirm Meaning", key=f"confirm_{entity.id}"):
                chosen = custom_meaning.strip() if choice == options[-1] else choice
                if chosen:
                    entity.business_meaning = chosen
                    entity.definition = f"{entity.name} refers to: {chosen}."
                    entity.possible_meanings = []
                    add_history(entity, reviewer, "disambiguate", f"Ambiguity resolved: selected '{chosen}'.")
                    repo.save_candidate_entity(entity)
                    st.rerun()
                else:
                    st.error("Please describe the meaning before confirming.")
        with col2:
            if st.button("Dismiss Ambiguity", key=f"dismiss_{entity.id}"):
                entity.possible_meanings = []
                add_history(entity, reviewer, "disambiguate", "Ambiguity dismissed - no interpretation change needed.")
                repo.save_candidate_entity(entity)
                st.rerun()

        st.caption(
            "Confirming a meaning does not approve this concept - go to Business Concepts to approve or reject it."
        )
