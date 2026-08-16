"""
Neo4jGraphProvider: wraps the existing, unmodified graph.neo4j_loader.Neo4jLoader.

Neo4jLoader itself keeps reading NEO4J_* from os.environ as a fallback -
that's unchanged, and is legitimate for direct no-args construction of that
class. This provider routes *which* secret names are read through
config.graph.options (graph.neo4j.uri_env/user_env/password_env/
database_env), and resolves those names via SecretsProvider - so a
Databricks/Azure deployment only changes secrets.provider in config.yaml
(env vars vs. Azure Key Vault), never this code.

Talks to whatever NEO4J_URI points at - local Neo4j Desktop/Docker
(bolt://...) or Neo4j AuraDB (neo4j+s://...) - the driver is scheme
agnostic, so switching between them is a config/env change only.
Neo4jAuraGraphProvider subclasses this unchanged, only tuning
Aura-appropriate defaults.
"""

from __future__ import annotations

import logging

from config.app_config import AppConfig
from graph.neo4j_loader import Neo4jLoader

from .graph_provider import GraphProvider
from .secrets_provider import get_secrets_provider

logger = logging.getLogger("kg_local.neo4j_graph_provider")


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

    def _connection_timeout(self) -> float | None:
        """Hook for subclasses (Neo4jAuraGraphProvider) to tune the default
        connection timeout without duplicating _get_loader()."""
        return None

    def _get_loader(self) -> Neo4jLoader:
        """Lazily builds one Neo4jLoader (and its underlying driver/connection
        pool) and reuses it across every method call on this provider
        instance, instead of opening a fresh driver/TLS/auth handshake per
        call - the driver itself is thread-safe and already pools
        connections internally."""
        if self._loader is None:
            timeout = self._connection_timeout()
            kwargs = {"uri": self.uri, "user": self.user, "password": self.password, "database": self.database}
            if timeout is not None:
                kwargs["connection_timeout"] = timeout
            self._loader = Neo4jLoader(**kwargs)
        return self._loader

    def connect(self) -> None:
        loader = self._get_loader()
        loader.connect_with_retry()
        logger.info("graph_operation operation=provider_connect uri=%s", self.uri)

    def create_constraints(self) -> None:
        self._get_loader().create_constraints()

    def create_indexes(self) -> None:
        self._get_loader().create_indexes()

    def save_entity(self, entities: list[dict]) -> int:
        loader = self._get_loader()
        with loader._driver.session(database=loader.database) as session:
            return loader.load_entities(session, entities)

    def save_relationship(self, relationships: list[dict]) -> int:
        loader = self._get_loader()
        with loader._driver.session(database=loader.database) as session:
            return loader.load_entity_relationships(session, relationships)

    def save_chunk(self, chunks: list[dict]) -> int:
        loader = self._get_loader()
        with loader._driver.session(database=loader.database) as session:
            return loader.load_chunks(session, chunks)

    def build_candidate_graph(self, graph: dict) -> dict:
        loader = self._get_loader()
        return loader.load_candidate_graph(graph)

    def build_production_graph(self, graph: dict) -> dict:
        loader = self._get_loader()
        loader.verify_connectivity()
        return loader.load_graph(graph)

    def query_graph(self, cypher: str, params: dict | None = None) -> list[dict]:
        return self._get_loader().query_graph(cypher, params)

    def close(self) -> None:
        if self._loader is not None:
            self._loader.close()
            self._loader = None

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

    def get_linked_documents(self, document_ids: list[str], hops: int, limit: int) -> dict:
        loader = self._get_loader()
        with loader._driver.session(database=loader.database) as session:
            return loader.get_linked_documents(session, document_ids, hops, limit)
