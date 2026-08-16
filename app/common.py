"""
Shared helpers for the Streamlit review app. Imported by every page.

Business-friendly language only - never use the words "Node", "Edge",
"Cypher", or "Ontology Class" in UI copy.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import streamlit as st

import providers
from config import load_config
from graph.startup import initialize_graph
from observability.logging_setup import configure_streamlit_logging, set_correlation_id
from review import CandidateEntity, HistoryEntry, WorkflowStatus

LOGGER_NAME = "kg_local"
_graph_initialized = False


def get_logger() -> logging.Logger:
    """Ensures process-wide structured logging is configured (no-op after
    the first call in this process), stamps the current Streamlit session's
    correlation id onto the logging context for this script rerun, and
    returns the shared "kg_local" logger - the same logger name/format
    main.py's CLI runs use, so file logs from either surface can be
    correlated the same way."""
    configure_streamlit_logging(load_config())
    if "correlation_id" not in st.session_state:
        st.session_state.correlation_id = str(uuid.uuid4())
    set_correlation_id(st.session_state.correlation_id)
    return logging.getLogger(LOGGER_NAME)

STATUS_LABELS: dict[WorkflowStatus, str] = {
    WorkflowStatus.NEW: "New",
    WorkflowStatus.PENDING_REVIEW: "Pending Review",
    WorkflowStatus.APPROVED: "Approved",
    WorkflowStatus.REJECTED: "Rejected",
    WorkflowStatus.MERGED: "Merged",
}

STATUS_ORDER = [
    WorkflowStatus.NEW,
    WorkflowStatus.PENDING_REVIEW,
    WorkflowStatus.APPROVED,
    WorkflowStatus.REJECTED,
    WorkflowStatus.MERGED,
]


def get_repo():
    return providers.get_approval_provider(load_config())


def get_storage():
    return providers.get_storage_provider(load_config())


def get_auth_provider():
    return providers.get_auth_provider(load_config())


def get_graph_provider():
    """Builds this run's GraphProvider and, on the first call in this
    process only, connects and idempotently ensures constraints/indexes
    exist - same first-call-wins guard as configure_streamlit_logging, so
    Streamlit reruns (and repeated per-page calls) don't repeat the
    connect/constraint/index round trips on every script rerun."""
    global _graph_initialized
    provider = providers.get_graph_provider(load_config())
    if not _graph_initialized:
        initialize_graph(provider)
        _graph_initialized = True
    return provider


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def status_label(status: WorkflowStatus) -> str:
    return STATUS_LABELS.get(status, status.value)


def reviewer_name() -> str:
    return get_auth_provider().current_user().display_name


def format_confidence(score: float) -> str:
    return f"{round(score * 100)}%"


def entity_display_name(entity_id: str, entities_by_id: dict[str, CandidateEntity]) -> str:
    entity = entities_by_id.get(entity_id)
    if entity is None:
        return entity_id
    if entity.status == WorkflowStatus.MERGED and entity.merged_into:
        canonical = entities_by_id.get(entity.merged_into)
        canonical_name = canonical.name if canonical else entity.merged_into
        return f"{entity.name} (merged into {canonical_name})"
    return entity.name


def add_history(obj, reviewer: str, action: str, comment: str | None = None) -> None:
    obj.history.append(HistoryEntry(timestamp=now_iso(), reviewer=reviewer, action=action, comment=comment))
