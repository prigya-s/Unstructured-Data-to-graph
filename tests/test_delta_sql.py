"""DeltaSqlTableStore generates its SQL from dataclass fields rather than
per-table hand-written strings - these tests assert on the generated SQL/
params against a fake DB-API connection (no real Databricks SQL Warehouse
needed), plus the catalog/schema identifier validation that closes the
config-trust SQL injection surface."""

from __future__ import annotations

import dataclasses

import pytest

from providers._delta_sql import BlobStore, DeltaSqlTableStore, build_delta_sql_store


@dataclasses.dataclass
class _Row:
    id: str
    name: str
    score: float
    tags: list[str]


class FakeCursor:
    def __init__(self, calls: list) -> None:
        self._calls = calls
        self.description = [("id",), ("name",), ("score",), ("tags",)]
        self._fetch_rows: list = []

    def execute(self, sql, params=None):
        self._calls.append(("execute", sql, params))

    def executemany(self, sql, seq_of_params):
        self._calls.append(("executemany", sql, list(seq_of_params)))

    def fetchall(self):
        return self._fetch_rows

    def fetchone(self):
        return self._fetch_rows[0] if self._fetch_rows else None

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list = []

    def cursor(self):
        return FakeCursor(self.calls)


def _store(**overrides) -> DeltaSqlTableStore:
    store = DeltaSqlTableStore(**overrides)
    store._connection = FakeConnection()
    return store


def test_catalog_must_be_a_valid_identifier():
    with pytest.raises(ValueError):
        DeltaSqlTableStore(catalog="kg_catalog; DROP TABLE x")


def test_schema_must_be_a_valid_identifier():
    with pytest.raises(ValueError):
        DeltaSqlTableStore(schema="kg_schema--comment")


def test_valid_catalog_and_schema_accepted():
    store = DeltaSqlTableStore(catalog="kg_catalog", schema="kg_schema")
    assert store.catalog == "kg_catalog"
    assert store.schema == "kg_schema"


def test_create_table_if_not_exists_generates_columns_from_fields():
    store = _store(catalog="cat", schema="sch")
    store.create_table_if_not_exists("rows", _Row)

    calls = store._connection.calls
    assert len(calls) == 1
    _, sql, _ = calls[0]
    assert "CREATE TABLE IF NOT EXISTS cat.sch.rows" in sql
    assert "id STRING" in sql
    assert "score DOUBLE" in sql
    assert "tags STRING" in sql
    assert "USING DELTA" in sql


def test_merge_rows_generates_staging_view_and_merge_statement():
    store = _store(catalog="cat", schema="sch")
    records = [{"id": "1", "name": "a", "score": 1.5, "tags": ["x"]}]

    store.merge_rows("rows", _Row, ("id",), records)

    calls = store._connection.calls
    kinds = [c[0] for c in calls]
    assert kinds == ["execute", "execute", "executemany", "execute"]

    create_sql = calls[0][1]
    assert "CREATE TABLE IF NOT EXISTS cat.sch.rows" in create_sql

    staging_sql = calls[1][1]
    assert staging_sql.startswith("CREATE OR REPLACE TEMPORARY VIEW rows_staging_")
    assert "SELECT * FROM cat.sch.rows WHERE 1=0" in staging_sql

    insert_sql, insert_rows = calls[2][1], calls[2][2]
    assert insert_sql.startswith("INSERT INTO rows_staging_")
    assert insert_rows == [("1", "a", 1.5, '["x"]')]

    merge_sql = calls[3][1]
    assert "MERGE INTO cat.sch.rows t USING rows_staging_" in merge_sql
    assert "ON t.id = s.id" in merge_sql
    assert "WHEN MATCHED THEN UPDATE SET id = s.id, name = s.name, score = s.score, tags = s.tags" in merge_sql
    assert "WHEN NOT MATCHED THEN INSERT (id, name, score, tags) VALUES (s.id, s.name, s.score, s.tags)" in merge_sql


def test_merge_rows_no_op_for_empty_records():
    store = _store(catalog="cat", schema="sch")
    store.merge_rows("rows", _Row, ("id",), [])
    assert store._connection.calls == []


def test_overwrite_rows_deletes_then_inserts():
    store = _store(catalog="cat", schema="sch")
    records = [{"id": "1", "name": "a", "score": 1.5, "tags": []}]

    store.overwrite_rows("rows", _Row, records)

    calls = store._connection.calls
    kinds = [c[0] for c in calls]
    assert kinds == ["execute", "execute", "executemany"]
    assert "DELETE FROM cat.sch.rows" in calls[1][1]


def test_select_all_decodes_json_encoded_structured_columns():
    store = _store(catalog="cat", schema="sch")
    cursor = FakeCursor(store._connection.calls)
    cursor._fetch_rows = [("1", "a", 1.5, '["x", "y"]')]
    store._connection.cursor = lambda: cursor

    rows = store.select_all("rows", _Row)

    assert rows == [{"id": "1", "name": "a", "score": 1.5, "tags": ["x", "y"]}]


def test_build_delta_sql_store_defaults():
    store = build_delta_sql_store({})
    assert store.catalog == "kg_catalog"
    assert store.schema == "kg_schema"
    assert store.server_hostname_env == "DATABRICKS_SQL_HOST"


def test_build_delta_sql_store_custom_options():
    store = build_delta_sql_store(
        {"catalog": "custom_cat", "schema": "custom_schema", "host_env": "MY_HOST"}
    )
    assert store.catalog == "custom_cat"
    assert store.schema == "custom_schema"
    assert store.server_hostname_env == "MY_HOST"


def test_blob_store_write_then_read_round_trips():
    store = _store(catalog="cat", schema="sch")
    blob = BlobStore(store)

    cursor = FakeCursor(store._connection.calls)
    store._connection.cursor = lambda: cursor

    blob.write("ontology", {"version": 1})

    cursor._fetch_rows = [('{"version": 1}',)]
    result = blob.read("ontology")

    assert result == {"version": 1}
