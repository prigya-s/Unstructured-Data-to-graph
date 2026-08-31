"""ClassProposal storage on LocalOntologyRepository must round-trip through
JSON exactly like the existing candidate entity/relationship stores, and
save_class_proposal()/save_class_proposals() must both upsert by id rather
than duplicate rows on repeated saves."""

from __future__ import annotations

from review.local_repository import LocalOntologyRepository
from review.models import ClassProposal, WorkflowStatus, make_proposal_id


def _proposal(name="Cryptocurrency Custody Service", status=WorkflowStatus.NEW, **overrides):
    defaults = dict(
        id=make_proposal_id(name),
        proposed_name=name,
        suggested_parent="Product",
        evidence="a cryptocurrency custody service was mentioned",
        source_chunks=["c1"],
        confidence=0.6,
        status=status,
        target_domain=None,
    )
    defaults.update(overrides)
    return ClassProposal(**defaults)


def test_make_proposal_id_is_deterministic_and_normalized():
    assert make_proposal_id("Cryptocurrency Custody Service") == make_proposal_id(
        "cryptocurrency custody service"
    )


def test_save_and_get_round_trip(tmp_path):
    repo = LocalOntologyRepository(tmp_path)
    proposal = _proposal()

    repo.save_class_proposal(proposal)

    [loaded] = repo.get_class_proposals()
    assert loaded.id == proposal.id
    assert loaded.proposed_name == proposal.proposed_name
    assert loaded.suggested_parent == "Product"
    assert loaded.status == WorkflowStatus.NEW


def test_save_class_proposal_upserts_by_id(tmp_path):
    repo = LocalOntologyRepository(tmp_path)
    proposal = _proposal()
    repo.save_class_proposal(proposal)

    proposal.status = WorkflowStatus.APPROVED
    proposal.reviewer = "alice"
    repo.save_class_proposal(proposal)

    proposals = repo.get_class_proposals()
    assert len(proposals) == 1
    assert proposals[0].status == WorkflowStatus.APPROVED
    assert proposals[0].reviewer == "alice"


def test_save_class_proposals_bulk_upserts(tmp_path):
    repo = LocalOntologyRepository(tmp_path)
    first = _proposal(name="Cryptocurrency Custody Service")
    second = _proposal(name="Green Energy Retrofit Loan")

    repo.save_class_proposals([first, second])
    assert len(repo.get_class_proposals()) == 2

    first.status = WorkflowStatus.REJECTED
    repo.save_class_proposals([first])

    proposals = {p.id: p for p in repo.get_class_proposals()}
    assert len(proposals) == 2
    assert proposals[first.id].status == WorkflowStatus.REJECTED
    assert proposals[second.id].status == WorkflowStatus.NEW


def test_save_class_proposals_empty_list_is_noop(tmp_path):
    repo = LocalOntologyRepository(tmp_path)
    repo.save_class_proposals([])
    assert repo.get_class_proposals() == []
    assert not repo.class_proposals_path.exists()


def test_get_class_proposals_empty_when_file_missing(tmp_path):
    repo = LocalOntologyRepository(tmp_path)
    assert repo.get_class_proposals() == []
