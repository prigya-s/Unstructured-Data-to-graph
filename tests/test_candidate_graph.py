"""build_candidate_graph() must reflect the full non-rejected candidate set
(NEW, PENDING_REVIEW, APPROVED) - not just approved content, since it's the
Silver-layer graph explored before anything is approved. REJECTED entities/
relationships must be excluded entirely; MERGED entities must be dropped as
standalone nodes and any relationship touching them resolved to the
canonical survivor (or dropped if that creates a self-relationship or a
dangling endpoint)."""

from __future__ import annotations

from review.candidate_graph import build_candidate_graph
from review.models import CandidateEntity, CandidateRelationship, WorkflowStatus
from review.repository import OntologyRepository


class FakeOntologyRepository(OntologyRepository):
    def __init__(self, entities, relationships) -> None:
        self._entities = entities
        self._relationships = relationships

    def save_candidate_entity(self, entity) -> None:
        raise AssertionError("build_candidate_graph() must not write")

    def save_candidate_relationship(self, relationship) -> None:
        raise AssertionError("build_candidate_graph() must not write")

    def get_candidate_entities(self):
        return self._entities

    def get_candidate_relationships(self):
        return self._relationships

    def get_approved_entities(self):
        return [e for e in self._entities if e.status == WorkflowStatus.APPROVED]

    def get_approved_relationships(self):
        return [r for r in self._relationships if r.status == WorkflowStatus.APPROVED]

    def save_class_proposal(self, proposal) -> None:
        raise AssertionError("build_candidate_graph() must not write")

    def get_class_proposals(self):
        return []


def _entity(id_, status, name=None, source_chunks=None, merged_into=None) -> CandidateEntity:
    return CandidateEntity(
        id=id_,
        name=name or id_,
        entity_type="System",
        definition="d",
        business_meaning="b",
        confidence_score=1.0,
        status=status,
        source_chunks=source_chunks or [],
        merged_into=merged_into,
    )


def _relationship(id_, source, rel_type, target, status) -> CandidateRelationship:
    return CandidateRelationship(
        id=id_,
        source_entity=source,
        relationship_type=rel_type,
        target_entity=target,
        confidence_score=1.0,
        status=status,
    )


def test_includes_new_pending_and_approved_excludes_rejected():
    entities = [
        _entity("e1", WorkflowStatus.NEW),
        _entity("e2", WorkflowStatus.PENDING_REVIEW),
        _entity("e3", WorkflowStatus.APPROVED),
        _entity("e4", WorkflowStatus.REJECTED),
    ]
    repo = FakeOntologyRepository(entities, [])

    graph = build_candidate_graph(repo)

    assert {e["id"] for e in graph["nodes"]["entities"]} == {"e1", "e2", "e3"}
    assert graph["stats"]["entities"] == 3


def test_merged_entity_dropped_as_standalone_node():
    entities = [
        _entity("e1", WorkflowStatus.APPROVED),
        _entity("e2", WorkflowStatus.MERGED, merged_into="e1"),
    ]
    repo = FakeOntologyRepository(entities, [])

    graph = build_candidate_graph(repo)

    assert {e["id"] for e in graph["nodes"]["entities"]} == {"e1"}


def test_relationship_resolves_merged_endpoint_to_survivor():
    entities = [
        _entity("e1", WorkflowStatus.APPROVED),
        _entity("e2", WorkflowStatus.APPROVED),
        _entity("e3", WorkflowStatus.MERGED, merged_into="e1"),
    ]
    relationships = [
        _relationship("r1", "e3", "USES", "e2", WorkflowStatus.PENDING_REVIEW),
    ]
    repo = FakeOntologyRepository(entities, relationships)

    graph = build_candidate_graph(repo)

    rels = graph["relationships"]["entity_relationships"]
    assert len(rels) == 1
    assert rels[0]["source"] == "e1"
    assert rels[0]["target"] == "e2"


def test_relationship_rejected_excluded():
    entities = [_entity("e1", WorkflowStatus.APPROVED), _entity("e2", WorkflowStatus.APPROVED)]
    relationships = [_relationship("r1", "e1", "USES", "e2", WorkflowStatus.REJECTED)]
    repo = FakeOntologyRepository(entities, relationships)

    graph = build_candidate_graph(repo)

    assert graph["relationships"]["entity_relationships"] == []


def test_relationship_dropped_when_merge_creates_self_relationship():
    entities = [
        _entity("e1", WorkflowStatus.APPROVED),
        _entity("e2", WorkflowStatus.MERGED, merged_into="e1"),
    ]
    relationships = [_relationship("r1", "e1", "USES", "e2", WorkflowStatus.PENDING_REVIEW)]
    repo = FakeOntologyRepository(entities, relationships)

    graph = build_candidate_graph(repo)

    assert graph["relationships"]["entity_relationships"] == []


def test_relationship_dropped_when_endpoint_missing_entirely():
    entities = [_entity("e1", WorkflowStatus.APPROVED)]
    relationships = [_relationship("r1", "e1", "USES", "e2", WorkflowStatus.PENDING_REVIEW)]
    repo = FakeOntologyRepository(entities, relationships)

    graph = build_candidate_graph(repo)

    assert graph["relationships"]["entity_relationships"] == []


def test_no_document_or_chunk_nodes():
    repo = FakeOntologyRepository([_entity("e1", WorkflowStatus.APPROVED)], [])

    graph = build_candidate_graph(repo)

    assert graph["nodes"]["documents"] == []
    assert graph["nodes"]["chunks"] == []


def test_mentions_built_from_source_chunks():
    entities = [_entity("e1", WorkflowStatus.APPROVED, source_chunks=["c1", "c2"])]
    repo = FakeOntologyRepository(entities, [])

    graph = build_candidate_graph(repo)

    assert {m["chunk_id"] for m in graph["relationships"]["mentions"]} == {"c1", "c2"}
    assert all(m["entity_id"] == "e1" for m in graph["relationships"]["mentions"])
