"""Confirms our own code paths route writes/reads through managed
transactions (session.execute_write/execute_read) rather than a bare
session.run() - that's what gives every batched write and read the driver's
built-in retry on transient errors (ServiceUnavailable, SessionExpired,
the errors Aura's rolling maintenance/leader elections actually raise). The
driver's internal retry behavior itself is Neo4j's tested code and isn't
re-tested here.

Also covers connect_with_retry() - the one place with a hand-rolled retry
loop, since it runs before any session/transaction exists and so isn't
covered by managed-transaction retry at all."""

from __future__ import annotations

import pytest

from graph.neo4j_loader import Neo4jLoader


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def consume(self):
        return None


class _FakeTx:
    def __init__(self, session):
        self.session = session

    def run(self, query, **params):
        self.session.run_calls += 1
        return _FakeResult(self.session.rows)


class _FakeSession:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.execute_write_calls = 0
        self.execute_read_calls = 0
        self.run_calls = 0

    def execute_write(self, fn):
        self.execute_write_calls += 1
        return fn(_FakeTx(self))

    def execute_read(self, fn):
        self.execute_read_calls += 1
        return fn(_FakeTx(self))


def _loader() -> Neo4jLoader:
    return Neo4jLoader(uri="bolt://localhost:7687", user="neo4j", password="test-password")


def test_run_batched_routes_through_execute_write_not_bare_run():
    session = _FakeSession()
    loader = _loader()

    loader._run_batched(session, "UNWIND $rows AS row MERGE (e:Entity {id: row.id})", [{"id": "e1"}])

    assert session.execute_write_calls == 1
    assert session.execute_read_calls == 0
    assert session.run_calls == 1


def test_run_batched_chunks_large_row_sets_into_separate_managed_transactions():
    session = _FakeSession()
    loader = _loader()
    rows = [{"id": str(i)} for i in range(1200)]

    count = loader._run_batched(session, "UNWIND $rows AS row MERGE (e:Entity {id: row.id})", rows)

    assert count == 1200
    assert session.execute_write_calls == 3  # 500 + 500 + 200


def test_run_read_routes_through_execute_read_not_bare_run():
    session = _FakeSession(rows=[{"chunk_id": "c1"}])
    loader = _loader()

    result = loader._run_read(session, "MATCH (c:Chunk) RETURN c.id AS chunk_id")

    assert session.execute_read_calls == 1
    assert session.execute_write_calls == 0
    assert result == [{"chunk_id": "c1"}]


def test_connect_with_retry_retries_transient_failures_then_succeeds(monkeypatch):
    loader = _loader()
    monkeypatch.setattr("graph.neo4j_loader.time.sleep", lambda seconds: None)

    calls = {"count": 0}

    def flaky_verify_connectivity():
        calls["count"] += 1
        if calls["count"] < 3:
            raise ConnectionError("transient")

    monkeypatch.setattr(loader, "verify_connectivity", flaky_verify_connectivity)

    loader.connect_with_retry(attempts=5, base_delay=0.01)

    assert calls["count"] == 3


def test_connect_with_retry_raises_after_exhausting_all_attempts(monkeypatch):
    loader = _loader()
    monkeypatch.setattr("graph.neo4j_loader.time.sleep", lambda seconds: None)

    calls = {"count": 0}

    def always_fails():
        calls["count"] += 1
        raise ConnectionError("still down")

    monkeypatch.setattr(loader, "verify_connectivity", always_fails)

    with pytest.raises(ConnectionError):
        loader.connect_with_retry(attempts=3, base_delay=0.01)

    assert calls["count"] == 3
