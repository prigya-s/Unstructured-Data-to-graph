"""
Generic, schema-driven row store for a Databricks SQL Warehouse, used by
UnityCatalogProvider and (optionally) a future Delta-backed OntologyRepository.

The point of this module: every StorageProvider table has an exact shape
already pinned down in src/contracts/schemas.py (TABLE_REGISTRY). Rather
than hand-writing CREATE TABLE / MERGE / SELECT SQL once per table (20+
methods across StorageProvider alone), this module derives that SQL from
the dataclass fields themselves. Implementing a new Delta-backed table
becomes "add one line to TABLE_REGISTRY" instead of "write four new SQL
strings" - the effort that's left after this refactor is exactly one
generic connection class, not N bespoke ones.

Connects via the Databricks SQL Connector for Python (`databricks-sql-connector`,
see requirements-databricks.txt) against a SQL Warehouse. Not exercised by
local dev (only imported when storage.provider/approval.provider selects a
Databricks-backed implementation) and not executable without a real
Databricks SQL Warehouse - same caveat as every other *_provider.py stub
this module replaces the body of.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from typing import Any

from .secrets_provider import EnvSecretsProvider, SecretsProvider

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")

_SQL_TYPES = {
    "int": "BIGINT",
    "float": "DOUBLE",
    "bool": "BOOLEAN",
}

# contracts/schemas.py has `from __future__ import annotations` (PEP 563),
# so dataclasses.fields(...).type is always the *string* the annotation was
# written as (e.g. "list[float] | None"), never a resolved type object -
# every check here has to work off that string, not isinstance/issubclass.


def _column_sql_type(field: dataclasses.Field) -> str:
    """list[...]/dict fields are stored as JSON-encoded STRING columns -
    Delta supports ARRAY/STRUCT natively, but a JSON string column keeps
    this generic helper independent of each contract's exact nested shape
    (still queryable via from_json() in Databricks SQL when needed)."""
    type_str = str(field.type)
    for py_name, sql_type in _SQL_TYPES.items():
        if type_str.startswith(py_name):
            return sql_type
    return "STRING"


def _is_structured(field: dataclasses.Field) -> bool:
    type_str = str(field.type)
    return type_str.startswith("list[") or type_str.startswith("dict")


def _encode_value(field: dataclasses.Field, value: Any) -> Any:
    if value is not None and _is_structured(field):
        return json.dumps(value)
    return value


def _decode_row(record_cls: type, row: dict) -> dict:
    decoded = dict(row)
    for f in dataclasses.fields(record_cls):
        if f.name in decoded and _is_structured(f) and isinstance(decoded[f.name], str):
            decoded[f.name] = json.loads(decoded[f.name])
    return decoded


class DeltaSqlTableStore:
    """One generic implementation of create/select/merge/overwrite, driven
    entirely by a dataclass's field names - shared by every Delta-backed
    table rather than duplicated per table."""

    def __init__(
        self,
        server_hostname_env: str = "DATABRICKS_SQL_HOST",
        http_path_env: str = "DATABRICKS_SQL_HTTP_PATH",
        access_token_env: str = "DATABRICKS_TOKEN",
        catalog: str = "kg_catalog",
        schema: str = "kg_schema",
        secrets: SecretsProvider | None = None,
    ) -> None:
        if not _IDENTIFIER_RE.match(catalog):
            raise ValueError(f"Invalid catalog name '{catalog}': must match {_IDENTIFIER_RE.pattern}.")
        if not _IDENTIFIER_RE.match(schema):
            raise ValueError(f"Invalid schema name '{schema}': must match {_IDENTIFIER_RE.pattern}.")
        self.server_hostname_env = server_hostname_env
        self.http_path_env = http_path_env
        self.access_token_env = access_token_env
        self.catalog = catalog
        self.schema = schema
        self._secrets = secrets or EnvSecretsProvider()
        self._connection = None

    def _connect(self):
        if self._connection is None:
            from databricks import sql  # optional dependency - see requirements-databricks.txt

            self._connection = sql.connect(
                server_hostname=self._secrets.get(self.server_hostname_env),
                http_path=self._secrets.get(self.http_path_env),
                access_token=self._secrets.get(self.access_token_env),
            )
        return self._connection

    def _qualified(self, table: str) -> str:
        return f"{self.catalog}.{self.schema}.{table}"

    def create_table_if_not_exists(self, table: str, record_cls: type) -> None:
        columns_sql = ", ".join(
            f"{f.name} {_column_sql_type(f)}" for f in dataclasses.fields(record_cls)
        )
        with self._connect().cursor() as cursor:
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {self._qualified(table)} ({columns_sql}) USING DELTA"
            )

    def select_all(self, table: str, record_cls: type) -> list[dict]:
        with self._connect().cursor() as cursor:
            cursor.execute(f"SELECT * FROM {self._qualified(table)}")
            columns = [d[0] for d in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return [_decode_row(record_cls, row) for row in rows]

    def overwrite_rows(self, table: str, record_cls: type, records: list[dict]) -> None:
        """Full-table replace - matches how LocalStorageProvider writes the
        bronze/silver/gold manifests today (df.write.mode("overwrite") in
        Spark terms), not an upsert."""
        self.create_table_if_not_exists(table, record_cls)
        fields = dataclasses.fields(record_cls)
        with self._connect().cursor() as cursor:
            cursor.execute(f"DELETE FROM {self._qualified(table)}")
            if records:
                self._insert_many(cursor, table, fields, records)

    def merge_rows(
        self, table: str, record_cls: type, primary_key: tuple[str, ...], records: list[dict]
    ) -> None:
        """Upsert by primary_key - the Delta-native equivalent of
        review/local_repository.py's read-modify-write-by-id pattern, made
        atomic across concurrent writers by Delta's MERGE INTO instead of
        an in-process lock."""
        if not records:
            return
        self.create_table_if_not_exists(table, record_cls)
        fields = dataclasses.fields(record_cls)
        staging = f"{table}_staging_{os.getpid()}"
        with self._connect().cursor() as cursor:
            cursor.execute(
                f"CREATE OR REPLACE TEMPORARY VIEW {staging} AS "
                f"SELECT * FROM {self._qualified(table)} WHERE 1=0"
            )
            self._insert_many(cursor, staging, fields, records, qualify=False)
            on_clause = " AND ".join(f"t.{k} = s.{k}" for k in primary_key)
            set_clause = ", ".join(f"{f.name} = s.{f.name}" for f in fields)
            insert_cols = ", ".join(f.name for f in fields)
            insert_vals = ", ".join(f"s.{f.name}" for f in fields)
            cursor.execute(
                f"MERGE INTO {self._qualified(table)} t USING {staging} s "
                f"ON {on_clause} "
                f"WHEN MATCHED THEN UPDATE SET {set_clause} "
                f"WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})"
            )

    def _insert_many(self, cursor, table: str, fields, records: list[dict], qualify: bool = True) -> None:
        target = self._qualified(table) if qualify else table
        columns = ", ".join(f.name for f in fields)
        placeholders = ", ".join("?" for _ in fields)
        rows = [
            tuple(_encode_value(f, record.get(f.name)) for f in fields) for record in records
        ]
        cursor.executemany(f"INSERT INTO {target} ({columns}) VALUES ({placeholders})", rows)


def build_delta_sql_store(options: dict, secrets: SecretsProvider | None = None) -> DeltaSqlTableStore:
    """Builds a DeltaSqlTableStore from the same options-dict shape every
    Delta-backed provider config block uses (host_env/http_path_env/
    token_env/catalog/schema - see config.databricks.example.yaml). Shared
    by UnityCatalogProvider and FutureOntoBricksRepository so the connection
    construction lives in exactly one place."""
    return DeltaSqlTableStore(
        server_hostname_env=options.get("host_env", "DATABRICKS_SQL_HOST"),
        http_path_env=options.get("http_path_env", "DATABRICKS_SQL_HTTP_PATH"),
        access_token_env=options.get("token_env", "DATABRICKS_TOKEN"),
        catalog=options.get("catalog", "kg_catalog"),
        schema=options.get("schema", "kg_schema"),
        secrets=secrets,
    )


class BlobStore:
    """For the two aggregate/"latest snapshot" documents (OntologyRecord,
    graph_export) that don't fit a row-per-record table: one row per table,
    keyed by a constant id, holding the whole document JSON-encoded in a
    single `payload` column. Backed by the same DeltaSqlTableStore
    connection/table-creation logic, not a separate persistence mechanism."""

    _KEY = "latest"

    def __init__(self, store: DeltaSqlTableStore) -> None:
        self._store = store

    def _ensure_table(self, table: str) -> None:
        with self._store._connect().cursor() as cursor:
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {self._store._qualified(table)} "
                f"(id STRING, payload STRING) USING DELTA"
            )

    def read(self, table: str) -> dict | None:
        self._ensure_table(table)
        with self._store._connect().cursor() as cursor:
            cursor.execute(
                f"SELECT payload FROM {self._store._qualified(table)} WHERE id = ?", (self._KEY,)
            )
            row = cursor.fetchone()
        return json.loads(row[0]) if row else None

    def write(self, table: str, record: dict) -> None:
        self._ensure_table(table)
        payload = json.dumps(record)
        with self._store._connect().cursor() as cursor:
            cursor.execute(f"DELETE FROM {self._store._qualified(table)} WHERE id = ?", (self._KEY,))
            cursor.execute(
                f"INSERT INTO {self._store._qualified(table)} (id, payload) VALUES (?, ?)",
                (self._KEY, payload),
            )
