"""OllamaExtractionProvider must batch chunks into /api/chat calls (grouped
by batch_size, "think" disabled), cache each chunk's raw per-chunk response
under its own chunk_id, filter to ontology-known types, dedupe entities, and
resolve relationship source/target names to entity ids scoped to their own
chunk - no real Ollama server required, the HTTP layer is mocked."""

from __future__ import annotations

import json

import pytest

from config.app_config import AppConfig, ExtractionConfig
from providers.ollama_extraction_provider import OllamaExtractionProvider

ONTOLOGY = {
    "entity_types": {"Person": {}, "System": {}},
    "relationship_types": {"OWNS": {}},
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


def _config(**options) -> AppConfig:
    return AppConfig(extraction=ExtractionConfig(provider="ollama", options={"ollama": options}))


def _chat_response(chunk_results: dict[str, dict]) -> dict:
    return {
        "message": {
            "content": json.dumps(
                {
                    "chunks": [
                        {"chunk_id": chunk_id, **result} for chunk_id, result in chunk_results.items()
                    ]
                }
            )
        }
    }


def test_extract_entities_filters_unknown_types_and_dedupes(monkeypatch):
    provider = OllamaExtractionProvider(_config())
    chunks = [
        {"chunk_id": "c1", "content": "Alice owns BillingSystem"},
        {"chunk_id": "c2", "content": "alice mentioned again"},
    ]

    call_count = 0

    def fake_urlopen(request, timeout):
        nonlocal call_count
        call_count += 1
        return _FakeResponse(
            _chat_response(
                {
                    "c1": {
                        "entities": [
                            {"name": "Alice", "type": "Person", "confidence_score": 0.9},
                            {"name": "BillingSystem", "type": "System", "confidence_score": 0.8},
                            {"name": "Ghost", "type": "NotAType", "confidence_score": 0.5},
                        ],
                        "relationships": [],
                    },
                    "c2": {"entities": [{"name": "alice", "type": "Person"}], "relationships": []},
                }
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    entities, mentions = provider.extract_entities(chunks, ONTOLOGY)

    assert call_count == 1  # both chunks fit in one batch
    names = {(e["name"], e["type"]) for e in entities}
    assert names == {("Alice", "Person"), ("BillingSystem", "System")}
    alice = next(e for e in entities if e["name"] == "Alice")
    assert alice["confidence_score"] == 0.9
    assert {(m["chunk_id"], m["entity_id"]) for m in mentions} == {
        ("c1", alice["id"]),
        ("c2", alice["id"]),
        ("c1", next(e for e in entities if e["name"] == "BillingSystem")["id"]),
    }


def test_extract_relationships_resolves_names_scoped_per_chunk(monkeypatch):
    provider = OllamaExtractionProvider(_config())
    chunks = [{"chunk_id": "c1", "content": "Alice owns BillingSystem"}]

    def fake_urlopen(request, timeout):
        return _FakeResponse(
            _chat_response(
                {
                    "c1": {
                        "entities": [
                            {"name": "Alice", "type": "Person"},
                            {"name": "BillingSystem", "type": "System"},
                        ],
                        "relationships": [
                            {
                                "source": "Alice",
                                "relationship": "OWNS",
                                "target": "BillingSystem",
                                "confidence_score": 0.7,
                            },
                            {"source": "Alice", "relationship": "BOGUS_TYPE", "target": "BillingSystem"},
                            {"source": "Alice", "relationship": "OWNS", "target": "Nobody"},
                        ],
                    }
                }
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    entities, mentions = provider.extract_entities(chunks, ONTOLOGY)
    relationships = provider.extract_relationships(chunks, entities, mentions, ONTOLOGY)

    assert len(relationships) == 1
    rel = relationships[0]
    alice_id = next(e["id"] for e in entities if e["name"] == "Alice")
    billing_id = next(e["id"] for e in entities if e["name"] == "BillingSystem")
    assert rel["source"] == alice_id
    assert rel["target"] == billing_id
    assert rel["relationship"] == "OWNS"
    assert rel["confidence_score"] == 0.7


def test_malformed_model_output_yields_empty_results(monkeypatch):
    provider = OllamaExtractionProvider(_config())
    chunks = [{"chunk_id": "c1", "content": "anything"}]

    def fake_urlopen(request, timeout):
        return _FakeResponse({"message": {"content": "not json"}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    entities, mentions = provider.extract_entities(chunks, ONTOLOGY)
    assert entities == []
    assert mentions == []


def test_extract_entities_caches_per_chunk_and_reuses_for_relationships(monkeypatch):
    provider = OllamaExtractionProvider(_config())
    chunks = [{"chunk_id": "c1", "content": "Alice owns BillingSystem"}]
    call_count = 0

    def fake_urlopen(request, timeout):
        nonlocal call_count
        call_count += 1
        return _FakeResponse(
            _chat_response(
                {
                    "c1": {
                        "entities": [
                            {"name": "Alice", "type": "Person"},
                            {"name": "BillingSystem", "type": "System"},
                        ],
                        "relationships": [
                            {"source": "Alice", "relationship": "OWNS", "target": "BillingSystem"}
                        ],
                    }
                }
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    entities, mentions = provider.extract_entities(chunks, ONTOLOGY)
    provider.extract_relationships(chunks, entities, mentions, ONTOLOGY)

    assert call_count == 1


def test_payload_disables_thinking(monkeypatch):
    provider = OllamaExtractionProvider(_config())
    chunks = [{"chunk_id": "c1", "content": "Alice owns BillingSystem"}]
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(_chat_response({"c1": {"entities": [], "relationships": []}}))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider.extract_entities(chunks, ONTOLOGY)

    assert captured["payload"]["think"] is False


def test_no_fit_entity_is_collected_as_a_class_proposal_not_dropped(monkeypatch):
    provider = OllamaExtractionProvider(_config())
    chunks = [{"chunk_id": "c1", "content": "CryptoCustodyService is a new offering"}]

    def fake_urlopen(request, timeout):
        return _FakeResponse(
            _chat_response(
                {
                    "c1": {
                        "entities": [
                            {
                                "name": "CryptoCustodyService",
                                "type": "NO_FIT",
                                "suggested_parent": "System",
                                "confidence_score": 0.7,
                            }
                        ],
                        "relationships": [],
                    }
                }
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    entities, mentions = provider.extract_entities(chunks, ONTOLOGY)

    assert entities == []
    assert mentions == []
    proposals = provider.get_class_proposals()
    assert len(proposals) == 1
    assert proposals[0]["proposed_name"] == "CryptoCustodyService"
    assert proposals[0]["suggested_parent"] == "System"
    assert proposals[0]["source_chunks"] == ["c1"]
    assert proposals[0]["confidence"] == 0.7


def test_no_fit_suggested_parent_outside_allowed_types_is_cleared(monkeypatch):
    provider = OllamaExtractionProvider(_config())
    chunks = [{"chunk_id": "c1", "content": "something new"}]

    def fake_urlopen(request, timeout):
        return _FakeResponse(
            _chat_response(
                {
                    "c1": {
                        "entities": [
                            {"name": "NewThing", "type": "NO_FIT", "suggested_parent": "NotAllowed"}
                        ],
                        "relationships": [],
                    }
                }
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider.extract_entities(chunks, ONTOLOGY)

    [proposal] = provider.get_class_proposals()
    assert proposal["suggested_parent"] is None


def test_get_class_proposals_merges_repeated_name_across_chunks_and_clears(monkeypatch):
    provider = OllamaExtractionProvider(_config())
    chunks = [
        {"chunk_id": "c1", "content": "first mention"},
        {"chunk_id": "c2", "content": "second mention"},
    ]

    def fake_urlopen(request, timeout):
        return _FakeResponse(
            _chat_response(
                {
                    "c1": {
                        "entities": [
                            {"name": "NewThing", "type": "NO_FIT", "confidence_score": 0.4}
                        ],
                        "relationships": [],
                    },
                    "c2": {
                        "entities": [
                            {
                                "name": "newthing",
                                "type": "NO_FIT",
                                "suggested_parent": "System",
                                "confidence_score": 0.9,
                            }
                        ],
                        "relationships": [],
                    },
                }
            )
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider.extract_entities(chunks, ONTOLOGY)

    proposals = provider.get_class_proposals()
    assert len(proposals) == 1
    assert proposals[0]["suggested_parent"] == "System"
    assert proposals[0]["confidence"] == 0.9
    assert set(proposals[0]["source_chunks"]) == {"c1", "c2"}

    assert provider.get_class_proposals() == []


def test_chunks_are_grouped_into_batches_of_batch_size(monkeypatch):
    provider = OllamaExtractionProvider(_config(batch_size=2))
    chunks = [
        {"chunk_id": "c1", "content": "one"},
        {"chunk_id": "c2", "content": "two"},
        {"chunk_id": "c3", "content": "three"},
    ]
    seen_batches = []

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        prompt = payload["messages"][1]["content"]
        batch_chunk_ids = [cid for cid in ("c1", "c2", "c3") if f'chunk_id: "{cid}"' in prompt]
        seen_batches.append(batch_chunk_ids)
        return _FakeResponse(
            _chat_response({cid: {"entities": [], "relationships": []} for cid in batch_chunk_ids})
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider.extract_entities(chunks, ONTOLOGY)

    assert seen_batches == [["c1", "c2"], ["c3"]]
