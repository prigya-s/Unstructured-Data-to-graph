"""
CosmosGraphProvider: placeholder GraphProvider backed by Azure Cosmos DB
(Gremlin API).

Not implemented yet. Select via graph.provider: cosmos in config.yaml once
implemented - publish() needs a Cosmos DB Gremlin-backed implementation
(graph.cosmos.endpoint_env/key_env/database_env from AppConfig), loading
the same graph_builder.build_graph() shape Neo4jGraphProvider does today.
"""

from __future__ import annotations

from typing import ClassVar

from config.app_config import AppConfig

from .graph_provider import GraphProvider


class CosmosGraphProvider(GraphProvider):
    _MSG: ClassVar[str] = (
        "Cosmos DB graph publishing is not yet implemented. Set "
        "graph.provider: neo4j in config.yaml to use Neo4j, or implement "
        "this class against Cosmos DB's Gremlin API."
    )

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def publish(self, graph: dict) -> dict:
        raise NotImplementedError(self._MSG)

    def search_chunks(self, query_vector: list[float], top_k: int) -> list[dict]:
        raise NotImplementedError(self._MSG)

    def get_mentioned_entities(self, chunk_ids: list[str]) -> list[dict]:
        raise NotImplementedError(self._MSG)

    def get_neighbors(self, entity_ids: list[str], hops: int, limit: int) -> dict:
        raise NotImplementedError(self._MSG)
