"""
Class Proposal Review endpoints - the human-gated side of Phase 3's
governed ontology growth. A NO_FIT-flagged entity becomes a reviewable
ClassProposal (see review.candidate_builder.build_class_proposals()); this
router lets a reviewer edit it, then approve (guardrail checks +
ontology.rdf.writer.append_class_to_domain()) or reject it. Mirrors
entities.py's shape (save/approve/reject against the same OntologyRepository)
plus the guardrail/`.ttl`-write step approving an entity never needed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api import deps
from api.review_helpers import add_history, now_iso
from ontology.rdf.graph_loader import load_full_ttl_graph
from ontology.rdf.guardrails import check_near_duplicate_labels
from ontology.rdf.writer import append_class_to_domain
from review import WorkflowStatus
from review.repository import OntologyRepository

router = APIRouter()

_DEFAULT_TARGET_DOMAIN = "extensions"


class SaveProposalBody(BaseModel):
    suggested_parent: str | None = None
    target_domain: str | None = None
    comment: str | None = None


class ActionBody(BaseModel):
    comment: str | None = None


def _get_proposal_or_404(repo: OntologyRepository, proposal_id: str):
    proposal = next((p for p in repo.get_class_proposals() if p.id == proposal_id), None)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"Class proposal '{proposal_id}' not found")
    return proposal


@router.get("/api/class-proposals")
def list_class_proposals(repo: OntologyRepository = Depends(deps.get_repository)) -> list[dict]:
    return [p.to_dict() for p in repo.get_class_proposals()]


@router.patch("/api/class-proposals/{proposal_id}/save")
def save_class_proposal(
    proposal_id: str,
    body: SaveProposalBody,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> dict:
    proposal = _get_proposal_or_404(repo, proposal_id)
    proposal.suggested_parent = body.suggested_parent
    proposal.target_domain = body.target_domain
    add_history(proposal, reviewer, "edit", body.comment or "Suggested parent/target domain updated.")
    repo.save_class_proposal(proposal)
    return proposal.to_dict()


@router.patch("/api/class-proposals/{proposal_id}/approve")
def approve_class_proposal(
    proposal_id: str,
    body: ActionBody,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> dict:
    proposal = _get_proposal_or_404(repo, proposal_id)

    graph = load_full_ttl_graph()
    duplicates = check_near_duplicate_labels(graph, proposal.proposed_name)
    if duplicates:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{proposal.proposed_name}' looks like a near-duplicate of existing "
                f"class(es): {', '.join(duplicates)}. Rename or reject this proposal instead."
            ),
        )

    domain_stem = proposal.target_domain or _DEFAULT_TARGET_DOMAIN

    try:
        target_path = append_class_to_domain(
            proposal.proposed_name, proposal.suggested_parent, domain_stem
        )
        outcome = f"Wrote new owl:Class '{proposal.proposed_name}' to {target_path.name}."
    except ValueError:
        outcome = f"'{proposal.proposed_name}' already exists in {domain_stem}.ttl - not rewritten."

    proposal.status = WorkflowStatus.APPROVED
    proposal.reviewer = reviewer
    proposal.review_timestamp = now_iso()
    add_history(proposal, reviewer, "approve", body.comment or outcome)
    repo.save_class_proposal(proposal)
    return proposal.to_dict()


@router.patch("/api/class-proposals/{proposal_id}/reject")
def reject_class_proposal(
    proposal_id: str,
    body: ActionBody,
    repo: OntologyRepository = Depends(deps.get_repository),
    reviewer: str = Depends(deps.get_current_reviewer),
) -> dict:
    proposal = _get_proposal_or_404(repo, proposal_id)
    proposal.status = WorkflowStatus.REJECTED
    proposal.reviewer = reviewer
    proposal.review_timestamp = now_iso()
    add_history(proposal, reviewer, "reject", body.comment)
    repo.save_class_proposal(proposal)
    return proposal.to_dict()
