"""
Ambiguity Resolution endpoints - mirrors app/pages/ambiguity_resolution.py.
An entity is "ambiguous" while it has possible_meanings and hasn't reached
a terminal status (approved/rejected/merged) - see review_helpers.is_ambiguous().
Confirming or dismissing clears possible_meanings but never changes status;
confirming a meaning does not approve the entity.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api import deps
from api.review_helpers import add_history, find_entity, is_ambiguous
from review.repository import OntologyRepository

router = APIRouter()


class ConfirmBody(BaseModel):
    chosen: str


def _get_entity_or_404(repo: OntologyRepository, entity_id: str):
    entity = find_entity(repo, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")
    return entity


@router.get("/api/ambiguity")
def list_ambiguous(repo: OntologyRepository = Depends(deps.get_repository)) -> list[dict]:
    return [e.to_dict() for e in repo.get_candidate_entities() if is_ambiguous(e)]


@router.patch("/api/ambiguity/{entity_id}/confirm")
def confirm_ambiguity(
    entity_id: str,
    body: ConfirmBody,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> dict:
    entity = _get_entity_or_404(repo, entity_id)
    chosen = body.chosen.strip()
    if not chosen:
        raise HTTPException(status_code=400, detail="chosen meaning is required")
    entity.business_meaning = chosen
    entity.definition = f"{entity.name} refers to: {chosen}."
    entity.possible_meanings = []
    add_history(entity, reviewer, "disambiguate", f"Ambiguity resolved: selected '{chosen}'.")
    repo.save_candidate_entity(entity)
    return entity.to_dict()


@router.patch("/api/ambiguity/{entity_id}/dismiss")
def dismiss_ambiguity(
    entity_id: str,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> dict:
    entity = _get_entity_or_404(repo, entity_id)
    entity.possible_meanings = []
    add_history(entity, reviewer, "disambiguate", "Ambiguity dismissed - no interpretation change needed.")
    repo.save_candidate_entity(entity)
    return entity.to_dict()
