from __future__ import annotations

import streamlit as st

from common import get_repo, get_storage
from review.graph_diff import compute_graph_diff

st.title("Graph Impact Analysis")
st.caption(
    "What changes in the Production Graph if every entity and relationship currently "
    "pending review were approved."
)

repo = get_repo()
storage = get_storage()
diff = compute_graph_diff(repo, storage)

col1, col2, col3, col4 = st.columns(4)
col1.metric("New Entities", len(diff.entities_added), delta=f"+{len(diff.entities_added)}")
col2.metric("New Relationships", len(diff.relationships_added), delta=f"+{len(diff.relationships_added)}")
col3.metric("Entities Merged", len(diff.entities_merged))
col4.metric("Entities/Relationships Removed", len(diff.entities_removed) + len(diff.relationships_removed))

st.divider()

col1, col2 = st.columns(2)
col1.metric("Net Entity Count Change", diff.entity_count_delta)
col2.metric("Net Relationship Count Change", diff.relationship_count_delta)

st.caption(
    "Net change accounts for entities added, removed, and merged away since the last "
    "Production Graph publish. See the Graph Difference View page for the full detail."
)
