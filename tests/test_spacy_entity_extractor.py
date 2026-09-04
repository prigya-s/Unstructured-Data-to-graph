"""Mirrors test_entity_extractor.py's scenarios against the spaCy-based
extractor: same ontology-driven classification, same output contract, so a
caller can swap extraction.provider between ontology_rules and spacy_rules
without any behavior change for these cases."""

from __future__ import annotations

from extraction.spacy_entity_extractor import extract_entities

ONTOLOGY = {
    "entity_types": {
        "Request": {"keywords": ["address"]},
        "Role": {"keywords": ["adult"]},
    },
    "technology_gazetteer": [],
}


def test_glue_word_phrase_captured_whole():
    chunk = {"chunk_id": "c1", "content": "Submit a Change of Address request within 30 days."}
    found, _ = extract_entities([chunk], ONTOLOGY)
    assert {(e["name"], e["type"]) for e in found} == {("Change of Address", "Request")}


def test_hyphenated_compound_captured_whole():
    chunk = {"chunk_id": "c1", "content": "The Account-Managing Adult must approve this change."}
    found, _ = extract_entities([chunk], ONTOLOGY)
    assert {(e["name"], e["type"]) for e in found} == {("Account-Managing Adult", "Role")}


def test_extract_entities_dedupes_across_chunks_with_fixed_phrase():
    chunks = [
        {"chunk_id": "c1", "content": "File a Change of Address form."},
        {"chunk_id": "c2", "content": "The Change of Address form takes 10 days to process."},
    ]
    entities, mentions = extract_entities(chunks, ONTOLOGY)
    assert [e["name"] for e in entities] == ["Change of Address"]
    assert {m["chunk_id"] for m in mentions} == {"c1", "c2"}


def test_domain_gazetteer_types_bare_acronym_correctly():
    ontology = {
        "entity_types": {},
        "technology_gazetteer": [],
        "domain_gazetteer": {"IVR": "Channel"},
    }
    chunk = {"chunk_id": "c1", "content": "The customer failed IVR authentication."}

    found, _ = extract_entities([chunk], ontology)

    assert ("IVR", "Channel") in {(e["name"], e["type"]) for e in found}


def test_domain_gazetteer_takes_precedence_over_flat_technology_gazetteer():
    ontology = {
        "entity_types": {},
        "technology_gazetteer": ["cat"],
        "domain_gazetteer": {"CAT": "Check"},
    }
    chunk = {"chunk_id": "c1", "content": "The process requires a CAT before continuing."}

    found, _ = extract_entities([chunk], ontology)

    assert ("CAT", "Check") in {(e["name"], e["type"]) for e in found}
    assert ("CAT", "Technology") not in {(e["name"], e["type"]) for e in found}


def test_section_heading_is_never_promoted_to_an_entity():
    ontology = {"entity_types": {}, "technology_gazetteer": []}
    chunk = {
        "chunk_id": "c1",
        "document": "d1",
        "section_path": "Change of address > Mortgage address",
        "content": "Some prose with no capitalized phrases here.",
    }

    found, _ = extract_entities([chunk], ontology)

    assert found == []


def test_no_entities_from_plain_prose_with_no_capitalized_words():
    ontology = {"entity_types": {}, "technology_gazetteer": []}
    chunk = {"chunk_id": "c1", "content": "this sentence has no capitalized words at all."}

    found, _ = extract_entities([chunk], ontology)

    assert found == []


def test_document_type_keyword_is_never_used_for_a_pattern():
    """Document candidates come from the pipeline's own chunk/source
    metadata, never free text - entity_types.Document.keywords must be
    skipped when building patterns, same as entity_extractor._classify."""
    ontology = {
        "entity_types": {"Document": {"keywords": ["policy"]}},
        "technology_gazetteer": [],
    }
    chunk = {"chunk_id": "c1", "content": "Refer to the Onboarding Policy for details."}

    found, _ = extract_entities([chunk], ontology)

    assert found == []
