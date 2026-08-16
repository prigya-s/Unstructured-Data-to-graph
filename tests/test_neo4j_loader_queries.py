"""Neo4jLoader's read methods (search_chunks/get_mentioned_entities/
get_neighbors) all take `session` as an explicit parameter rather than
opening one themselves, so they can be exercised here with a fake session
that records the Cypher/parameters it was called with - no real Neo4j
needed. Reads/writes go through session.execute_read()/execute_write()
(managed transactions, for the driver's built-in retry on transient
errors), so the fake session implements those instead of a bare .run().
get_neighbors must also clamp hops/limit to the module's defensive upper
bounds (see _MAX_HOPS/_MAX_NEIGHBOR_LIMIT) regardless of what a
misconfigured caller passes in."""

from __future__ import annotations

from graph.neo4j_loader import _MAX_HOPS, _MAX_NEIGHBOR_LIMIT, Neo4jLoader


class _FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def consume(self):
        return None


class _FakeTx:
    def __init__(self, session):
        self.session = session

    def run(self, query, **params):
        self.session.last_query = query
        self.session.last_params = params
        return _FakeResult(self.session.rows)


class _FakeSession:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or []
        self.last_query: str | None = None
        self.last_params: dict | None = None

    def execute_read(self, fn):
        return fn(_FakeTx(self))

    def execute_write(self, fn):
        return fn(_FakeTx(self))


def _loader() -> Neo4jLoader:
    return Neo4jLoader(uri="bolt://localhost:7687", user="neo4j", password="test-password")


def test_search_chunks_passes_query_vector_and_top_k():
    session = _FakeSession(rows=[{"chunk_id": "c1", "content": "hi", "document_id": "d1", "score": 0.9}])
    loader = _loader()

    result = loader.search_chunks(session, [0.1, 0.2, 0.3], top_k=5)

    assert session.last_params["query_vector"] == [0.1, 0.2, 0.3]
    assert session.last_params["top_k"] == 5
    assert result == [{"chunk_id": "c1", "content": "hi", "document_id": "d1", "score": 0.9}]


def test_get_mentioned_entities_passes_chunk_ids():
    session = _FakeSession(rows=[])
    loader = _loader()

    loader.get_mentioned_entities(session, ["c1", "c2"])

    assert session.last_params["chunk_ids"] == ["c1", "c2"]


def test_get_neighbors_clamps_hops_and_limit_within_range():
    session = _FakeSession(rows=[])
    loader = _loader()

    loader.get_neighbors(session, ["e1"], hops=2, limit=10)

    assert "*1..2" in session.last_query
    assert session.last_params["limit"] == 10


def test_get_neighbors_clamps_hops_above_max():
    session = _FakeSession(rows=[])
    loader = _loader()

    loader.get_neighbors(session, ["e1"], hops=999, limit=10)

    assert f"*1..{_MAX_HOPS}" in session.last_query


def test_get_neighbors_clamps_limit_above_max():
    session = _FakeSession(rows=[])
    loader = _loader()

    loader.get_neighbors(session, ["e1"], hops=1, limit=999999)

    assert session.last_params["limit"] == _MAX_NEIGHBOR_LIMIT


def test_get_neighbors_clamps_hops_and_limit_below_minimum():
    session = _FakeSession(rows=[])
    loader = _loader()

    loader.get_neighbors(session, ["e1"], hops=0, limit=0)

    assert "*1..1" in session.last_query
    assert session.last_params["limit"] == 1


def test_get_neighbors_shapes_entities_and_paths():
    session = _FakeSession(
        rows=[
            {
                "entity_id": "e2",
                "name": "Payments Service",
                "entity_type": "Service",
                "source_name": "Checkout",
                "relationship_types": ["DEPENDS_ON"],
            }
        ]
    )
    loader = _loader()

    result = loader.get_neighbors(session, ["e1"], hops=1, limit=10)

    assert result["entities"] == [
        {"entity_id": "e2", "name": "Payments Service", "entity_type": "Service"}
    ]
    assert result["paths"] == [
        {
            "source_name": "Checkout",
            "relationship_types": ["DEPENDS_ON"],
            "target_name": "Payments Service",
        }
    ]


def test_load_candidate_entities_batches_through_execute_write():
    session = _FakeSession()
    loader = _loader()

    count = loader.load_candidate_entities(
        session, [{"id": "e1", "name": "Checkout", "type": "Service", "source_chunk": "c1"}]
    )

    assert count == 1
    assert "CandidateEntity" in session.last_query


def test_load_candidate_relationships_uses_generic_relationship_type():
    session = _FakeSession()
    loader = _loader()

    count = loader.load_candidate_relationships(
        session, [{"source": "e1", "target": "e2", "relationship": "DEPENDS_ON", "source_chunk": "c1"}]
    )

    assert count == 1
    assert "CANDIDATE_RELATIONSHIP" in session.last_query
    assert "DEPENDS_ON" not in session.last_query


def test_load_page_hierarchy_merges_child_of_page_between_documents():
    session = _FakeSession()
    loader = _loader()

    count = loader.load_page_hierarchy(session, [{"child_id": "c1", "parent_id": "p1"}])

    assert count == 1
    assert "CHILD_OF_PAGE" in session.last_query
    assert "MERGE" in session.last_query


def test_load_page_links_merges_leads_to_with_answer_label():
    session = _FakeSession()
    loader = _loader()

    count = loader.load_page_links(
        session, [{"source_id": "q18", "target_id": "q19", "answer_label": "An adult"}]
    )

    assert count == 1
    assert "LEADS_TO" in session.last_query
    assert "MERGE" in session.last_query
    assert "answer_label" in session.last_query


def test_get_linked_documents_clamps_hops_and_limit_within_range():
    session = _FakeSession(rows=[])
    loader = _loader()

    loader.get_linked_documents(session, ["q18"], hops=2, limit=10)

    assert "*1..2" in session.last_query
    assert session.last_params["limit"] == 10


def test_get_linked_documents_clamps_hops_above_max():
    session = _FakeSession(rows=[])
    loader = _loader()

    loader.get_linked_documents(session, ["q18"], hops=999, limit=10)

    assert f"*1..{_MAX_HOPS}" in session.last_query


def test_get_linked_documents_clamps_limit_above_max():
    session = _FakeSession(rows=[])
    loader = _loader()

    loader.get_linked_documents(session, ["q18"], hops=1, limit=999999)

    assert session.last_params["limit"] == _MAX_NEIGHBOR_LIMIT


def test_get_linked_documents_is_forward_only_not_undirected():
    session = _FakeSession(rows=[])
    loader = _loader()

    loader.get_linked_documents(session, ["q18"], hops=1, limit=10)

    assert "-[rels:LEADS_TO*1..1]->" in session.last_query


def test_get_linked_documents_shapes_documents_and_paths():
    session = _FakeSession(
        rows=[
            {
                "document_id": "q19",
                "name": "MD1.50 - Q19",
                "source_name": "MD1.50 - Q18",
                "answer_labels": ["An adult"],
            }
        ]
    )
    loader = _loader()

    result = loader.get_linked_documents(session, ["q18"], hops=1, limit=10)

    assert result["documents"] == [{"document_id": "q19", "name": "MD1.50 - Q19"}]
    assert result["paths"] == [
        {
            "source_name": "MD1.50 - Q18",
            "answer_labels": ["An adult"],
            "target_name": "MD1.50 - Q19",
        }
    ]


def test_clear_candidate_graph_detach_deletes_candidate_entities():
    session = _FakeSession()
    loader = _loader()

    loader.clear_candidate_graph(session)

    assert "CandidateEntity" in session.last_query
    assert "DETACH DELETE" in session.last_query
