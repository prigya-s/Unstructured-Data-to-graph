"""
CosmosGraphProvider: placeholder GraphProvider backed by Azure Cosmos DB
(Gremlin API).

Not implemented yet. Select via graph.provider: cosmos in config.yaml once
implemented - build_production_graph()/build_candidate_graph() need a
Cosmos DB Gremlin-backed implementation (graph.cosmos.endpoint_env/key_env/
database_env from AppConfig), loading the same graph_builder.build_graph()
shape Neo4jGraphProvider does today.
"""

from __future__ import annotations

from typing import ClassVar

from config.app_config import AppConfig

from .graph_provider import GraphProvider


class CosmosGraphProvider(GraphProvider):
    _MSG: ClassVar[str] = (
        "Cosmos DB graph support is not yet implemented. Set "
        "graph.provider: neo4j (or neo4j_aura) in config.yaml to use Neo4j, "
        "or implement this class against Cosmos DB's Gremlin API."
    )

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def connect(self) -> None:
        raise NotImplementedError(self._MSG)

    def create_constraints(self) -> None:
        raise NotImplementedError(self._MSG)

    def create_indexes(self) -> None:
        raise NotImplementedError(self._MSG)

    def save_entity(self, entities: list[dict]) -> int:
        raise NotImplementedError(self._MSG)

    def save_relationship(self, relationships: list[dict]) -> int:
        raise NotImplementedError(self._MSG)

    def save_chunk(self, chunks: list[dict]) -> int:
        raise NotImplementedError(self._MSG)

    def build_candidate_graph(self, graph: dict) -> dict:
        raise NotImplementedError(self._MSG)

    def build_production_graph(self, graph: dict) -> dict:
        raise NotImplementedError(self._MSG)

    def search_chunks(self, query_vector: list[float], top_k: int) -> list[dict]:
        raise NotImplementedError(self._MSG)

    def get_mentioned_entities(self, chunk_ids: list[str]) -> list[dict]:
        raise NotImplementedError(self._MSG)

    def get_neighbors(self, entity_ids: list[str], hops: int, limit: int) -> dict:
        raise NotImplementedError(self._MSG)

    def get_linked_documents(self, document_ids: list[str], hops: int, limit: int) -> dict:
        raise NotImplementedError(self._MSG)

    def query_graph(self, cypher: str, params: dict | None = None) -> list[dict]:
        raise NotImplementedError(self._MSG)

    def close(self) -> None:
        raise NotImplementedError(self._MSG)
