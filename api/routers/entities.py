"""
Entity Review endpoints - mirrors app/pages/entity_review.py's mutation
actions exactly (save definition/meaning, approve, reject, merge, bulk
approve). The page does status/category filtering client-side over the
full GET /api/entities list, same as the Streamlit multiselects did.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api import deps
from api.review_helpers import add_history, find_entity, now_iso
from review import WorkflowStatus
from review.repository import OntologyRepository

router = APIRouter()

_TERMINAL_STATUSES = (WorkflowStatus.APPROVED, WorkflowStatus.REJECTED, WorkflowStatus.MERGED)


class SaveEntityBody(BaseModel):
    name: str
    definition: str
    business_meaning: str
    comment: str | None = None


class ActionBody(BaseModel):
    comment: str | None = None


class MergeBody(BaseModel):
    target_id: str
    comment: str | None = None


class BulkApproveBody(BaseModel):
    ids: list[str]


def _get_entity_or_404(repo: OntologyRepository, entity_id: str):
    entity = find_entity(repo, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    return entity


@router.get("/api/entities")
def list_entities(repo: OntologyRepository = Depends(deps.get_repository)) -> list[dict]:
    return [e.to_dict() for e in repo.get_candidate_entities()]


@router.patch("/api/entities/{entity_id}/save")
def save_entity(
    entity_id: str,
    body: SaveEntityBody,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> dict:
    entity = _get_entity_or_404(repo, entity_id)
    entity.name = body.name
    entity.definition = body.definition
    entity.business_meaning = body.business_meaning
    add_history(entity, reviewer, "edit", body.comment or "Name/definition/business meaning updated.")
    repo.save_candidate_entity(entity)
    return entity.to_dict()


@router.patch("/api/entities/{entity_id}/approve")
def approve_entity(
    entity_id: str,
    body: ActionBody,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> dict:
    entity = _get_entity_or_404(repo, entity_id)
    entity.status = WorkflowStatus.APPROVED
    entity.reviewer = reviewer
    entity.review_timestamp = now_iso()
    add_history(entity, reviewer, "approve", body.comment)
    repo.save_candidate_entity(entity)
    return entity.to_dict()


@router.patch("/api/entities/{entity_id}/reject")
def reject_entity(
    entity_id: str,
    body: ActionBody,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> dict:
    entity = _get_entity_or_404(repo, entity_id)
    entity.status = WorkflowStatus.REJECTED
    entity.reviewer = reviewer
    entity.review_timestamp = now_iso()
    add_history(entity, reviewer, "reject", body.comment)
    repo.save_candidate_entity(entity)
    return entity.to_dict()


@router.patch("/api/entities/{entity_id}/merge")
def merge_entity(
    entity_id: str,
    body: MergeBody,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> dict:
    entity = _get_entity_or_404(repo, entity_id)
    target = _get_entity_or_404(repo, body.target_id)
    entity.merged_into = target.id
    entity.status = WorkflowStatus.MERGED
    add_history(entity, reviewer, "merge", f"Merged into '{target.name}'.")
    repo.save_candidate_entity(entity)
    return entity.to_dict()


@router.post("/api/entities/bulk-approve")
def bulk_approve_entities(
    body: BulkApproveBody,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> list[dict]:
    by_id = {e.id: e for e in repo.get_candidate_entities()}
    updated = []
    for entity_id in body.ids:
        entity = by_id.get(entity_id)
        if entity is None or entity.status in _TERMINAL_STATUSES:
            continue
        entity.status = WorkflowStatus.APPROVED
        entity.reviewer = reviewer
        entity.review_timestamp = now_iso()
        add_history(entity, reviewer, "approve", "Bulk approved.")
        updated.append(entity)
    repo.save_candidate_entities(updated)
    return [e.to_dict() for e in updated]
