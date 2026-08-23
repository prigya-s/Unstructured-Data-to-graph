"""GET /api/candidate-graph - passthrough of build_candidate_graph(repo),
same call app/pages/candidate_graph.py makes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api import deps
from review.candidate_graph import build_candidate_graph
from review.repository import OntologyRepository

router = APIRouter()


@router.get("/api/candidate-graph")
def get_candidate_graph(repo: OntologyRepository = Depends(deps.get_repository)) -> dict:
    return build_candidate_graph(repo)
