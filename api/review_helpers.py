"""
Pure review-workflow helpers ported from app/common.py, minus everything
there that touches Streamlit directly (get_logger's session-state
correlation id, reviewer_name's sidebar widget - see api/deps.py for the
header-based replacement). Kept separate from app/common.py so api/ has no
import path through anything that imports streamlit, which matters once
app/ is retired (see the plan's step 6).
"""

from __future__ import annotations

from datetime import datetime, timezone

from review import CandidateEntity, CandidateRelationship, HistoryEntry, WorkflowStatus
from review.repository import OntologyRepository

_TERMINAL_STATUSES = (WorkflowStatus.APPROVED, WorkflowStatus.REJECTED, WorkflowStatus.MERGED)

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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def status_label(status: WorkflowStatus) -> str:
    return STATUS_LABELS.get(status, status.value)


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


def is_publish_ready(entity_id: str, entities_by_id: dict[str, CandidateEntity]) -> bool:
    """Ported from app/pages/relationship_review.py's _is_publish_ready(): true
    if the entity is approved, or merged into an entity that is approved."""
    entity = entities_by_id.get(entity_id)
    if entity is None:
        return False
    if entity.status == WorkflowStatus.APPROVED:
        return True
    if entity.status == WorkflowStatus.MERGED and entity.merged_into:
        canonical = entities_by_id.get(entity.merged_into)
        return canonical is not None and canonical.status == WorkflowStatus.APPROVED
    return False


def is_ambiguous(entity: CandidateEntity) -> bool:
    return bool(entity.possible_meanings) and entity.status not in _TERMINAL_STATUSES


def find_entity(repo: OntologyRepository, entity_id: str) -> CandidateEntity | None:
    return next((e for e in repo.get_candidate_entities() if e.id == entity_id), None)


def find_relationship(repo: OntologyRepository, relationship_id: str) -> CandidateRelationship | None:
    return next((r for r in repo.get_candidate_relationships() if r.id == relationship_id), None)
