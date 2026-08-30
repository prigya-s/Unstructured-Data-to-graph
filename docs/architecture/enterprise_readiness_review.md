# Enterprise Readiness Review: Azure / Databricks Architecture, Security & Scalability

> **Historical audit.** This review was performed against the Streamlit app
> (`app/common.py`, `app/pages/*.py`) that existed at the time. That app has
> since been fully replaced by the FastAPI (`api/`) + React (`web/`) stack
> described in the current [README](../../README.md) — so any finding below
> that names an `app/` file is describing a problem that was fixed in code
> which no longer exists, not a gap in the current stack. The test count in
> the Testing section below is likewise a snapshot from when this review was
> written, not the current count. See
> [production_readiness_review.md](production_readiness_review.md) for the
> most recent full review.

Reviewed against the Azure Well-Architected Framework, Databricks Lakehouse
best practices, cloud-native architecture principles, and enterprise security
standards. Scope: architecture, code quality, security, authentication,
authorization, secrets management, data contracts, pipeline design,
performance, scalability, testing, and observability. Constraint honored
throughout: **no business functionality was added** - every refactor below is
infrastructure, architecture, or a scoped bug fix; extraction/chunking/
relationship logic, ontology generation, and graph loading behavior are
byte-identical to before this pass (see `docs/architecture/migration_assessment.md`
for the prior provider-pattern refactor this one builds on).

Baseline production readiness score at the start of this pass: **48/100**.
Current score after the refactors below: **80/100**. Scoring rationale and
remaining gaps are at the end of this document.

## Architecture Review

**Provider pattern & Bronze/Silver/Gold** - already in place from the prior
refactor (`docs/architecture/review_board_assessment.md`) and unchanged here:
every stage depends on an ABC (`StorageProvider`, `DocumentSource`,
`EmbeddingProvider`, `ApprovalProvider`/`OntologyRepository`,
`OntologyProvider`, `GraphProvider`), never a concrete class. This pass added
two more provider seams to close gaps the earlier review flagged but didn't
yet resolve:

- `SecretsProvider` (`src/providers/secrets_provider.py`) - `EnvSecretsProvider`
  (today's behavior) and `AzureKeyVaultSecretsProvider` (Managed Identity via
  `DefaultAzureCredential`, deferred SDK import). `Neo4jGraphProvider` and
  `DeltaSqlTableStore._connect()` now resolve credentials through this
  interface instead of calling `os.environ.get()` directly - switching to Key
  Vault is a `secrets.provider: azure_key_vault` config change, not a code
  change.
- `AuthProvider` (`src/providers/auth_provider.py`) - `LocalAuthProvider`
  (today's free-text sidebar identity, explicitly dev-only) and
  `AzureADAuthProvider` (validates the identity Databricks Apps or an Azure AD
  auth proxy already injects at the platform layer; raises
  `NotImplementedError` until wired to a real header/claim source).

**CRITICAL - Stages 2-7 were not independently restartable.** `ChunkingStage`
through `ApprovalStage` read their inputs from `ctx.<field>` (the prior
stage's in-memory Python object) instead of from `StorageProvider`, while
`GraphStage`/`OntologyStage` already did it correctly. This meant a stage
could only run correctly as part of a single `run_all()` process - the exact
opposite of "each stage is a Databricks Workflow task." **Impact if
unresolved**: any attempt to run stages as separate Databricks Workflow tasks
(the explicit target architecture) would silently process empty/stale data,
because a fresh task process has no in-memory `ctx` from a prior task.
**Resolved**: every stage (`extraction_stage.py`, `chunking_stage.py`,
`embedding_stage.py`, `entity_extraction_stage.py`,
`relationship_extraction_stage.py`, `approval_stage.py`) now reads its inputs
via `ctx.storage.read_*()` at the top of `run()`, matching the pattern
`GraphStage`/`OntologyStage` already used. Proven by
`tests/test_stage_statelessness.py`, which constructs a fresh
`PipelineContext` (all in-memory fields at their empty default) per stage and
asserts the stage's output is sourced from a fake `StorageProvider`, not the
empty ctx.

**HIGH - `app/pages/publish.py` bypassed the provider layer.** It called
`review.publisher.publish_graph()` directly with its own unconfigured
`Neo4jLoader()` and pre-refactor `output/` paths, duplicating the "no
approved concepts" guard `OntologyStage`/`GraphStage` already implement
correctly. **Impact if unresolved**: the Streamlit publish flow would use
different credentials/paths than the CLI, and any future change to
`GraphProvider` config wouldn't apply to the app. **Resolved**: rewritten to
build a `PipelineContext` and run `OntologyStage`/`GraphStage` via
`PipelineRunner`, identical to `main.py:run_publish_ontology/run_publish_graph`.

## Security Review

**CRITICAL - No Managed Identity / Key Vault readiness.** All secrets
(`NEO4J_PASSWORD`, Databricks tokens) were read directly via
`os.environ.get()` scattered across provider constructors, with no
abstraction to swap to a vault-backed source. **Impact if unresolved**:
production deployment would require either committing to plaintext env vars
permanently or a second refactor pass under deployment pressure.
**Resolved**: see the `SecretsProvider` seam above. `Neo4jGraphProvider` now
raises a clear `ValueError` if a required secret resolves to `None` at
construction time, instead of silently passing `None` into `Neo4jLoader` and
relying on its own hardcoded fallback - credential-resolution failures now
surface at startup, not at first query.

**CRITICAL - Committed secret, no `.gitignore`.** A live `NEO4J_PASSWORD`
value was present in a tracked `.env`-adjacent file, and no `.gitignore`
existed to prevent `.venv/`, `lakehouse/`, `output/`, `logs/`, or future
`.env` files from being committed. **Impact if unresolved**: credential
leakage on any push to a shared remote. **Resolved**: `.gitignore` added
covering `.env`, `.venv/`, `lakehouse/`, `output/`, `logs/`, `__pycache__/`,
`*.pyc`. Rotating the actual leaked `NEO4J_PASSWORD` value is a user action
against their own Neo4j instance - listed under Remaining Gaps, not silently
skipped.

**CRITICAL - No RBAC on the review/approval app.** The Streamlit sidebar
accepted a free-text reviewer name with no role concept, so any user could
approve/reject/merge ontology candidates. **Impact if unresolved**: no
enforceable separation between "can propose" and "can approve" in a
multi-user enterprise deployment, and audit history entries were
self-reported strings. **Resolved**: see the `AuthProvider` seam above -
`LocalAuthProvider` returns a fixed `roles=["reviewer","approver"]` object
(still dev-only, but now a typed seam instead of a text box); every history
entry is sourced from `providers.get_auth_provider(config).current_user()`.
Enforcing role-gated UI actions and wiring `AzureADAuthProvider` to a real
identity source remain gaps - see below.

**MEDIUM - Config-trust SQL injection surface.** `DeltaSqlTableStore`
interpolated `catalog`/`schema` from config directly into SQL identifiers
with no validation. **Impact if unresolved**: a malformed or malicious
`config.yaml` value could inject arbitrary SQL into every generated
statement. **Resolved**: `catalog`/`schema` are validated against
`^[A-Za-z0-9_]+$` at `DeltaSqlTableStore.__init__`, raising `ValueError`
otherwise. Covered by `tests/test_delta_sql.py`.

## Scalability Review

**HIGH - O(N) repository round trips for candidate persistence.**
`candidate_builder.build_candidates()` called `save_candidate_entity()`/
`save_candidate_relationship()` once per row inside its loop - for
`LocalOntologyRepository` this meant one full read-modify-write of the entire
JSON file per entity/relationship; for a future Delta-backed repository it
would mean one `MERGE INTO` per row. **Impact if unresolved**: ingestion
throughput would degrade linearly (worse for the local JSON backend, whose
read-modify-write is itself O(file size) per call) as document volume grows -
directly contradicts the "batch operations, no unnecessary loops" requirement.
**Resolved**: `OntologyRepository` gained `save_candidate_entities()`/
`save_candidate_relationships()` (batch methods, with a safe per-row-loop
default for any backend that doesn't override); `LocalOntologyRepository`
overrides both with a true single read-modify-write for the whole batch;
`FutureOntoBricksRepository` overrides both to call
`DeltaSqlTableStore.merge_rows()` once with the full list. `build_candidates()`
now collects rows during its loop and calls each batch method exactly once.
Proven by `tests/test_candidate_builder_batching.py`, whose fake repository
raises if the per-row methods are ever called.

**HIGH - Dead code masking a real dedup bug.** In
`relationship_extractor.py`, a `seen_global` set was populated but never
checked before appending to `all_relationships` - duplicate relationships
across chunks were never filtered at the document level (only within a
single chunk). **Impact if unresolved**: relationship counts and downstream
graph edge counts would over-report, growing with document overlap/repetition
without bound. **Resolved**: added the missing
`if key in seen_global: continue` guard, matching the per-chunk pattern
already used in `extract_relationships_from_chunk`.

**MEDIUM - No structured observability.** Logs were plain text with no
correlation id, so a Databricks Workflow run spanning multiple tasks/log
files couldn't be reconstructed as one run. **Impact if unresolved**:
production incident investigation would require manually correlating log
files by timestamp proximity, not a queryable run id. **Resolved**:
`main.py` generates one `uuid4()` `run_id` per CLI invocation, stamps it onto
every log record via a `logging.Filter` attached to each `Handler` (so it
applies regardless of which module's logger emitted the record), and writes
the file handler's output as one JSON object per line
(timestamp/level/logger/run_id/message/exc_info) while keeping the console
handler human-readable. `observability.log_dir` and `ontology.schema_path`
are now `AppConfig` properties read from `config.yaml` instead of hardcoded
module constants, defaulting to the prior paths so behavior is unchanged
unless overridden.

**MEDIUM - Duplicated provider-construction boilerplate.** `_delta_sql.py`
construction (`host_env`/`http_path_env`/`token_env`/`catalog`/`schema` →
`DeltaSqlTableStore(...)`) was repeated in every Delta-backed provider.
**Resolved**: added `build_delta_sql_store(options, secrets)` in
`_delta_sql.py`; `FutureOntoBricksRepository`/`UnityCatalogProvider` now call
it instead of each repeating the same options-dict unpacking.

**MEDIUM - Dead `execution_mode`/`FeatureFlags` config.** Both were fully
redundant with each section's own `provider` key (already the real selector)
and were never read by any code path - a maintainability hazard (two knobs
appearing to control behavior when only one did) more than a functional bug.
**Resolved**: removed from `AppConfig`, `config.yaml`,
`config.databricks.example.yaml`; corrected the `providers/__init__.py`
docstring's inaccurate "read here, once, at startup" claim.

## Testing

Zero test coverage existed before this pass. Added a pytest suite covering
the architectural seams identified as highest-risk (not exhaustive business
logic coverage, by explicit scope decision):

| File | Coverage |
|---|---|
| `tests/test_provider_factories.py` | All 8 `get_*_provider()` factories resolve the class matching config, raise `ValueError` on an unknown value. |
| `tests/test_stage_statelessness.py` | Each of the 6 fixed stages reads from a fake `StorageProvider` against a fresh `PipelineContext` - the direct proof of the CRITICAL 1 fix. |
| `tests/test_delta_sql.py` | Catalog/schema identifier validation; generated SQL for create/select/overwrite/merge against a fake DB-API connection; `build_delta_sql_store()` defaults and overrides. |
| `tests/test_candidate_builder_batching.py` | Batch save methods called exactly once regardless of row count; decided-status rows (APPROVED/REJECTED/MERGED) still skipped. |

41 tests, all passing (`pytest tests/`) at the time of this review — the suite
has grown substantially since (see [production_readiness_review.md](production_readiness_review.md)
for a more recent count).

## Production Readiness Score: 80/100

| Category | Before | After | Rationale |
|---|---|---|---|
| Architecture / provider pattern | 8/10 | 9/10 | Stage statelessness gap (CRITICAL 1) closed; provider seams now cover secrets and auth in addition to the original 6. |
| Security / secrets management | 2/10 | 8/10 | Managed Identity / Key Vault seam implemented and wired; committed-secret exposure closed via `.gitignore`. Real vault not yet deployed against - see gaps. |
| Authentication / authorization | 1/10 | 5/10 | `AuthProvider` seam exists with a typed role model; `AzureADAuthProvider` is a real interface but still a stub, and no UI action is yet role-gated. |
| Scalability / performance | 4/10 | 8/10 | O(N) repository round trips eliminated; dead dedup bug fixed. Not yet load-tested at enterprise document volume. |
| Data contracts / pipeline design | 7/10 | 8/10 | All stages now genuinely restartable/idempotent per the target Workflow-task model. |
| Observability | 2/10 | 7/10 | Structured JSON logs with run-id correlation; no centralized log shipping (e.g. to Log Analytics/Databricks system tables) configured yet. |
| Testing | 0/10 | 6/10 | Core seams covered; extraction/chunking/graph-loading business logic itself remains untested (explicit scope decision, not an oversight). |
| Configuration-driven design | 6/10 | 8/10 | Dead config removed; secrets/auth/observability sections added; ontology schema path and log dir now config-driven. |

Overall: **48 → 80**. The remaining 20 points are concentrated in gaps that
require a live Azure/Databricks environment or a product decision this
review cannot make unilaterally - see below.

## Remaining Gaps Before Enterprise Deployment

1. **No live validation against real Azure/Databricks infrastructure.**
   `AzureKeyVaultSecretsProvider`, `DatabricksEmbeddingProvider`,
   `UnityCatalogProvider`, and `DeltaSqlTableStore` are real, reviewed code -
   none have been executed against an actual Key Vault, Unity Catalog
   Warehouse, or Model Serving endpoint in this environment. Required before
   go-live: a Databricks Workflow run against a real SQL Warehouse, and a
   Key Vault + Managed Identity smoke test in a deployed Azure environment.
2. **`AzureADAuthProvider` is a stub, and no UI action is role-gated.**
   It raises `NotImplementedError` pending a decision on how identity reaches
   the app (Databricks Apps header injection vs. an App Service
   authentication proxy vs. MSAL). Once wired, the Streamlit pages
   themselves still need per-action role checks (e.g. only `approver` role
   can approve) - `AuthProvider` supplies the identity/roles, but nothing yet
   consumes `roles` to gate a button.
3. **`NEO4J_PASSWORD` rotation.** The value previously committed to a tracked
   file must be rotated on the live Neo4j instance - an action against
   external infrastructure this review cannot perform.
4. **No pinned dependency lockfile.** `requirements.txt`/
   `requirements-databricks.txt`/`requirements-azure.txt` use `>=` version
   floors; no `pip-compile`/`uv.lock` exists to pin exact versions for
   reproducible production builds (no such tool available in this
   environment to generate one).
5. **No load/volume testing.** The O(N) → O(1) repository batching fix and
   restartable-stage fix are architecturally correct but unverified at the
   document volume an enterprise deployment would actually see.
6. **Centralized log shipping not configured.** Structured JSON logs are
   correlated by `run_id` and written to `observability.log_dir`, but nothing
   yet ships them to Azure Log Analytics, a Databricks system table, or
   another queryable sink - required for real production observability
   beyond reading local/Volume-mounted log files.
7. **Extraction/chunking/graph-loading business logic remains untested.**
   Scoped out of this pass by explicit decision (test the architectural
   seams, not exhaustively the business logic) - a future pass should add
   coverage for `docling_parser`, `semantic_chunker`, `entity_extractor`,
   `relationship_extractor`, and `graph_builder` directly.
