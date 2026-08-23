"""GET/POST /api/ontology/preview - wraps generate_approved_ontology(repo),
same call app/pages/ontology_preview.py makes on load and on its "Regenerate
Preview" button. Both routes do the same thing; POST exists to make the
regenerate action an explicit user-triggered call from the React page
(GET is also safe to call repeatedly - generate_approved_ontology has no
caching to invalidate)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api import deps
from review import WorkflowStatus
from review.ontology_generator import generate_approved_ontology
from review.repository import OntologyRepository

router = APIRouter()

_PENDING = (WorkflowStatus.NEW, WorkflowStatus.PENDING_REVIEW)


@router.get("/api/ontology/preview")
@router.post("/api/ontology/preview/regenerate")
def get_ontology_preview(repo: OntologyRepository = Depends(deps.get_repository)) -> dict:
    pending_count = sum(1 for e in repo.get_candidate_entities() if e.status in _PENDING) + sum(
        1 for r in repo.get_candidate_relationships() if r.status in _PENDING
    )
    ontology = generate_approved_ontology(repo)
    ontology["pending_count"] = pending_count
    return ontology
