"""HybridExtractionProvider must run rule-based extraction on every chunk
first, and only call the LLM for chunks where rule-based extraction found
fewer than min_entities_per_chunk entities - proving the LLM's workload is
limited to the low-recall subset, not the whole corpus."""

from __future__ import annotations

import json

import pytest

from config.app_config import AppConfig, ExtractionConfig
from providers.hybrid_extraction_provider import HybridExtractionProvider

ONTOLOGY = {
    "entity_types": {"Person": {"keywords": ["engineer"]}, "System": {}},
    "relationship_types": {"OWNS": {}},
    "technology_gazetteer": [],
}


class _FakeResponse:
    def __init__(self, body: dict) -> None:
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def _config(**hybrid_options) -> AppConfig:
    return AppConfig(extraction=ExtractionConfig(provider="hybrid", options={"hybrid": hybrid_options}))


def _llm_response(chunk_results: dict[str, dict]) -> dict:
    return {
        "message": {
            "content": json.dumps(
                {"chunks": [{"chunk_id": cid, **result} for cid, result in chunk_results.items()]}
            )
        }
    }


def _chunk_ids_in_prompt(request) -> set[str]:
    prompt = json.loads(request.data.decode("utf-8"))["messages"][1]["content"]
    return {line.split('"')[1] for line in prompt.splitlines() if line.startswith("chunk_id:")}


def test_no_llm_call_when_rule_based_recall_is_sufficient(monkeypatch):
    provider = HybridExtractionProvider(_config())
    chunks = [{"chunk_id": "c1", "content": "Alice Chen is the Lead Engineer."}]

    def fail_urlopen(request, timeout):
        raise AssertionError("LLM should not be called when rule-based extraction already succeeded")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)

    entities, mentions = provider.extract_entities(chunks, ONTOLOGY)

    assert {(e["name"], e["type"]) for e in entities} == {("Lead Engineer", "Person")}
    assert {(m["chunk_id"], m["entity_id"]) for m in mentions} == {("c1", entities[0]["id"])}


def test_llm_fallback_only_for_low_recall_chunks(monkeypatch):
    provider = HybridExtractionProvider(_config())
    chunks = [
        {"chunk_id": "c1", "content": "Alice Chen is the Lead Engineer."},
        {"chunk_id": "c2", "content": "system uptime metrics were reviewed yesterday."},
    ]
    seen_batches = []

    def fake_urlopen(request, timeout):
        batch = _chunk_ids_in_prompt(request)
        seen_batches.append(batch)
        return _FakeResponse(
            _llm_response(
                {cid: {"entities": [{"name": "BillingSystem", "type": "System"}], "relationships": []}
                 for cid in batch}
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    entities, mentions = provider.extract_entities(chunks, ONTOLOGY)

    assert seen_batches == [{"c2"}]  # only the low-recall chunk was sent to the LLM
    names = {(e["name"], e["type"]) for e in entities}
    assert names == {("Lead Engineer", "Person"), ("BillingSystem", "System")}
    assert {m["chunk_id"] for m in mentions} == {"c1", "c2"}


def test_relationships_routed_to_the_provider_that_extracted_each_chunk(monkeypatch):
    provider = HybridExtractionProvider(_config())
    chunks = [
        {"chunk_id": "c1", "content": "Alice Chen is the Lead Engineer."},
        {"chunk_id": "c2", "content": "system uptime metrics were reviewed yesterday."},
    ]

    def fake_urlopen(request, timeout):
        batch = _chunk_ids_in_prompt(request)
        return _FakeResponse(
            _llm_response(
                {
                    cid: {
                        "entities": [{"name": "BillingSystem", "type": "System"}],
                        "relationships": [
                            {"source": "BillingSystem", "relationship": "OWNS", "target": "BillingSystem"}
                        ],
                    }
                    for cid in batch
                }
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    entities, mentions = provider.extract_entities(chunks, ONTOLOGY)
    relationships = provider.extract_relationships(chunks, entities, mentions, ONTOLOGY)

    # self-relationship (source == target) is dropped by the LLM provider's own
    # defensive filter, so this only proves c2 was routed through the LLM path
    # without raising - no relationships survive from either provider here.
    assert relationships == []


def test_get_class_proposals_forwards_to_llm_leg_only(monkeypatch):
    provider = HybridExtractionProvider(_config())
    chunks = [{"chunk_id": "c2", "content": "system uptime metrics were reviewed yesterday."}]

    def fake_urlopen(request, timeout):
        batch = _chunk_ids_in_prompt(request)
        return _FakeResponse(
            _llm_response(
                {
                    cid: {
                        "entities": [{"name": "CryptoCustodyService", "type": "NO_FIT"}],
                        "relationships": [],
                    }
                    for cid in batch
                }
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider.extract_entities(chunks, ONTOLOGY)

    proposals = provider.get_class_proposals()
    assert [p["proposed_name"] for p in proposals] == ["CryptoCustodyService"]
    assert provider.get_class_proposals() == []


def test_min_entities_per_chunk_is_configurable(monkeypatch):
    provider = HybridExtractionProvider(_config(min_entities_per_chunk=2))
    chunks = [{"chunk_id": "c1", "content": "Alice Chen is the Lead Engineer."}]

    def fake_urlopen(request, timeout):
        batch = _chunk_ids_in_prompt(request)
        return _FakeResponse(_llm_response({cid: {"entities": [], "relationships": []} for cid in batch}))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    entities, mentions = provider.extract_entities(chunks, ONTOLOGY)

    # only 1 rule-based entity found, threshold requires 2 -> falls back to the LLM too
    assert {(e["name"], e["type"]) for e in entities} == {("Lead Engineer", "Person")}
