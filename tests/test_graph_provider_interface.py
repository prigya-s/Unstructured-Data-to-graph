"""Conformance check: every concrete GraphProvider implementation must
override all of GraphProvider's abstract methods. A class with any
abstractmethod left unimplemented has a non-empty __abstractmethods__ and
Python itself refuses to instantiate it - checking that set directly (no
network, no construction) is what actually pins the interface, since a
missed override is otherwise silent until someone tries to instantiate that
class."""

from __future__ import annotations

from config.app_config import AppConfig
from providers.cosmos_graph_provider import CosmosGraphProvider
from providers.graph_provider import GraphProvider
from providers.mock_graph_provider import MockGraphProvider
from providers.neo4j_aura_graph_provider import Neo4jAuraGraphProvider
from providers.neo4j_graph_provider import Neo4jGraphProvider

_IMPLEMENTATIONS = [Neo4jGraphProvider, Neo4jAuraGraphProvider, CosmosGraphProvider, MockGraphProvider]


def test_graph_provider_declares_the_full_interface():
    expected = {
        "connect",
        "create_constraints",
        "create_indexes",
        "save_entity",
        "save_relationship",
        "save_chunk",
        "build_candidate_graph",
        "build_production_graph",
        "search_chunks",
        "get_mentioned_entities",
        "get_neighbors",
        "get_linked_documents",
        "query_graph",
        "close",
    }
    assert expected.issubset(GraphProvider.__abstractmethods__)


def test_cosmos_graph_provider_get_linked_documents_raises_not_implemented():
    provider = CosmosGraphProvider(AppConfig())

    try:
        provider.get_linked_documents(["d1"], hops=1, limit=10)
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass


def test_every_implementation_overrides_all_abstract_methods():
    for cls in _IMPLEMENTATIONS:
        assert not getattr(cls, "__abstractmethods__", set()), (
            f"{cls.__name__} is missing an implementation for: {cls.__abstractmethods__}"
        )


def test_neo4j_aura_graph_provider_subclasses_neo4j_graph_provider():
    assert issubclass(Neo4jAuraGraphProvider, Neo4jGraphProvider)
