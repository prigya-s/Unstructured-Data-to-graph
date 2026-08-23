"""
Relationship Review endpoints - mirrors app/pages/relationship_review.py.
No merge, no bulk action on relationships (the Streamlit page has neither).
GET resolves source/target entity names and publish-readiness server-side,
same computation the Streamlit page did inline via entity_display_name()
and its local _is_publish_ready().
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api import deps
from api.review_helpers import add_history, entity_display_name, find_relationship, is_publish_ready, now_iso
from review import WorkflowStatus
from review.repository import OntologyRepository

router = APIRouter()


class SaveRelationshipBody(BaseModel):
    relationship_type: str
    comment: str | None = None


class ActionBody(BaseModel):
    comment: str | None = None


def _get_relationship_or_404(repo: OntologyRepository, relationship_id: str):
    relationship = find_relationship(repo, relationship_id)
    if relationship is None:
        raise HTTPException(status_code=404, detail=f"Relationship '{relationship_id}' not found")
    return relationship


def _to_row(relationship, repo: OntologyRepository) -> dict:
    entities_by_id = {e.id: e for e in repo.get_candidate_entities()}
    row = relationship.to_dict()
    row["source_name"] = entity_display_name(relationship.source_entity, entities_by_id)
    row["target_name"] = entity_display_name(relationship.target_entity, entities_by_id)
    row["publish_ready"] = is_publish_ready(relationship.source_entity, entities_by_id) and is_publish_ready(
        relationship.target_entity, entities_by_id
    )
    return row


@router.get("/api/relationships")
def list_relationships(repo: OntologyRepository = Depends(deps.get_repository)) -> list[dict]:
    return [_to_row(rel, repo) for rel in repo.get_candidate_relationships()]


@router.patch("/api/relationships/{relationship_id}/save")
def save_relationship(
    relationship_id: str,
    body: SaveRelationshipBody,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> dict:
    relationship = _get_relationship_or_404(repo, relationship_id)
    relationship.relationship_type = body.relationship_type
    add_history(relationship, reviewer, "edit", body.comment or "Relationship type updated.")
    repo.save_candidate_relationship(relationship)
    return _to_row(relationship, repo)


@router.patch("/api/relationships/{relationship_id}/approve")
def approve_relationship(
    relationship_id: str,
    body: ActionBody,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> dict:
    relationship = _get_relationship_or_404(repo, relationship_id)
    relationship.status = WorkflowStatus.APPROVED
    relationship.reviewer = reviewer
    relationship.review_timestamp = now_iso()
    add_history(relationship, reviewer, "approve", body.comment)
    repo.save_candidate_relationship(relationship)
    return _to_row(relationship, repo)


@router.patch("/api/relationships/{relationship_id}/reject")
def reject_relationship(
    relationship_id: str,
    body: ActionBody,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> dict:
    relationship = _get_relationship_or_404(repo, relationship_id)
    relationship.status = WorkflowStatus.REJECTED
    relationship.reviewer = reviewer
    relationship.review_timestamp = now_iso()
    add_history(relationship, reviewer, "reject", body.comment)
    repo.save_candidate_relationship(relationship)
    return _to_row(relationship, repo)
