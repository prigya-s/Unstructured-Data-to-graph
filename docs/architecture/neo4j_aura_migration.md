# Neo4j AuraDB Migration: GraphProvider Refactor

## Summary

kg-local no longer requires a locally-running Neo4j Desktop/Docker instance.
The graph layer now runs against **either** a local Neo4j (`bolt://`/`neo4j://`)
**or** Neo4j AuraDB (`neo4j+s://`) — selectable purely by configuration, with
no code changes and no functionality removed. A `MockGraphProvider` also
lets the app and full pipeline run with zero live database at all (useful
for local dev and CI).

This was a refactor of the graph infrastructure only — no business logic,
retrieval semantics, or governance boundaries were rebuilt or changed.

## Architectural changes

### GraphProvider interface (`src/providers/graph_provider.py`)

All graph access goes through the `GraphProvider` abstract base class — no
code outside `src/providers/` and `src/graph/` ever imports the Neo4j driver
directly. The interface now covers the full graph lifecycle:

| Method | Purpose |
|---|---|
| `connect()` | Establish/verify connectivity, with retry |
| `create_constraints()` | Idempotent uniqueness constraints |
| `create_indexes()` | Idempotent indexes (vector index once embeddings exist) |
| `save_entity(entities)` | Batched upsert of `:Entity` nodes |
| `save_relationship(relationships)` | Batched upsert of entity relationships |
| `save_chunk(chunks)` | Batched upsert of `:Chunk` nodes |
| `build_candidate_graph(graph)` | Load the Silver-tier candidate graph |
| `build_production_graph(graph)` | Load the full Gold-tier graph (was `publish()`) |
| `search_chunks(query_vector, top_k)` | Vector search retrieval (unchanged) |
| `get_mentioned_entities(chunk_ids)` | Entity retrieval (unchanged) |
| `get_neighbors(entity_ids, hops, limit)` | Graph expansion retrieval (unchanged) |
| `query_graph(cypher, params)` | Generic parameterized read-only escape hatch |
| `close()` | Release the driver/connection pool |

The three named retrieval methods are unchanged in behavior and Cypher —
GraphRAG retrieval already depended on them by name, and the governance
rule that retrieval only ever sees Gold-tier data is enforced by their
`MATCH`/label clauses, which were not touched.

### Provider implementations (`src/providers/`)

- **`Neo4jGraphProvider`** — the concrete implementation backing both local
  Neo4j and (via subclass) Aura. Wraps `graph/neo4j_loader.py`'s
  `Neo4jLoader`, built lazily and reused across every call on the provider
  instance (one driver/connection pool per provider, not per call).
- **`Neo4jAuraGraphProvider`** — thin subclass of `Neo4jGraphProvider`. Same
  code path (the driver is already scheme-agnostic), only overriding the
  default connection timeout (30s, vs 10s for local — cloud round trips and
  possible instance resume on the free tier) and tagging connect logs with
  `target=aura`.
- **`CosmosGraphProvider`** — stub implementing the full interface, every
  method raising `NotImplementedError`. Reserved for a future Cosmos DB
  Gremlin/graph backend; fixes a latent bug where this provider name was
  registered in the factory but the file didn't exist.
- **`MockGraphProvider`** — full in-memory implementation (dicts/lists, no
  network). Lets `graph.provider: mock` run the entire pipeline and app with
  no live database — used by the test suite and available for local dev.

Selecting an implementation is one config line (`graph.provider`); nothing
else in the codebase branches on which one is active.

### Candidate Graph now also writes to Neo4j (Silver tier)

The existing Candidate Graph (`review/candidate_graph.py`) is unchanged — it
still produces a pure JSON document consumed by the review UI. What's new:
`CandidateGraphStage` now also calls
`graph_provider.build_candidate_graph(candidate_graph)`, which loads those
same pending entities/relationships into the graph database under **distinct
labels**:

- `:CandidateEntity` nodes (not `:Entity`)
- A single generic `:CANDIDATE_RELATIONSHIP` edge type, with the real
  semantic relationship name stored as a `relationship_type` property
  (avoids growing the relationship-type whitelist for unapproved data)

Every retrieval Cypher statement (`search_chunks`, `get_mentioned_entities`,
`get_neighbors`) only ever matches `:Entity`/`:Chunk`/`:Document` and the
existing whitelisted relationship types — it is structurally blind to
`:CandidateEntity` nodes. **The Gold-only-for-retrieval invariant is
unchanged**, even though Candidate Graph data now physically exists in the
same database.

Each pipeline run fully refreshes the candidate tier (`DETACH DELETE` on all
`:CandidateEntity` nodes, then reload) — mirroring how the JSON export is
fully overwritten each run, so approve/reject/merge transitions are always
reflected exactly, with no incremental-delete bookkeeping.

### Reliability: retries, timeouts, batching

- **Writes and reads go through managed transactions**
  (`session.execute_write` / `session.execute_read`) instead of bare
  `session.run()`. This gives the driver's built-in retry on transient
  errors (`ServiceUnavailable`, `SessionExpired` — what Aura's rolling
  maintenance and leader elections actually raise) to every batched write
  and every read, at the correct transaction granularity.
- **`connect_with_retry(attempts=3, base_delay=1.0)`** wraps the initial
  connectivity check with exponential backoff. This is the one place with a
  hand-rolled retry loop, since it runs before any session/transaction
  exists and so isn't covered by managed-transaction retry.
- **Connection timeout** is explicit (10s local default, 30s for Aura) —
  the driver has no timeout by default.
- **Batching**: all writes go through `UNWIND $rows AS row` + `MERGE`,
  chunked at 500 rows per transaction (`_BATCH_SIZE`). No row-by-row writes
  anywhere in the loader.
- **Idempotency**: constraints and indexes use `IF NOT EXISTS`; entity/chunk/
  relationship loads use `MERGE`. Safe to re-run `create_constraints()` /
  `create_indexes()` / a full pipeline run any number of times.

### Startup initialization (`src/graph/startup.py`)

`initialize_graph(provider)` calls `connect()` → `create_constraints()` →
`create_indexes()` in order, idempotently. Called:

- Once per CLI invocation, from `build_context()` in `main.py` — covers
  `ingest` (which runs through `CandidateGraphStage`, now a graph-writing
  stage) and `publish-graph`.
- Once per Streamlit process, from `app/common.py`'s `get_graph_provider()`,
  guarded by a module-level flag so reruns don't repeat it. (The app has
  since been rebuilt as FastAPI + React; the same once-per-process
  initialization now happens via `api/deps.py`.)

### Observability

Structured log lines (`logger.info`/`logger.warning`, key=value text inside
the existing JSON log envelope — no changes to `JsonFormatter`) are emitted
for: connect attempts (including each retry and final success/failure),
close, constraint/index creation, and every batched write/read with row
count and duration in milliseconds. Example:

```
graph_operation operation=connect uri=neo4j+s://xxxx.databases.neo4j.io database=neo4j attempt=1 status=ok
graph_operation operation=write rows=500 duration_ms=142
graph_operation operation=read rows=8 duration_ms=23
```

## Configuration

### `graph.provider` values

| Value | Backend | Notes |
|---|---|---|
| `neo4j` | Local Neo4j Desktop/Docker | `NEO4J_URI=bolt://...` or `neo4j://...` |
| `neo4j_aura` | Neo4j AuraDB (cloud) | `NEO4J_URI=neo4j+s://<dbid>.databases.neo4j.io` |
| `cosmos` | *(not yet implemented)* | Raises `NotImplementedError` |
| `mock` | In-memory, no database | For local dev/tests |

### Example: local Neo4j (unchanged)

```yaml
graph:
  provider: neo4j
  neo4j:
    uri_env: NEO4J_URI
    user_env: NEO4J_USER
    password_env: NEO4J_PASSWORD
    database_env: NEO4J_DATABASE
```

```
# .env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<your local password>
NEO4J_DATABASE=neo4j
```

### Example: Neo4j AuraDB

```yaml
graph:
  provider: neo4j_aura
  neo4j:
    uri_env: NEO4J_URI
    user_env: NEO4J_USER
    password_env: NEO4J_PASSWORD
    database_env: NEO4J_DATABASE
```

```
# .env
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<generated when the Aura instance was created>
NEO4J_DATABASE=neo4j
```

Switching between the two is exactly the two changes above (`graph.provider`
+ the `NEO4J_*` values) — no other file changes. Credential *names* are
config-driven (`graph.neo4j.*_env`); credential *values* are resolved
through `SecretsProvider` (env vars locally, Azure Key Vault in
Databricks/production), never hardcoded.

### Deployment modes (both config-only)

- **Mode 1 — local app + Aura**: run `main.py`/Streamlit locally as today,
  with `graph.provider: neo4j_aura` and Aura credentials in `.env`.
- **Mode 2 — Databricks + Aura**: same `graph.provider: neo4j_aura`, with
  `secrets.provider: azure_key_vault` so credentials resolve from Key Vault
  instead of a local `.env` file. See `config.databricks.example.yaml` for
  the rest of the Databricks-mode provider values (storage, embedding,
  approval) — the graph section is identical to Mode 1 aside from secrets
  resolution.

## Neo4j AuraDB setup guide

1. Create a free or paid AuraDB instance at https://console.neo4j.io.
   - **Instance tier**: any tier supports the vector index used here
     (`db.index.vector.queryNodes`, available since Neo4j 5.11 / all
     current Aura tiers). Pick a tier sized for your expected node/
     relationship volume; the free tier is sufficient for development.
2. On creation, Aura generates and shows the initial password **once** —
   save it immediately (a Key Vault secret in production, `.env` locally).
3. Copy the **Connection URI** shown on the instance page — it will look
   like `neo4j+s://xxxxxxxx.databases.neo4j.io`. The `neo4j+s://` scheme is
   required for Aura and implies TLS automatically; no separate TLS
   configuration is needed.
4. Set `NEO4J_URI`, `NEO4J_USER` (default `neo4j`), `NEO4J_PASSWORD`, and
   `NEO4J_DATABASE` (default `neo4j`) — locally in `.env`, or as Key Vault
   secrets in Databricks/production (named per `graph.neo4j.*_env` in
   `config.yaml`).
5. Set `graph.provider: neo4j_aura` in `config.yaml`.
6. Run the app/pipeline as usual. `initialize_graph()` runs automatically on
   startup and idempotently creates constraints and indexes — no manual
   schema setup step is required.

## Migration checklist

- [ ] Create an Aura instance and record its URI + generated password.
- [ ] Add `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` / `NEO4J_DATABASE`
      to `.env` (local) or Key Vault (Databricks/production).
- [ ] Set `graph.provider: neo4j_aura` in `config.yaml` (or leave as
      `neo4j` to keep using local Neo4j — both remain fully supported).
- [ ] Run `pytest tests/ -q` — should be green with the two Aura
      integration tests skipped (no live Aura credentials in the test env).
- [ ] Optionally run `tests/test_neo4j_aura_integration.py` against a real
      (ideally disposable) Aura instance by setting
      `NEO4J_AURA_TEST_URI` / `NEO4J_AURA_TEST_USER` /
      `NEO4J_AURA_TEST_PASSWORD`.
- [ ] Run `python src/main.py ingest` and `python src/main.py publish-graph`
      (or the Streamlit app) once against Aura to confirm constraints/
      indexes are created and a full pipeline round trip succeeds.

## Files changed

The `app/` files below reflect the Streamlit UI that existed at the time of
this migration; that UI has since been fully rebuilt as FastAPI (`api/`) +
React (`web/`), and none of the listed `app/` files exist anymore. The
equivalent initialization today lives in `api/deps.py`.

- `src/providers/graph_provider.py` — redesigned `GraphProvider` ABC (13 methods)
- `src/graph/neo4j_loader.py` — retries, managed transactions, `create_indexes()`,
  candidate graph loads, structured logging
- `src/providers/neo4j_graph_provider.py` — implements the full interface
- `src/providers/neo4j_aura_graph_provider.py` — new, Aura-tuned subclass
- `src/providers/cosmos_graph_provider.py` — updated stub, full interface
- `src/providers/mock_graph_provider.py` — new, in-memory implementation
- `src/providers/__init__.py` — factory dispatch for `neo4j_aura`/`mock`
- `src/graph/startup.py` — new, `initialize_graph()`
- `src/pipeline/stages/graph_stage.py` — `publish()` → `build_production_graph()`
- `src/pipeline/stages/candidate_graph_stage.py` — now also writes to the graph
- `src/config/app_config.py` — new `environment` field
- `config.yaml` — `environment` key, documented `graph.provider` values, Aura example
- `src/main.py` — calls `initialize_graph()` at startup
- `app/common.py` — new `get_graph_provider()` with once-per-process init guard
- `app/pages/publish.py`, `app/pages/chat.py` — use `get_graph_provider()`,
  provider-neutral UI copy (no longer Neo4j-specific)
- Tests: `tests/test_neo4j_graph_provider.py`, `tests/test_neo4j_loader_queries.py`,
  `tests/test_stage_statelessness.py` (updated); `tests/test_mock_graph_provider.py`,
  `tests/test_graph_provider_interface.py`, `tests/test_neo4j_retry.py`,
  `tests/test_neo4j_aura_integration.py` (new)

## Verification performed

- `pytest tests/ -q` — 107 passed, 2 skipped (Aura integration tests, no
  live credentials in this environment).
- Confirmed no remaining `.publish(` call sites and no remaining bare
  `session.run(` usages outside comments/docstrings — all writes/reads route
  through `build_production_graph()`/`build_candidate_graph()` and managed
  transactions.
- Confirmed `search_chunks`/`get_mentioned_entities`/`get_neighbors` Cypher
  is unchanged from before this refactor — retrieval remains structurally
  blind to `:CandidateEntity` data.
