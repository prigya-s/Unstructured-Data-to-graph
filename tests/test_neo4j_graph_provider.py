"""Neo4jGraphProvider must build its Neo4jLoader (and the driver/connection
pool underneath it) at most once per provider instance and reuse it across
every method call - see _get_loader()'s docstring. A regression here would
mean every retrieval call opens a fresh TLS/auth handshake to Neo4j.

Also covers the newer lifecycle/write methods (connect, create_constraints,
create_indexes, build_candidate_graph, build_production_graph) added for
the Neo4j AuraDB migration."""

from __future__ import annotations

from config.app_config import AppConfig, GraphConfig, StorageConfig
from providers.neo4j_graph_provider import Neo4jGraphProvider


class _FakeTx:
    def __init__(self, session):
        self.session = session

    def run(self, query, **params):
        self.session.last_query = query
        self.session.last_params = params
        self.session.queries.append(query)
        return _FakeResult(self.session.rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def consume(self):
        return None


class _FakeSession:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.last_query = None
        self.last_params = None
        self.queries: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute_write(self, fn):
        return fn(_FakeTx(self))

    def execute_read(self, fn):
        return fn(_FakeTx(self))


class _FakeDriver:
    def __init__(self):
        self.session_obj = _FakeSession()

    def session(self, database=None):
        return self.session_obj

    def close(self):
        pass


class _FakeNeo4jLoader:
    instances_created = 0

    def __init__(self, uri=None, user=None, password=None, database=None, connection_timeout=None):
        _FakeNeo4jLoader.instances_created += 1
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.connection_timeout = connection_timeout
        self._driver = _FakeDriver()
        self.closed = False
        self.connect_with_retry_called = False
        self.constraints_created = False
        self.indexes_created = False
        self.candidate_graph_loaded_with: dict | None = None

    def verify_connectivity(self):
        pass

    def connect_with_retry(self, attempts=3, base_delay=1.0):
        self.connect_with_retry_called = True

    def create_constraints(self):
        self.constraints_created = True

    def create_indexes(self, embedding_dimensions=None):
        self.indexes_created = True

    def load_entities(self, session, entities):
        return len(entities)

    def load_entity_relationships(self, session, relationships):
        return len(relationships)

    def load_chunks(self, session, chunks):
        return len(chunks)

    def load_graph(self, graph):
        return {"nodes_loaded": 0, "relationships_loaded": 0}

    def load_candidate_graph(self, graph):
        self.candidate_graph_loaded_with = graph
        return {"candidate_entities_loaded": len(graph["nodes"]["entities"]), "candidate_relationships_loaded": 0}

    def query_graph(self, cypher, params=None):
        return []

    def search_chunks(self, session, query_vector, top_k):
        return []

    def get_mentioned_entities(self, session, chunk_ids):
        return []

    def get_neighbors(self, session, entity_ids, hops, limit):
        return {"entities": [], "paths": []}

    def close(self):
        self.closed = True


def _config(tmp_path) -> AppConfig:
    return AppConfig(
        storage=StorageConfig(provider="local", root=str(tmp_path)),
        graph=GraphConfig(provider="neo4j"),
    )


def _provider(tmp_path, monkeypatch) -> Neo4jGraphProvider:
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
    monkeypatch.setattr("providers.neo4j_graph_provider.Neo4jLoader", _FakeNeo4jLoader)
    _FakeNeo4jLoader.instances_created = 0
    return Neo4jGraphProvider(_config(tmp_path))


def test_loader_is_built_lazily_not_at_construction(tmp_path, monkeypatch):
    _provider(tmp_path, monkeypatch)
    assert _FakeNeo4jLoader.instances_created == 0


def test_loader_is_reused_across_calls(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)

    provider.build_production_graph({"nodes": {}, "relationships": {}})
    provider.search_chunks([0.1, 0.2], top_k=5)
    provider.get_mentioned_entities(["c1"])
    provider.get_neighbors(["e1"], hops=2, limit=10)

    assert _FakeNeo4jLoader.instances_created == 1


def test_close_releases_the_loader_so_a_later_call_builds_a_new_one(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)

    provider.search_chunks([0.1], top_k=1)
    provider.close()
    provider.search_chunks([0.1], top_k=1)

    assert _FakeNeo4jLoader.instances_created == 2


def test_connect_calls_connect_with_retry(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)

    provider.connect()

    assert provider._loader.connect_with_retry_called


def test_create_constraints_delegates_to_loader(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)

    provider.create_constraints()

    assert provider._loader.constraints_created


def test_create_indexes_delegates_to_loader(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)

    provider.create_indexes()

    assert provider._loader.indexes_created


def test_build_production_graph_verifies_connectivity_and_loads(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)

    stats = provider.build_production_graph({"nodes": {}, "relationships": {}})

    assert stats == {"nodes_loaded": 0, "relationships_loaded": 0}


def test_build_candidate_graph_delegates_to_loader(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)
    graph = {"nodes": {"entities": [{"id": "e1"}]}, "relationships": {"entity_relationships": []}}

    stats = provider.build_candidate_graph(graph)

    assert provider._loader.candidate_graph_loaded_with == graph
    assert stats["candidate_entities_loaded"] == 1


def test_save_entity_batches_through_loader(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)

    count = provider.save_entity([{"id": "e1"}, {"id": "e2"}])

    assert count == 2


def test_query_graph_delegates_to_loader(tmp_path, monkeypatch):
    provider = _provider(tmp_path, monkeypatch)

    result = provider.query_graph("MATCH (n) RETURN n", {"limit": 5})

    assert result == []
