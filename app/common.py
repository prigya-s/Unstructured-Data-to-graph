"""
Shared helpers for the Streamlit review app. Imported by every page.

Business-friendly language only - never use the words "Node", "Edge",
"Cypher", or "Ontology Class" in UI copy.
"""

from __future__ import annotations

from datetime import datetime, timezone

import providers
from config import load_config
from review import CandidateEntity, HistoryEntry, WorkflowStatus

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


def get_auth_provider():
    return providers.get_auth_provider(load_config())


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
