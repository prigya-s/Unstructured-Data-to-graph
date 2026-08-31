"""build_class_proposals() must create a reviewable ClassProposal row per
NO_FIT dict from ExtractionProvider.get_class_proposals(), and must leave a
proposal alone once it has a terminal status (APPROVED/REJECTED/MERGED) -
same idempotency rule build_candidates() already applies to entities/
relationships, so a repeat ingest run never overwrites a reviewer's
decision."""

from __future__ import annotations

from review.candidate_builder import build_class_proposals
from review.local_repository import LocalOntologyRepository
from review.models import ClassProposal, WorkflowStatus, make_proposal_id


def _raw(name="Cryptocurrency Custody Service", **overrides) -> dict:
    defaults = dict(
        proposed_name=name,
        suggested_parent="Product",
        evidence="a cryptocurrency custody service was mentioned",
        source_chunks=["c1"],
        confidence=0.6,
    )
    defaults.update(overrides)
    return defaults


def test_build_class_proposals_creates_new_rows(tmp_path):
    repo = LocalOntologyRepository(tmp_path)

    saved = build_class_proposals([_raw()], repo)

    assert saved == 1
    [proposal] = repo.get_class_proposals()
    assert proposal.proposed_name == "Cryptocurrency Custody Service"
    assert proposal.suggested_parent == "Product"
    assert proposal.status == WorkflowStatus.NEW


def test_build_class_proposals_empty_list_returns_zero(tmp_path):
    repo = LocalOntologyRepository(tmp_path)

    assert build_class_proposals([], repo) == 0
    assert repo.get_class_proposals() == []


def test_build_class_proposals_skips_approved_proposal(tmp_path):
    repo = LocalOntologyRepository(tmp_path)
    name = "Cryptocurrency Custody Service"
    decided = ClassProposal(
        id=make_proposal_id(name),
        proposed_name=name,
        suggested_parent="Product",
        evidence="already decided",
        source_chunks=["c0"],
        confidence=0.9,
        status=WorkflowStatus.APPROVED,
        reviewer="alice",
    )
    repo.save_class_proposal(decided)

    saved = build_class_proposals([_raw(name=name)], repo)

    assert saved == 0
    [proposal] = repo.get_class_proposals()
    assert proposal.status == WorkflowStatus.APPROVED
    assert proposal.reviewer == "alice"


def test_build_class_proposals_still_creates_unrelated_new_proposal(tmp_path):
    repo = LocalOntologyRepository(tmp_path)
    decided_name = "Cryptocurrency Custody Service"
    decided = ClassProposal(
        id=make_proposal_id(decided_name),
        proposed_name=decided_name,
        suggested_parent="Product",
        evidence="already decided",
        source_chunks=["c0"],
        confidence=0.9,
        status=WorkflowStatus.REJECTED,
    )
    repo.save_class_proposal(decided)

    saved = build_class_proposals(
        [_raw(name=decided_name), _raw(name="Green Energy Retrofit Loan")], repo
    )

    assert saved == 1
    proposals = {p.proposed_name: p for p in repo.get_class_proposals()}
    assert proposals[decided_name].status == WorkflowStatus.REJECTED
    assert proposals["Green Energy Retrofit Loan"].status == WorkflowStatus.NEW
