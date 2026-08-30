"""build_candidates() must call the batch save_candidate_entities/
save_candidate_relationships methods exactly once each per invocation,
never the per-row save_candidate_entity/save_candidate_relationship -
that O(N) -> O(1) call-count change (previously O(N) repository round
trips) is CRITICAL to HIGH finding fix. FakeOntologyRepository's singular
methods raise if called, so any regression to a per-row loop fails loudly.
Decided-status skip logic (APPROVED/REJECTED/MERGED for entities,
APPROVED/REJECTED for relationships) must still be respected."""

from __future__ import annotations

from review.candidate_builder import build_candidates
from review.models import CandidateEntity, CandidateRelationship, WorkflowStatus, make_relationship_id
from review.repository import OntologyRepository


class FakeOntologyRepository(OntologyRepository):
    def __init__(self, entities=None, relationships=None) -> None:
        self._entities = list(entities or [])
        self._relationships = list(relationships or [])
        self.saved_entities: list[CandidateEntity] = []
        self.saved_relationships: list[CandidateRelationship] = []
        self.save_entities_calls = 0
        self.save_relationships_calls = 0

    def save_candidate_entity(self, entity) -> None:
        raise AssertionError("build_candidates() must call save_candidate_entities(), not the per-row method")

    def save_candidate_relationship(self, relationship) -> None:
        raise AssertionError(
            "build_candidates() must call save_candidate_relationships(), not the per-row method"
        )

    def save_candidate_entities(self, entities) -> None:
        self.save_entities_calls += 1
        self.saved_entities = list(entities)

    def save_candidate_relationships(self, relationships) -> None:
        self.save_relationships_calls += 1
        self.saved_relationships = list(relationships)

    def get_candidate_entities(self):
        return self._entities

    def get_candidate_relationships(self):
        return self._relationships

    def get_approved_entities(self):
        return [e for e in self._entities if e.status == WorkflowStatus.APPROVED]

    def get_approved_relationships(self):
        return [r for r in self._relationships if r.status == WorkflowStatus.APPROVED]

    def save_class_proposal(self, proposal) -> None:
        raise AssertionError("build_candidates() must not touch class proposals")

    def get_class_proposals(self):
        return []


_CHUNKS = [{"chunk_id": "c1", "content": "Foo talks to Bar.", "document": "d1"}]
_ENTITIES = [
    {"id": "e1", "type": "System", "name": "Foo"},
    {"id": "e2", "type": "System", "name": "Bar"},
]
_MENTIONS = [
    {"entity_id": "e1", "chunk_id": "c1"},
    {"entity_id": "e1", "chunk_id": "c1"},
    {"entity_id": "e2", "chunk_id": "c1"},
    {"entity_id": "e2", "chunk_id": "c1"},
]
_RELATIONSHIPS = [
    {"source": "e1", "relationship": "USES", "target": "e2", "source_chunk": "c1"},
]


def test_build_candidates_calls_batch_save_methods_exactly_once():
    repository = FakeOntologyRepository()

    entities_saved, relationships_saved = build_candidates(
        _ENTITIES, _MENTIONS, _RELATIONSHIPS, _CHUNKS, repository
    )

    assert repository.save_entities_calls == 1
    assert repository.save_relationships_calls == 1
    assert entities_saved == 2
    assert relationships_saved == 1
    assert {e.id for e in repository.saved_entities} == {"e1", "e2"}
    assert repository.saved_relationships[0].id == make_relationship_id("e1", "USES", "e2")


def test_build_candidates_skips_decided_entities():
    decided = CandidateEntity(
        id="e1",
        name="Foo",
        entity_type="System",
        definition="d",
        business_meaning="b",
        confidence_score=1.0,
        status=WorkflowStatus.APPROVED,
    )
    repository = FakeOntologyRepository(entities=[decided])

    entities_saved, _ = build_candidates(_ENTITIES, _MENTIONS, _RELATIONSHIPS, _CHUNKS, repository)

    assert entities_saved == 1
    assert {e.id for e in repository.saved_entities} == {"e2"}


def test_build_candidates_skips_decided_relationships():
    rel_id = make_relationship_id("e1", "USES", "e2")
    decided = CandidateRelationship(
        id=rel_id,
        source_entity="e1",
        relationship_type="USES",
        target_entity="e2",
        confidence_score=1.0,
        status=WorkflowStatus.REJECTED,
    )
    repository = FakeOntologyRepository(relationships=[decided])

    _, relationships_saved = build_candidates(_ENTITIES, _MENTIONS, _RELATIONSHIPS, _CHUNKS, repository)

    assert relationships_saved == 0
    assert repository.saved_relationships == []


def test_build_candidates_still_calls_batch_methods_when_nothing_new():
    rel_id = make_relationship_id("e1", "USES", "e2")
    decided_entities = [
        CandidateEntity(
            id="e1", name="Foo", entity_type="System", definition="d", business_meaning="b",
            confidence_score=1.0, status=WorkflowStatus.APPROVED,
        ),
        CandidateEntity(
            id="e2", name="Bar", entity_type="System", definition="d", business_meaning="b",
            confidence_score=1.0, status=WorkflowStatus.MERGED,
        ),
    ]
    decided_relationships = [
        CandidateRelationship(
            id=rel_id, source_entity="e1", relationship_type="USES", target_entity="e2",
            confidence_score=1.0, status=WorkflowStatus.APPROVED,
        )
    ]
    repository = FakeOntologyRepository(entities=decided_entities, relationships=decided_relationships)

    entities_saved, relationships_saved = build_candidates(
        _ENTITIES, _MENTIONS, _RELATIONSHIPS, _CHUNKS, repository
    )

    assert entities_saved == 0
    assert relationships_saved == 0
    assert repository.save_entities_calls == 1
    assert repository.save_relationships_calls == 1
    assert repository.saved_entities == []
    assert repository.saved_relationships == []
