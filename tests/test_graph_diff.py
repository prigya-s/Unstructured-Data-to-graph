"""compute_graph_diff() compares the last-published Gold graph
(storage.read_graph_export()) against the graph that would result if every
currently pending entity/relationship were approved. Exercises the exact
kind of example the spec calls out: "+5 New Entities, +12 New
Relationships, 2 Entities Merged, 1 Relationship Removed" - proven here at
smaller scale with hand-built fixtures covering every status."""

from __future__ import annotations

from review.graph_diff import compute_graph_diff
from review.models import CandidateEntity, CandidateRelationship, WorkflowStatus
from review.repository import OntologyRepository


class FakeOntologyRepository(OntologyRepository):
    def __init__(self, entities, relationships) -> None:
        self._entities = entities
        self._relationships = relationships

    def save_candidate_entity(self, entity) -> None:
        raise AssertionError("compute_graph_diff() must not write")

    def save_candidate_relationship(self, relationship) -> None:
        raise AssertionError("compute_graph_diff() must not write")

    def get_candidate_entities(self):
        return self._entities

    def get_candidate_relationships(self):
        return self._relationships

    def get_approved_entities(self):
        return [e for e in self._entities if e.status == WorkflowStatus.APPROVED]

    def get_approved_relationships(self):
        return [r for r in self._relationships if r.status == WorkflowStatus.APPROVED]


class FakeStorage:
    def __init__(self, graph_export=None) -> None:
        self._graph_export = graph_export

    def read_graph_export(self):
        return self._graph_export


def _entity(id_, status, name=None, entity_type="System", merged_into=None) -> CandidateEntity:
    return CandidateEntity(
        id=id_,
        name=name or id_,
        entity_type=entity_type,
        definition="d",
        business_meaning="b",
        confidence_score=1.0,
        status=status,
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


def _baseline(entities, relationships):
    return {
        "nodes": {"entities": entities},
        "relationships": {"entity_relationships": relationships},
    }


def test_empty_baseline_everything_live_shows_as_added():
    repo = FakeOntologyRepository([_entity("e1", WorkflowStatus.APPROVED)], [])
    storage = FakeStorage(graph_export=None)

    diff = compute_graph_diff(repo, storage)

    assert [e["id"] for e in diff.entities_added] == ["e1"]
    assert diff.entities_removed == []
    assert diff.entity_count_delta == 1


def test_new_entity_since_baseline_is_added():
    baseline = _baseline([{"id": "e1", "name": "Foo", "type": "System"}], [])
    entities = [_entity("e1", WorkflowStatus.APPROVED, name="Foo"), _entity("e2", WorkflowStatus.PENDING_REVIEW)]
    repo = FakeOntologyRepository(entities, [])
    storage = FakeStorage(graph_export=baseline)

    diff = compute_graph_diff(repo, storage)

    assert [e["id"] for e in diff.entities_added] == ["e2"]
    assert diff.entities_removed == []
    assert diff.entities_modified == []


def test_entity_rejected_after_publish_shows_as_removed():
    baseline = _baseline([{"id": "e1", "name": "Foo", "type": "System"}], [])
    entities = [_entity("e1", WorkflowStatus.REJECTED, name="Foo")]
    repo = FakeOntologyRepository(entities, [])
    storage = FakeStorage(graph_export=baseline)

    diff = compute_graph_diff(repo, storage)

    assert [e["id"] for e in diff.entities_removed] == ["e1"]
    assert diff.entity_count_delta == -1


def test_entity_name_change_shows_as_modified():
    baseline = _baseline([{"id": "e1", "name": "Foo", "type": "System"}], [])
    entities = [_entity("e1", WorkflowStatus.APPROVED, name="Foo Renamed")]
    repo = FakeOntologyRepository(entities, [])
    storage = FakeStorage(graph_export=baseline)

    diff = compute_graph_diff(repo, storage)

    assert len(diff.entities_modified) == 1
    assert diff.entities_modified[0]["before"]["name"] == "Foo"
    assert diff.entities_modified[0]["after"]["name"] == "Foo Renamed"


def test_newly_merged_entity_present_in_baseline_counted_once_as_merged_not_removed():
    baseline = _baseline(
        [{"id": "e1", "name": "Foo", "type": "System"}, {"id": "e2", "name": "Foo Dup", "type": "System"}],
        [],
    )
    entities = [
        _entity("e1", WorkflowStatus.APPROVED, name="Foo"),
        _entity("e2", WorkflowStatus.MERGED, name="Foo Dup", merged_into="e1"),
    ]
    repo = FakeOntologyRepository(entities, [])
    storage = FakeStorage(graph_export=baseline)

    diff = compute_graph_diff(repo, storage)

    assert [m["id"] for m in diff.entities_merged] == ["e2"]
    assert diff.entities_merged[0]["merged_into"] == "e1"
    assert diff.entities_removed == []
    assert diff.entity_count_delta == -1


def test_relationship_added_and_removed():
    baseline = _baseline(
        [{"id": "e1", "name": "Foo", "type": "System"}, {"id": "e2", "name": "Bar", "type": "System"}],
        [{"source": "e1", "relationship": "USES", "target": "e2"}],
    )
    entities = [
        _entity("e1", WorkflowStatus.APPROVED, name="Foo"),
        _entity("e2", WorkflowStatus.APPROVED, name="Bar"),
        _entity("e3", WorkflowStatus.APPROVED, name="Baz"),
    ]
    relationships = [
        _relationship("r1", "e1", "DEPENDS_ON", "e3", WorkflowStatus.PENDING_REVIEW),
    ]
    repo = FakeOntologyRepository(entities, relationships)
    storage = FakeStorage(graph_export=baseline)

    diff = compute_graph_diff(repo, storage)

    assert len(diff.relationships_added) == 1
    assert diff.relationships_added[0] == {"source": "e1", "relationship": "DEPENDS_ON", "target": "e3"}
    assert len(diff.relationships_removed) == 1
    assert diff.relationships_removed[0] == {"source": "e1", "relationship": "USES", "target": "e2"}
    assert diff.relationship_count_delta == 0


def test_spec_example_scale():
    baseline_entities = [{"id": f"base{i}", "name": f"Base{i}", "type": "System"} for i in range(10)]
    baseline_relationships = [
        {"source": "base0", "relationship": "USES", "target": "base1"}
    ]
    baseline = _baseline(baseline_entities, baseline_relationships)

    entities = [_entity(f"base{i}", WorkflowStatus.APPROVED, name=f"Base{i}") for i in range(10)]
    entities += [_entity(f"new{i}", WorkflowStatus.PENDING_REVIEW) for i in range(5)]
    entities += [
        _entity("mergedA", WorkflowStatus.MERGED, merged_into="base0"),
        _entity("mergedB", WorkflowStatus.MERGED, merged_into="base1"),
    ]
    baseline_entities.append({"id": "mergedA", "name": "mergedA", "type": "System"})
    baseline_entities.append({"id": "mergedB", "name": "mergedB", "type": "System"})

    relationships = [_relationship("r0", "base0", "USES", "base1", WorkflowStatus.APPROVED)]
    relationships += [
        _relationship(f"r{i+1}", f"new{i}", "DEPENDS_ON", "base0", WorkflowStatus.PENDING_REVIEW)
        for i in range(5)
    ]
    relationships += [
        _relationship(f"r{i+6}", f"new{i}", "CONNECTS_TO", f"new{(i + 1) % 5}", WorkflowStatus.NEW)
        for i in range(5)
    ]
    relationships += [
        _relationship("r_gone", "base0", "DEPENDS_ON", "base1", WorkflowStatus.REJECTED)
    ]
    baseline["relationships"]["entity_relationships"].append(
        {"source": "base0", "relationship": "DEPENDS_ON", "target": "base1"}
    )

    repo = FakeOntologyRepository(entities, relationships)
    storage = FakeStorage(graph_export=baseline)

    diff = compute_graph_diff(repo, storage)

    assert len(diff.entities_added) == 5
    assert len(diff.entities_merged) == 2
    assert diff.entities_removed == []
    assert len(diff.relationships_added) == 10
    assert len(diff.relationships_removed) == 1
