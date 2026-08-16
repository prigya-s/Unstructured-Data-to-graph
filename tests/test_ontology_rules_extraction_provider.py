"""OntologyRulesExtractionProvider must delegate straight through to the
unchanged extraction.entity_extractor/relationship_extractor module
functions - byte-identical behavior to the pre-provider code path."""

from __future__ import annotations

from extraction import entity_extractor, relationship_extractor
from providers.ontology_rules_extraction_provider import OntologyRulesExtractionProvider

ONTOLOGY = {
    "entity_types": {"Person": {"keywords": ["engineer"]}},
    "relationship_types": {"OWNS": {}},
    "technology_gazetteer": [],
}

CHUNKS = [{"chunk_id": "c1", "content": "Alice Smith is an Engineer."}]


def test_extract_entities_matches_module_function():
    provider = OntologyRulesExtractionProvider()

    expected_entities, expected_mentions = entity_extractor.extract_entities(CHUNKS, ONTOLOGY)
    entities, mentions = provider.extract_entities(CHUNKS, ONTOLOGY)

    assert entities == expected_entities
    assert mentions == expected_mentions


def test_extract_relationships_matches_module_function():
    provider = OntologyRulesExtractionProvider()
    entities, mentions = provider.extract_entities(CHUNKS, ONTOLOGY)

    expected = relationship_extractor.extract_relationships(CHUNKS, entities, mentions, ONTOLOGY)
    relationships = provider.extract_relationships(CHUNKS, entities, mentions, ONTOLOGY)

    assert relationships == expected
