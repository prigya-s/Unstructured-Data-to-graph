"""MockGraphProvider exercises the full GraphProvider interface with zero
live Neo4j - this is what lets the app/pipeline run end to end
(graph.provider: mock) without a database. Coverage here mirrors the real
providers' contract: save_entity/save_relationship/save_chunk are batched
upserts, build_candidate_graph fully replaces the candidate set each call,
and get_neighbors clamps hops/limit the same way graph.neo4j_loader does."""

from __future__ import annotations

from providers.mock_graph_provider import MockGraphProvider


def _provider() -> MockGraphProvider:
    return MockGraphProvider()


def test_connect_create_constraints_create_indexes_are_no_ops():
    provider = _provider()

    provider.connect()
    provider.create_constraints()
    provider.create_indexes()

    assert provider.connected
    assert provider.constraints_created
    assert provider.indexes_created


def test_save_entity_and_get_mentioned_entities():
    provider = _provider()

    provider.save_entity([{"id": "e1", "name": "Checkout", "type": "Service", "source_chunk": "c1"}])
    result = provider.get_mentioned_entities(["c1"])

    assert result == [{"entity_id": "e1", "name": "Checkout", "entity_type": "Service"}]


def test_save_chunk_and_search_chunks():
    provider = _provider()

    provider.save_chunk([{"id": "c1", "content": "hello", "document": "d1"}])
    result = provider.search_chunks([0.1, 0.2], top_k=5)

    assert result == [{"chunk_id": "c1", "content": "hello", "document_id": "d1", "score": 1.0}]


def test_search_chunks_respects_top_k():
    provider = _provider()
    provider.save_chunk(
        [
            {"id": "c1", "content": "a", "document": "d1"},
            {"id": "c2", "content": "b", "document": "d1"},
            {"id": "c3", "content": "c", "document": "d1"},
        ]
    )

    result = provider.search_chunks([0.1], top_k=2)

    assert len(result) == 2


def test_build_candidate_graph_replaces_previous_candidates():
    provider = _provider()
    first = {
        "nodes": {"entities": [{"id": "e1", "name": "Old", "type": "System", "source_chunk": "c1"}]},
        "relationships": {"entity_relationships": []},
    }
    second = {
        "nodes": {"entities": [{"id": "e2", "name": "New", "type": "System", "source_chunk": "c1"}]},
        "relationships": {"entity_relationships": []},
    }

    provider.build_candidate_graph(first)
    stats = provider.build_candidate_graph(second)

    assert "e1" not in provider.candidate_entities
    assert "e2" in provider.candidate_entities
    assert stats == {"candidate_entities_loaded": 1, "candidate_relationships_loaded": 0}


def test_build_production_graph_returns_stats_and_stores_entities():
    provider = _provider()
    graph = {
        "nodes": {
            "documents": [{"id": "d1", "name": "d1", "source_path": "d1", "markdown_path": "d1"}],
            "chunks": [{"id": "c1", "document": "d1", "content": "hello"}],
            "entities": [{"id": "e1", "name": "Checkout", "type": "Service", "source_chunk": "c1"}],
        },
        "relationships": {
            "has_chunk": [{"document_id": "d1", "chunk_id": "c1"}],
            "mentions": [{"chunk_id": "c1", "entity_id": "e1"}],
            "entity_relationships": [],
        },
    }

    stats = provider.build_production_graph(graph)

    assert stats["nodes_loaded"] == 3
    assert stats["relationships_loaded"] == 2
    assert provider.constraints_created and provider.indexes_created
    assert "e1" in provider.entities


def test_build_production_graph_counts_page_hierarchy_relationships():
    provider = _provider()
    graph = {
        "nodes": {
            "documents": [
                {"id": "d1", "name": "d1", "source_path": "d1", "markdown_path": "d1"},
                {"id": "d2", "name": "d2", "source_path": "d2", "markdown_path": "d2"},
            ],
            "chunks": [],
            "entities": [],
        },
        "relationships": {
            "has_chunk": [],
            "mentions": [],
            "entity_relationships": [],
            "page_hierarchy": [{"child_id": "d2", "parent_id": "d1"}],
        },
    }

    stats = provider.build_production_graph(graph)

    assert stats["relationships_loaded"] == 1


def test_build_production_graph_without_page_hierarchy_key_is_backward_compatible():
    provider = _provider()
    graph = {
        "nodes": {"documents": [], "chunks": [], "entities": []},
        "relationships": {"has_chunk": [], "mentions": [], "entity_relationships": []},
    }

    stats = provider.build_production_graph(graph)

    assert stats["relationships_loaded"] == 0


def test_build_production_graph_counts_page_links_relationships():
    provider = _provider()
    graph = {
        "nodes": {
            "documents": [
                {"id": "q18", "name": "Q18", "source_path": "q18", "markdown_path": "q18"},
                {"id": "q19", "name": "Q19", "source_path": "q19", "markdown_path": "q19"},
            ],
            "chunks": [],
            "entities": [],
        },
        "relationships": {
            "has_chunk": [],
            "mentions": [],
            "entity_relationships": [],
            "page_links": [{"source_id": "q18", "target_id": "q19", "answer_label": "An adult"}],
        },
    }

    stats = provider.build_production_graph(graph)

    assert stats["relationships_loaded"] == 1


def _linked_docs_provider() -> MockGraphProvider:
    provider = _provider()
    graph = {
        "nodes": {
            "documents": [
                {"id": "q18", "name": "Q18", "source_path": "q18", "markdown_path": "q18"},
                {"id": "q19", "name": "Q19", "source_path": "q19", "markdown_path": "q19"},
                {"id": "q33", "name": "Q33", "source_path": "q33", "markdown_path": "q33"},
            ],
            "chunks": [],
            "entities": [],
        },
        "relationships": {
            "has_chunk": [],
            "mentions": [],
            "entity_relationships": [],
            "page_links": [
                {"source_id": "q18", "target_id": "q19", "answer_label": "An adult"},
                {"source_id": "q19", "target_id": "q33", "answer_label": "Confirmed"},
            ],
        },
    }
    provider.build_production_graph(graph)
    return provider


def test_get_linked_documents_single_hop():
    provider = _linked_docs_provider()

    result = provider.get_linked_documents(["q18"], hops=1, limit=10)

    assert result["documents"] == [{"document_id": "q19", "name": "Q19"}]
    assert result["paths"] == [
        {"source_name": "Q18", "answer_labels": ["An adult"], "target_name": "Q19"}
    ]


def test_get_linked_documents_multi_hop_bfs():
    provider = _linked_docs_provider()

    result = provider.get_linked_documents(["q18"], hops=2, limit=10)

    assert {d["document_id"] for d in result["documents"]} == {"q19", "q33"}


def test_get_linked_documents_is_forward_only():
    provider = _linked_docs_provider()

    result = provider.get_linked_documents(["q33"], hops=1, limit=10)

    assert result["documents"] == []
    assert result["paths"] == []


def test_get_linked_documents_clamps_hops_and_limit():
    provider = _linked_docs_provider()

    result = provider.get_linked_documents(["q18"], hops=999, limit=0)

    assert result["documents"] == [{"document_id": "q19", "name": "Q19"}]


def test_get_neighbors_clamps_hops_and_limit():
    provider = _provider()
    provider.save_entity(
        [
            {"id": "e1", "name": "Checkout", "type": "Service", "source_chunk": "c1"},
            {"id": "e2", "name": "Payments", "type": "Service", "source_chunk": "c1"},
        ]
    )
    provider.save_relationship([{"source": "e1", "relationship": "DEPENDS_ON", "target": "e2", "source_chunk": "c1"}])

    result = provider.get_neighbors(["e1"], hops=999, limit=0)

    assert result["entities"] == [{"entity_id": "e2", "name": "Payments", "entity_type": "Service"}]
    assert result["paths"] == [
        {"source_name": "Checkout", "relationship_types": ["DEPENDS_ON"], "target_name": "Payments"}
    ]


def test_query_graph_raises_not_implemented():
    provider = _provider()

    try:
        provider.query_graph("MATCH (n) RETURN n")
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass


def test_close_marks_closed():
    provider = _provider()

    provider.close()

    assert provider.closed
