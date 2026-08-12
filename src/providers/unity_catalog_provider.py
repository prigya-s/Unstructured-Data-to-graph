"""
UnityCatalogProvider: StorageProvider backed by managed Delta tables in
Unity Catalog, reached via a Databricks SQL Warehouse.

Every write_*/read_* method below is a thin call into DeltaSqlTableStore/
BlobStore (see _delta_sql.py), driven by contracts.schemas.TABLE_REGISTRY -
there is no per-table SQL hand-written here. Adding a column to a contract
is the only change needed for this class to pick it up; adding a new table
is a TABLE_REGISTRY entry, not a new method body.

Connection details (server hostname / HTTP path / access token env var
names, catalog, schema) come from config.yaml's storage.unity_catalog
block - see config.databricks.example.yaml. Requires the optional
databricks-sql-connector dependency (requirements-databricks.txt); not
exercised by local dev, and not executable without a real SQL Warehouse.
"""

from __future__ import annotations

from config.app_config import AppConfig
from contracts.schemas import TABLE_REGISTRY

from ._delta_sql import BlobStore, build_delta_sql_store
from .secrets_provider import get_secrets_provider
from .storage_provider import StorageProvider


class UnityCatalogProvider(StorageProvider):
    def __init__(self, config: AppConfig) -> None:
        options = config.storage.options.get("unity_catalog", {})
        self._store = build_delta_sql_store(options, secrets=get_secrets_provider(config))
        self._blobs = BlobStore(self._store)

    def _overwrite(self, table: str, records: list[dict]) -> None:
        record_cls, _ = TABLE_REGISTRY[table]
        self._store.overwrite_rows(table, record_cls, records)

    def _select(self, table: str) -> list[dict]:
        record_cls, _ = TABLE_REGISTRY[table]
        return self._store.select_all(table, record_cls)

    # -- bronze ---------------------------------------------------------------
    def write_documents(self, records: list[dict]) -> None:
        self._overwrite("raw_documents", records)

    def read_documents(self) -> list[dict]:
        return self._select("raw_documents")

    # -- silver -----------------------------------------------------------------
    def write_markdown(self, records: list[dict]) -> None:
        self._overwrite("markdown", records)

    def read_markdown(self) -> list[dict]:
        return self._select("markdown")

    def write_chunks(self, records: list[dict]) -> None:
        self._overwrite("chunks", records)

    def read_chunks(self) -> list[dict]:
        return self._select("chunks")

    def write_embeddings(self, records: list[dict]) -> None:
        self._overwrite("embeddings", records)

    def read_embeddings(self) -> list[dict]:
        return self._select("embeddings")

    # -- gold -------------------------------------------------------------------
    def write_entities(self, entities: list[dict], mentions: list[dict]) -> None:
        self._overwrite("entities", entities)
        self._overwrite("mentions", mentions)

    def read_entities(self) -> tuple[list[dict], list[dict]]:
        return self._select("entities"), self._select("mentions")

    def write_relationships(self, records: list[dict]) -> None:
        self._overwrite("relationships", records)

    def read_relationships(self) -> list[dict]:
        return self._select("relationships")

    def write_approved_entities(self, records: list[dict]) -> None:
        self._overwrite("approved_entities", records)

    def read_approved_entities(self) -> list[dict]:
        return self._select("approved_entities")

    def write_approved_relationships(self, records: list[dict]) -> None:
        self._overwrite("approved_relationships", records)

    def read_approved_relationships(self) -> list[dict]:
        return self._select("approved_relationships")

    def write_ontology(self, record: dict) -> None:
        self._blobs.write("ontology", record)

    def read_ontology(self) -> dict | None:
        return self._blobs.read("ontology")

    def write_graph_export(self, record: dict) -> None:
        self._blobs.write("graph_export", record)

    def read_graph_export(self) -> dict | None:
        return self._blobs.read("graph_export")

    # -- silver: candidate graph -----------------------------------------------
    def write_candidate_graph(self, record: dict) -> None:
        self._blobs.write("candidate_graph", record)

    def read_candidate_graph(self) -> dict | None:
        return self._blobs.read("candidate_graph")
