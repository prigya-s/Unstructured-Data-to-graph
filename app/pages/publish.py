from __future__ import annotations

import streamlit as st

import providers
from common import get_repo
from config import load_config
from pipeline.context import PipelineContext
from pipeline.runner import PipelineRunner
from pipeline.stages.graph_stage import GraphStage
from pipeline.stages.ontology_stage import OntologyStage
from review import WorkflowStatus

_RUNNER = PipelineRunner([OntologyStage(), GraphStage()])


def _build_context() -> PipelineContext:
    config = load_config()
    return PipelineContext(
        config=config,
        storage=providers.get_storage_provider(config),
        document_source=providers.get_document_source(config),
        embedding_provider=providers.get_embedding_provider(config),
        approval_provider=providers.get_approval_provider(config),
        ontology_provider=providers.get_ontology_provider(config),
        graph_provider=providers.get_graph_provider(config),
    )

st.title("Publish")
st.caption("Only approved concepts and relationships are ever published. Rejected, pending, or ambiguous concepts are never included.")

repo = get_repo()
entities = repo.get_candidate_entities()
relationships = repo.get_candidate_relationships()

approved_entities = sum(1 for e in entities if e.status == WorkflowStatus.APPROVED)
approved_relationships = sum(1 for r in relationships if r.status == WorkflowStatus.APPROVED)
pending_entities = sum(1 for e in entities if e.status in (WorkflowStatus.NEW, WorkflowStatus.PENDING_REVIEW))
pending_relationships = sum(
    1 for r in relationships if r.status in (WorkflowStatus.NEW, WorkflowStatus.PENDING_REVIEW)
)

col1, col2, col3 = st.columns(3)
col1.metric("Approved Concepts", approved_entities)
col2.metric("Approved Relationships", approved_relationships)
col3.metric("Still Pending", pending_entities + pending_relationships)

if pending_entities or pending_relationships:
    st.warning(
        f"{pending_entities} concept(s) and {pending_relationships} relationship(s) are still "
        "pending review. Publishing will only include approved items."
    )

st.divider()
st.subheader("Step 1: Generate Approved Ontology")
st.caption("Writes the approved business glossary to the configured lakehouse storage.")
if st.button("Generate Approved Ontology"):
    try:
        ctx = _RUNNER.run_stage("ontology", _build_context())
        ontology = ctx.ontology_result
        st.success(
            f"Ontology generated with {ontology['stats']['total_entities']} concepts and "
            f"{ontology['stats']['total_relationships']} relationships."
        )
    except ValueError as exc:
        st.error(str(exc))

st.divider()
st.subheader("Step 2: Publish to Neo4j")
st.caption(
    "Loads only approved concepts and relationships into the graph database. Previously "
    "published items are updated in place - safe to run more than once."
)
if st.button("Generate Neo4j Graph", type="primary"):
    try:
        ctx = _RUNNER.run_stage("graph", _build_context())
        stats = ctx.publish_stats
        st.success(
            f"Published {stats['entities_loaded']} concepts and "
            f"{stats['relationships_loaded']} relationships to Neo4j."
        )
    except ValueError as exc:
        st.error(str(exc))
    except Exception as exc:  # noqa: BLE001 - surface connection errors as a friendly message
        st.error(
            "Could not publish to Neo4j. Ensure Neo4j Desktop is running and check the "
            f"credentials in your .env file. Details: {exc}"
        )
