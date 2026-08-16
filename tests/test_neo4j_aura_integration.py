"""Real round trip against a live Neo4j AuraDB instance - skipped entirely
unless NEO4J_AURA_TEST_URI/NEO4J_AURA_TEST_PASSWORD are set, so the default
test run (and CI without Aura credentials) never needs live Neo4j. Point
these at a disposable/free-tier Aura instance, never production data - this
test writes and deletes real nodes.

Run explicitly with:
    NEO4J_AURA_TEST_URI=neo4j+s://xxxx.databases.neo4j.io \\
    NEO4J_AURA_TEST_USER=neo4j \\
    NEO4J_AURA_TEST_PASSWORD=... \\
    pytest tests/test_neo4j_aura_integration.py -q
"""

from __future__ import annotations

import os

import pytest

from config.app_config import AppConfig, GraphConfig
from providers.neo4j_aura_graph_provider import Neo4jAuraGraphProvider

_URI = os.environ.get("NEO4J_AURA_TEST_URI")
_PASSWORD = os.environ.get("NEO4J_AURA_TEST_PASSWORD")

pytestmark = pytest.mark.skipif(
    not (_URI and _PASSWORD),
    reason="Set NEO4J_AURA_TEST_URI and NEO4J_AURA_TEST_PASSWORD to run against a real Aura instance",
)


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", _URI)
    monkeypatch.setenv("NEO4J_USER", os.environ.get("NEO4J_AURA_TEST_USER", "neo4j"))
    monkeypatch.setenv("NEO4J_PASSWORD", _PASSWORD)
    config = AppConfig(graph=GraphConfig(provider="neo4j_aura"))
    provider = Neo4jAuraGraphProvider(config)
    yield provider
    provider.query_graph("MATCH (n) WHERE n.id STARTS WITH 'aura-integration-test-' DETACH DELETE n")
    provider.close()


def test_connect_create_constraints_and_indexes_against_real_aura(provider):
    provider.connect()
    provider.create_constraints()
    provider.create_indexes()


def test_build_production_graph_round_trip_against_real_aura(provider):
    provider.connect()
    graph = {
        "nodes": {
            "documents": [
                {
                    "id": "aura-integration-test-d1",
                    "name": "d1",
                    "source_path": "d1",
                    "markdown_path": "d1",
                }
            ],
            "chunks": [
                {
                    "id": "aura-integration-test-c1",
                    "document": "aura-integration-test-d1",
                    "section_path": "",
                    "content": "hello",
                    "token_count": 1,
                    "embedding": None,
                }
            ],
            "entities": [
                {
                    "id": "aura-integration-test-e1",
                    "name": "Checkout",
                    "type": "Service",
                    "source_chunk": "aura-integration-test-c1",
                }
            ],
        },
        "relationships": {
            "has_chunk": [{"document_id": "aura-integration-test-d1", "chunk_id": "aura-integration-test-c1"}],
            "mentions": [{"chunk_id": "aura-integration-test-c1", "entity_id": "aura-integration-test-e1"}],
            "entity_relationships": [],
        },
    }

    stats = provider.build_production_graph(graph)

    assert stats["nodes_loaded"] == 3
    assert stats["relationships_loaded"] == 2

    result = provider.query_graph(
        "MATCH (e:Entity {id: $id}) RETURN e.name AS name", {"id": "aura-integration-test-e1"}
    )
    assert result == [{"name": "Checkout"}]
