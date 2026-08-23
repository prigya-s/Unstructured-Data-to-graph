"""GET /api/dashboard - same aggregation app/pages/dashboard.py does inline
over repo.get_candidate_entities()/get_candidate_relationships()."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api import deps
from api.review_helpers import STATUS_ORDER, status_label
from review import WorkflowStatus
from review.repository import OntologyRepository

router = APIRouter()


@router.get("/api/dashboard")
def get_dashboard(repo: OntologyRepository = Depends(deps.get_repository)) -> dict:
    entities = repo.get_candidate_entities()
    relationships = repo.get_candidate_relationships()

    source_documents = {doc for e in entities for doc in e.source_documents}

    pending_ambiguous = [
        e
        for e in entities
        if e.possible_meanings
        and e.status not in (WorkflowStatus.APPROVED, WorkflowStatus.REJECTED, WorkflowStatus.MERGED)
    ]

    categories = sorted({e.entity_type for e in entities})
    entities_by_category_status = [
        {
            "category": category,
            **{
                status_label(status): sum(1 for e in entities if e.entity_type == category and e.status == status)
                for status in STATUS_ORDER
            },
        }
        for category in categories
    ]

    history_rows = [
        {
            "timestamp": entry.timestamp,
            "subject": entity.name,
            "action": entry.action,
            "reviewer": entry.reviewer,
            "comment": entry.comment or "",
        }
        for entity in entities
        for entry in entity.history
    ] + [
        {
            "timestamp": entry.timestamp,
            "subject": f"{rel.source_entity} -> {rel.target_entity}",
            "action": entry.action,
            "reviewer": entry.reviewer,
            "comment": entry.comment or "",
        }
        for rel in relationships
        for entry in rel.history
    ]
    history_rows.sort(key=lambda r: r["timestamp"], reverse=True)

    return {
        "documents_processed": len(source_documents),
        "candidate_entities": len(entities),
        "candidate_relationships": len(relationships),
        "approved_entities": sum(1 for e in entities if e.status == WorkflowStatus.APPROVED),
        "approved_relationships": sum(1 for r in relationships if r.status == WorkflowStatus.APPROVED),
        "rejected_total": sum(1 for e in entities if e.status == WorkflowStatus.REJECTED)
        + sum(1 for r in relationships if r.status == WorkflowStatus.REJECTED),
        "pending_ambiguous_count": len(pending_ambiguous),
        "entities_by_category_status": entities_by_category_status,
        "recent_activity": history_rows[:10],
    }
