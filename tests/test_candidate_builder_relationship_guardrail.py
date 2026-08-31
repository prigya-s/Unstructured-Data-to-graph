"""build_candidates()'s optional `config` param wires
ontology.rdf.guardrails.check_relationship_type_mismatch into relationship
candidate creation - advisory only (a "warning" history entry, never a
rejected/lowered-confidence row), and fully inert under the default `local`
provider (config=None or no turtle_modules) so every existing caller/test
that doesn't pass config is unaffected."""

from __future__ import annotations

from config.app_config import AppConfig, OntologyConfig
from review.candidate_builder import build_candidates
from review.models import WorkflowStatus
from review.repository import OntologyRepository


class FakeOntologyRepository(OntologyRepository):
    def __init__(self) -> None:
        self.saved_relationships = []

    def save_candidate_entity(self, entity) -> None:
        raise AssertionError("not exercised by this test")

    def save_candidate_relationship(self, relationship) -> None:
        raise AssertionError("not exercised by this test")

    def save_candidate_entities(self, entities) -> None:
        pass

    def save_candidate_relationships(self, relationships) -> None:
        self.saved_relationships = list(relationships)

    def get_candidate_entities(self):
        return []

    def get_candidate_relationships(self):
        return []

    def get_approved_entities(self):
        return []

    def get_approved_relationships(self):
        return []

    def save_class_proposal(self, proposal) -> None:
        raise AssertionError("not exercised by this test")

    def get_class_proposals(self):
        return []


_CHUNKS = [{"chunk_id": "c1", "content": "Alice owns Bob.", "document": "d1"}]
_ENTITIES = [
    {"id": "e1", "type": "Party", "name": "Alice"},
    {"id": "e2", "type": "Party", "name": "Bob"},
]
_MENTIONS = [
    {"entity_id": "e1", "chunk_id": "c1"},
    {"entity_id": "e2", "chunk_id": "c1"},
]
_RELATIONSHIPS = [
    {"source": "e1", "relationship": "OWNS", "target": "e2", "source_chunk": "c1"},
]


def _turtle_config() -> AppConfig:
    return AppConfig(ontology=OntologyConfig(turtle_modules=["ontology/rdf/domains/change_of_address.ttl"]))


def test_relationship_mismatch_recorded_as_warning_history_entry():
    repository = FakeOntologyRepository()

    build_candidates(_ENTITIES, _MENTIONS, _RELATIONSHIPS, _CHUNKS, repository, _turtle_config())

    assert len(repository.saved_relationships) == 1
    candidate = repository.saved_relationships[0]
    assert candidate.status == WorkflowStatus.PENDING_REVIEW
    warnings = [h for h in candidate.history if h.action == "warning"]
    assert len(warnings) == 1
    assert "OWNS" in warnings[0].comment


def test_relationship_satisfying_domain_range_has_no_warning():
    repository = FakeOntologyRepository()
    entities = [
        {"id": "e1", "type": "Team", "name": "Platform Team"},
        {"id": "e2", "type": "System", "name": "Ledger"},
    ]
    relationships = [{"source": "e1", "relationship": "OWNS", "target": "e2", "source_chunk": "c1"}]

    build_candidates(entities, _MENTIONS, relationships, _CHUNKS, repository, _turtle_config())

    candidate = repository.saved_relationships[0]
    assert [h for h in candidate.history if h.action == "warning"] == []


def test_no_config_is_a_noop_no_warning_added():
    repository = FakeOntologyRepository()

    build_candidates(_ENTITIES, _MENTIONS, _RELATIONSHIPS, _CHUNKS, repository)

    candidate = repository.saved_relationships[0]
    assert [h for h in candidate.history if h.action == "warning"] == []


def test_local_provider_config_is_a_noop_no_warning_added():
    repository = FakeOntologyRepository()

    build_candidates(_ENTITIES, _MENTIONS, _RELATIONSHIPS, _CHUNKS, repository, AppConfig())

    candidate = repository.saved_relationships[0]
    assert [h for h in candidate.history if h.action == "warning"] == []
