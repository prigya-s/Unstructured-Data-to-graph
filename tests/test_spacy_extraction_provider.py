"""SpacyExtractionProvider must delegate straight through to
extraction.spacy_entity_extractor / extraction.relationship_extractor -
same contract as OntologyRulesExtractionProvider, just a different
rules-leg implementation underneath."""

from __future__ import annotations

from extraction import relationship_extractor, spacy_entity_extractor
from providers.spacy_extraction_provider import SpacyExtractionProvider

ONTOLOGY = {
    "entity_types": {"Person": {"keywords": ["engineer"]}},
    "relationship_types": {"OWNS": {}},
    "technology_gazetteer": [],
}

CHUNKS = [{"chunk_id": "c1", "content": "Alice Smith is an Engineer."}]


def test_extract_entities_matches_module_function():
    provider = SpacyExtractionProvider()

    expected_entities, expected_mentions = spacy_entity_extractor.extract_entities(CHUNKS, ONTOLOGY)
    entities, mentions = provider.extract_entities(CHUNKS, ONTOLOGY)

    assert entities == expected_entities
    assert mentions == expected_mentions


def test_extract_relationships_matches_module_function():
    provider = SpacyExtractionProvider()
    entities, mentions = provider.extract_entities(CHUNKS, ONTOLOGY)

    expected = relationship_extractor.extract_relationships(CHUNKS, entities, mentions, ONTOLOGY)
    relationships = provider.extract_relationships(CHUNKS, entities, mentions, ONTOLOGY)

    assert relationships == expected


def test_get_class_proposals_is_a_no_op():
    """This provider cannot flag NO_FIT - every entity it emits is one of
    the fixed ontology types, same governance guarantee as
    OntologyRulesExtractionProvider."""
    provider = SpacyExtractionProvider()
    assert provider.get_class_proposals() == []
