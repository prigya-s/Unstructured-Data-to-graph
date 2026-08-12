"""Neo4jGraphProvider must build its Neo4jLoader (and the driver/connection
pool underneath it) at most once per provider instance and reuse it across
every method call - see _get_loader()'s docstring. A regression here would
mean every retrieval call opens a fresh TLS/auth handshake to Neo4j."""

from __future__ import annotations

from config.app_config import AppConfig, GraphConfig, StorageConfig
from providers.neo4j_graph_provider import Neo4jGraphProvider


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDriver:
    def session(self, database=None):
        return _FakeSession()

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
        self._driver = _FakeDriver()
        self.closed = False

    def verify_connectivity(self):
        pass

    def load_graph(self, graph):
        return {"nodes_loaded": 0, "relationships_loaded": 0}

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

    provider.publish({"nodes": {}, "relationships": {}})
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
