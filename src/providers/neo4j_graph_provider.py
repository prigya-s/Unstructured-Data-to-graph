"""
Neo4jGraphProvider: wraps the existing, unmodified graph.neo4j_loader.Neo4jLoader.

Neo4jLoader itself keeps reading NEO4J_* from os.environ as a fallback -
that's unchanged, and is legitimate for direct no-args construction of that
class. This provider routes *which* secret names are read through
config.graph.options (graph.neo4j.uri_env/user_env/password_env/
database_env), and resolves those names via SecretsProvider - so a
Databricks/Azure deployment only changes secrets.provider in config.yaml
(env vars vs. Azure Key Vault), never this code.
"""

from __future__ import annotations

from config.app_config import AppConfig
from graph.neo4j_loader import Neo4jLoader

from .graph_provider import GraphProvider
from .secrets_provider import get_secrets_provider


class Neo4jGraphProvider(GraphProvider):
    def __init__(self, config: AppConfig) -> None:
        neo4j_options = config.graph.options.get("neo4j", {})
        secrets = get_secrets_provider(config)
        self.uri = secrets.get(neo4j_options.get("uri_env", "NEO4J_URI"))
        self.user = secrets.get(neo4j_options.get("user_env", "NEO4J_USER"))
        self.password = secrets.get(neo4j_options.get("password_env", "NEO4J_PASSWORD"))
        self.database = secrets.get(neo4j_options.get("database_env", "NEO4J_DATABASE"))

        missing = [
            label
            for label, value in (("uri", self.uri), ("user", self.user), ("password", self.password))
            if not value
        ]
        if missing:
            raise ValueError(
                f"Neo4j connection is missing required secret(s): {', '.join(missing)}. "
                "Check graph.neo4j.*_env in config.yaml and that secrets.provider can resolve them."
            )
        self._loader: Neo4jLoader | None = None

    def _get_loader(self) -> Neo4jLoader:
        """Lazily builds one Neo4jLoader (and its underlying driver/connection
        pool) and reuses it across every method call on this provider
        instance, instead of opening a fresh driver/TLS/auth handshake per
        call - the driver itself is thread-safe and already pools
        connections internally."""
        if self._loader is None:
            self._loader = Neo4jLoader(
                uri=self.uri, user=self.user, password=self.password, database=self.database
            )
        return self._loader

    def close(self) -> None:
        if self._loader is not None:
            self._loader.close()
            self._loader = None

    def publish(self, graph: dict) -> dict:
        loader = self._get_loader()
        loader.verify_connectivity()
        return loader.load_graph(graph)

    def search_chunks(self, query_vector: list[float], top_k: int) -> list[dict]:
        loader = self._get_loader()
        with loader._driver.session(database=loader.database) as session:
            return loader.search_chunks(session, query_vector, top_k)

    def get_mentioned_entities(self, chunk_ids: list[str]) -> list[dict]:
        loader = self._get_loader()
        with loader._driver.session(database=loader.database) as session:
            return loader.get_mentioned_entities(session, chunk_ids)

    def get_neighbors(self, entity_ids: list[str], hops: int, limit: int) -> dict:
        loader = self._get_loader()
        with loader._driver.session(database=loader.database) as session:
            return loader.get_neighbors(session, entity_ids, hops, limit)
