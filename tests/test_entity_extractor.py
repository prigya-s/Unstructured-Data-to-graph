"""_PHRASE_RE must span lowercase glue words ("of", "the", "for", "to") and
hyphenated compounds between capitalized tokens, so multi-word entity names
like "Change of Address" or "Account-Managing Adult" are captured whole
instead of being split at the first lowercase/hyphenated token."""

from __future__ import annotations

from extraction.entity_extractor import _clean_phrase, extract_entities, extract_entities_from_chunk

ONTOLOGY = {
    "entity_types": {
        "Request": {"keywords": ["address"]},
        "Role": {"keywords": ["adult"]},
    },
    "technology_gazetteer": [],
}


def test_glue_word_phrase_captured_whole():
    chunk = {"chunk_id": "c1", "content": "Submit a Change of Address request within 30 days."}
    found = extract_entities_from_chunk(chunk, ONTOLOGY)
    assert {(e["name"], e["type"]) for e in found} == {("Change of Address", "Request")}


def test_hyphenated_compound_captured_whole():
    chunk = {"chunk_id": "c1", "content": "The Account-Managing Adult must approve this change."}
    found = extract_entities_from_chunk(chunk, ONTOLOGY)
    assert {(e["name"], e["type"]) for e in found} == {("Account-Managing Adult", "Role")}


def test_trailing_glue_word_is_stripped():
    assert _clean_phrase("Change of") == "Change"
    assert _clean_phrase("The Change of Address") == "Change of Address"


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

    found = extract_entities_from_chunk(chunk, ontology)

    assert ("IVR", "Channel") in {(e["name"], e["type"]) for e in found}


def test_domain_gazetteer_takes_precedence_over_flat_technology_gazetteer():
    ontology = {
        "entity_types": {},
        "technology_gazetteer": ["cat"],
        "domain_gazetteer": {"CAT": "Check"},
    }
    chunk = {"chunk_id": "c1", "content": "The process requires a CAT before continuing."}

    found = extract_entities_from_chunk(chunk, ontology)

    assert ("CAT", "Check") in {(e["name"], e["type"]) for e in found}
    assert ("CAT", "Technology") not in {(e["name"], e["type"]) for e in found}


def test_section_heading_is_never_promoted_to_an_entity():
    """section_path is chunk provenance (already written onto the Chunk
    node in Neo4j - see graph.neo4j_loader), never a mintable domain
    entity. A heading with no capitalized phrases of its own must produce
    zero entities, regardless of how deep the section_path is."""
    ontology = {"entity_types": {}, "technology_gazetteer": []}
    chunk = {
        "chunk_id": "c1",
        "document": "d1",
        "section_path": "Change of address > Mortgage address",
        "content": "Some prose with no capitalized phrases here.",
    }

    found = extract_entities_from_chunk(chunk, ontology)

    assert found == []
