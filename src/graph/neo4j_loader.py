"""
Phase 7: Neo4j loader.

Connects to a local Neo4j instance using credentials from .env, creates
uniqueness constraints, and idempotently loads Document/Chunk/Entity
nodes plus HAS_CHUNK / MENTIONS / ontology relationships via batched
MERGE statements (safe to re-run without creating duplicates).
"""

from __future__ import annotations

import logging
import os

from neo4j import GraphDatabase

logger = logging.getLogger("kg_local.neo4j_loader")

# Whitelist of relationship types we allow to be interpolated into Cypher
# (Neo4j does not support parameterized relationship types). This is a
# hardcoded, static mirror of the relationship types defined in
# ontology.yaml - it is NOT derived from ontology.yaml at call time, so it
# must be kept in sync by hand if the ontology's relationship types change.
ALLOWED_RELATIONSHIP_TYPES = {
    "USES",
    "DEPENDS_ON",
    "CONNECTS_TO",
    "OWNS",
    "CONTAINS",
    "IMPLEMENTS",
    "REFERENCES",
}

_CONSTRAINTS = [
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
]

_BATCH_SIZE = 500

# Defensive upper bounds on graph expansion, applied regardless of what a
# (config-driven, not user-input-driven) caller passes in - keeps a
# misconfigured retrieval.graph_expansion_hops from turning into an
# unbounded-cost traversal.
_MAX_HOPS = 3
_MAX_NEIGHBOR_LIMIT = 100

# Seconds to wait for the initial connection/handshake to Neo4j before
# failing - the driver has no timeout by default.
_DEFAULT_CONNECTION_TIMEOUT_SECONDS = 10


class Neo4jLoader:
    def __init__(self, uri: str | None = None, user: str | None = None,
                 password: str | None = None, database: str | None = None,
                 connection_timeout: float = _DEFAULT_CONNECTION_TIMEOUT_SECONDS):
        self.uri = uri or os.environ["NEO4J_URI"]
        self.user = user or os.environ["NEO4J_USER"]
        self.password = password or os.environ["NEO4J_PASSWORD"]
        self.database = database or os.environ.get("NEO4J_DATABASE", "neo4j")
        self._driver = GraphDatabase.driver(
            self.uri, auth=(self.user, self.password), connection_timeout=connection_timeout
        )

    def close(self):
        self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def verify_connectivity(self):
        self._driver.verify_connectivity()

    def create_constraints(self):
        with self._driver.session(database=self.database) as session:
            for statement in _CONSTRAINTS:
                session.run(statement)
        logger.info("Constraints ensured (document_id, chunk_id, entity_id)")

    def _run_batched(self, session, query: str, rows: list[dict]):
        total = 0
        for i in range(0, len(rows), _BATCH_SIZE):
            batch = rows[i : i + _BATCH_SIZE]
            session.run(query, rows=batch)
            total += len(batch)
        return total

    def load_documents(self, session, documents: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (d:Document {id: row.id})
        SET d.name = row.name,
            d.source_path = row.source_path,
            d.markdown_path = row.markdown_path
        """
        return self._run_batched(session, query, documents)

    def load_chunks(self, session, chunks: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (c:Chunk {id: row.id})
        SET c.document = row.document,
            c.section_path = row.section_path,
            c.content = row.content,
            c.token_count = row.token_count,
            c.embedding = row.embedding
        """
        return self._run_batched(session, query, chunks)

    def create_vector_index(self, session, dimensions: int) -> None:
        """Idempotent - safe to call on every load_graph(). Only meaningful
        once chunks carry an `embedding` property (see load_chunks)."""
        session.run(
            """
            CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
            FOR (c:Chunk) ON c.embedding
            OPTIONS {indexConfig: {
                `vector.dimensions`: $dimensions,
                `vector.similarity_function`: 'cosine'
            }}
            """,
            dimensions=dimensions,
        )
        logger.info("Vector index ensured (chunk_embedding, dimensions=%d)", dimensions)

    def load_entities(self, session, entities: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (e:Entity {id: row.id})
        SET e.name = row.name,
            e.type = row.type,
            e.source_chunk = row.source_chunk
        """
        count = self._run_batched(session, query, entities)

        # Add the ontology type as a secondary label for richer visual
        # grouping in Neo4j Browser (e.g. :Entity:Service). APOC-free.
        by_type: dict[str, list[dict]] = {}
        for entity in entities:
            by_type.setdefault(entity["type"], []).append(entity)

        for entity_type, rows in by_type.items():
            safe_label = "".join(ch for ch in entity_type if ch.isalnum() or ch == "_")
            if not safe_label:
                continue
            label_query = f"""
            UNWIND $rows AS row
            MATCH (e:Entity {{id: row.id}})
            SET e:{safe_label}
            """
            session.run(label_query, rows=[{"id": r["id"]} for r in rows])

        return count

    def load_has_chunk(self, session, has_chunk: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MATCH (d:Document {id: row.document_id})
        MATCH (c:Chunk {id: row.chunk_id})
        MERGE (d)-[:HAS_CHUNK]->(c)
        """
        return self._run_batched(session, query, has_chunk)

    def load_mentions(self, session, mentions: list[dict]) -> int:
        query = """
        UNWIND $rows AS row
        MATCH (c:Chunk {id: row.chunk_id})
        MATCH (e:Entity {id: row.entity_id})
        MERGE (c)-[:MENTIONS]->(e)
        """
        return self._run_batched(session, query, mentions)

    def load_entity_relationships(self, session, entity_relationships: list[dict]) -> int:
        by_type: dict[str, list[dict]] = {}
        for rel in entity_relationships:
            rel_type = rel["relationship"]
            if rel_type not in ALLOWED_RELATIONSHIP_TYPES:
                logger.warning("Skipping unknown relationship type: %s", rel_type)
                continue
            by_type.setdefault(rel_type, []).append(rel)

        total = 0
        for rel_type, rows in by_type.items():
            query = f"""
            UNWIND $rows AS row
            MATCH (a:Entity {{id: row.source}})
            MATCH (b:Entity {{id: row.target}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r.source_chunk = row.source_chunk
            """
            total += self._run_batched(session, query, rows)
        return total

    def search_chunks(self, session, query_vector: list[float], top_k: int) -> list[dict]:
        result = session.run(
            """
            CALL db.index.vector.queryNodes('chunk_embedding', $top_k, $query_vector)
            YIELD node, score
            RETURN node.id AS chunk_id, node.content AS content,
                   node.document AS document_id, score
            ORDER BY score DESC
            """,
            top_k=top_k,
            query_vector=query_vector,
        )
        return [dict(record) for record in result]

    def get_mentioned_entities(self, session, chunk_ids: list[str]) -> list[dict]:
        result = session.run(
            """
            MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
            WHERE c.id IN $chunk_ids
            RETURN DISTINCT e.id AS entity_id, e.name AS name, e.type AS entity_type
            """,
            chunk_ids=chunk_ids,
        )
        return [dict(record) for record in result]

    def get_neighbors(self, session, entity_ids: list[str], hops: int, limit: int) -> dict:
        safe_hops = max(1, min(int(hops), _MAX_HOPS))
        safe_limit = max(1, min(int(limit), _MAX_NEIGHBOR_LIMIT))
        result = session.run(
            """
            MATCH (e:Entity)-[rels*1..%d]-(n:Entity)
            WHERE e.id IN $entity_ids AND NOT n.id IN $entity_ids
            RETURN DISTINCT n.id AS entity_id, n.name AS name, n.type AS entity_type,
                   e.name AS source_name,
                   [rel IN rels | type(rel)] AS relationship_types
            LIMIT $limit
            """
            % safe_hops,
            entity_ids=entity_ids,
            limit=safe_limit,
        )
        entities: dict[str, dict] = {}
        paths: list[dict] = []
        for record in result:
            row = dict(record)
            entities[row["entity_id"]] = {
                "entity_id": row["entity_id"],
                "name": row["name"],
                "entity_type": row["entity_type"],
            }
            paths.append(
                {
                    "source_name": row["source_name"],
                    "relationship_types": row["relationship_types"],
                    "target_name": row["name"],
                }
            )
        return {"entities": list(entities.values()), "paths": paths}

    def load_graph(self, graph: dict) -> dict:
        """Load a full graph JSON document (as produced by graph_builder).
        Returns a stats dict of nodes/relationships loaded."""
        self.create_constraints()

        stats = {}
        with self._driver.session(database=self.database) as session:
            stats["documents_loaded"] = self.load_documents(session, graph["nodes"]["documents"])
            stats["chunks_loaded"] = self.load_chunks(session, graph["nodes"]["chunks"])

            embedded_chunk = next(
                (c for c in graph["nodes"]["chunks"] if c.get("embedding")), None
            )
            if embedded_chunk is not None:
                self.create_vector_index(session, len(embedded_chunk["embedding"]))

            stats["entities_loaded"] = self.load_entities(session, graph["nodes"]["entities"])
            stats["has_chunk_loaded"] = self.load_has_chunk(
                session, graph["relationships"]["has_chunk"]
            )
            stats["mentions_loaded"] = self.load_mentions(
                session, graph["relationships"]["mentions"]
            )
            stats["entity_relationships_loaded"] = self.load_entity_relationships(
                session, graph["relationships"]["entity_relationships"]
            )

        stats["nodes_loaded"] = (
            stats["documents_loaded"] + stats["chunks_loaded"] + stats["entities_loaded"]
        )
        stats["relationships_loaded"] = (
            stats["has_chunk_loaded"]
            + stats["mentions_loaded"]
            + stats["entity_relationships_loaded"]
        )
        return stats
