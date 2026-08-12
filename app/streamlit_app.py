"""
Entity Review - Streamlit entry point.

Run with:
    streamlit run app/streamlit_app.py

Built with Streamlit so it can later be deployed as a Databricks App with
no code changes - see README.md "Databricks App Deployment" section.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _APP_DIR.parent

sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_APP_DIR))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(_PROJECT_ROOT / ".env")

st.set_page_config(
    page_title="Entity Review",
    page_icon="\U0001F4CB",
    layout="wide",
    initial_sidebar_state="expanded",
)

pg = st.navigation(
    [
        st.Page(_APP_DIR / "pages" / "dashboard.py", title="Dashboard", default=True),
        st.Page(_APP_DIR / "pages" / "entity_review.py", title="Entity Review"),
        st.Page(_APP_DIR / "pages" / "relationship_review.py", title="Relationships"),
        st.Page(_APP_DIR / "pages" / "ambiguity_resolution.py", title="Ambiguity Resolution"),
        st.Page(_APP_DIR / "pages" / "candidate_graph.py", title="Candidate Graph"),
        st.Page(_APP_DIR / "pages" / "graph_impact_analysis.py", title="Graph Impact Analysis"),
        st.Page(_APP_DIR / "pages" / "graph_difference_view.py", title="Graph Difference View"),
        st.Page(_APP_DIR / "pages" / "ontology_preview.py", title="Ontology Preview"),
        st.Page(_APP_DIR / "pages" / "publish.py", title="Publish"),
        st.Page(_APP_DIR / "pages" / "production_graph.py", title="Production Graph"),
        st.Page(_APP_DIR / "pages" / "chat.py", title="Ask the Knowledge Graph"),
    ]
)
pg.run()
