"""main._update_orphaned_by_edit_flags flags an APPROVED candidate entity
that dropped out of the current corpus (no mention anywhere - see A4 of
composed-gliding-gem.md) and clears the flag if it's mentioned again later.
Never touches non-APPROVED rows or deletes anything - matches the plan's
explicit mandate that a human decides retire vs. keep via the existing
approve/reject workflow."""

from __future__ import annotations

from main import _update_orphaned_by_edit_flags
from review.models import CandidateEntity, WorkflowStatus
from review.repository import OntologyRepository


class FakeOntologyRepository(OntologyRepository):
    def __init__(self, entities: list[CandidateEntity]) -> None:
        self._entities = {e.id: e for e in entities}
        self.saved: list[CandidateEntity] = []

    def save_candidate_entity(self, entity) -> None:
        self._entities[entity.id] = entity
        self.saved.append(entity)

    def save_candidate_relationship(self, relationship) -> None:
        raise AssertionError("not exercised by this test")

    def save_candidate_entities(self, entities) -> None:
        for entity in entities:
            self.save_candidate_entity(entity)

    def save_candidate_relationships(self, relationships) -> None:
        raise AssertionError("not exercised by this test")

    def get_candidate_entities(self):
        return list(self._entities.values())

    def get_candidate_relationships(self):
        return []

    def get_approved_entities(self):
        return [e for e in self._entities.values() if e.status == WorkflowStatus.APPROVED]

    def get_approved_relationships(self):
        return []

    def save_class_proposal(self, proposal) -> None:
        raise AssertionError("not exercised by this test")

    def get_class_proposals(self):
        return []


def _approved_entity(entity_id: str) -> CandidateEntity:
    return CandidateEntity(
        id=entity_id,
        name=entity_id,
        entity_type="System",
        definition="d",
        business_meaning="b",
        confidence_score=1.0,
        status=WorkflowStatus.APPROVED,
    )


def test_approved_entity_with_no_remaining_evidence_gets_flagged():
    repository = FakeOntologyRepository([_approved_entity("e1")])

    flagged, cleared = _update_orphaned_by_edit_flags(repository, entities_lost={"e1"}, current_entity_ids=set())

    assert (flagged, cleared) == (1, 0)
    assert repository.get_candidate_entities()[0].orphaned_by_edit is True


def test_pending_review_entity_is_never_flagged():
    entity = _approved_entity("e1")
    entity.status = WorkflowStatus.PENDING_REVIEW
    repository = FakeOntologyRepository([entity])

    flagged, cleared = _update_orphaned_by_edit_flags(repository, entities_lost={"e1"}, current_entity_ids=set())

    assert (flagged, cleared) == (0, 0)
    assert repository.get_candidate_entities()[0].orphaned_by_edit is False


def test_flag_is_cleared_once_evidence_reappears():
    entity = _approved_entity("e1")
    entity.orphaned_by_edit = True
    repository = FakeOntologyRepository([entity])

    flagged, cleared = _update_orphaned_by_edit_flags(repository, entities_lost=set(), current_entity_ids={"e1"})

    assert (flagged, cleared) == (0, 1)
    assert repository.get_candidate_entities()[0].orphaned_by_edit is False


def test_already_flagged_entity_still_missing_is_not_recounted():
    entity = _approved_entity("e1")
    entity.orphaned_by_edit = True
    repository = FakeOntologyRepository([entity])

    flagged, cleared = _update_orphaned_by_edit_flags(repository, entities_lost={"e1"}, current_entity_ids=set())

    assert (flagged, cleared) == (0, 0)
    assert repository.saved == []


def test_unrelated_approved_entity_is_left_untouched():
    entity = _approved_entity("e2")
    repository = FakeOntologyRepository([entity])

    flagged, cleared = _update_orphaned_by_edit_flags(repository, entities_lost={"e1"}, current_entity_ids={"e2"})

    assert (flagged, cleared) == (0, 0)
    assert repository.saved == []
