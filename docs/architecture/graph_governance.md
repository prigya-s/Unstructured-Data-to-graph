# Graph Governance: Silver/Gold Layers

## Summary

The pipeline's flow from extraction to a published graph is split into two
explicit, disjoint layers so business users always know whether they're
looking at the extraction engine's current best guess or at what's actually
approved and (about to be) live in Neo4j:

```
Entity Extraction -> Candidate Graph (Silver) -> Approval ->
Approved Ontology (Gold) -> Production Graph (Gold) -> Neo4j / future Cosmos DB
```

This is an additive extension of the existing six-provider architecture
(`DocumentSource`, `StorageProvider`, `ApprovalProvider`, `OntologyProvider`,
`GraphProvider`, plus the prior `SecretsProvider`/`AuthProvider` additions).
No existing abstraction was changed or replaced - one new storage method
pair, one new pure-function module pair, and one new pipeline stage.

## Artifact map

| Layer | Artifact | Built by | Stored via | Gated on approval? |
|---|---|---|---|---|
| Silver | Candidate entities/relationships | `ApprovalStage` / `candidate_builder` | `ApprovalProvider` (`lakehouse/gold/review/`) | No - this is the review queue itself |
| Silver | **Candidate Graph** | `review.candidate_graph.build_candidate_graph()` | `StorageProvider.write_candidate_graph()` (`lakehouse/silver/candidate_graph/candidate_graph.json`) | No |
| Gold | Approved entities/relationships | `OntologyStage` | `StorageProvider.write_approved_entities()`/`write_approved_relationships()` | Yes |
| Gold | Approved Ontology | `OntologyStage` / `ontology_generator` | `StorageProvider.write_ontology()` (`lakehouse/gold/ontology/ontology.json`) | Yes |
| Gold | **Production Graph** | `GraphStage` / `graph_builder` | `StorageProvider.write_graph_export()` (`lakehouse/gold/graph_exports/graph_export.json`) | Yes |
| Gold | Neo4j / future Cosmos DB | `GraphProvider.publish()` | External graph database | Yes - Production Graph only |

Both the Candidate Graph and the Production Graph are produced by
`graph_builder.build_graph()` unmodified - the only difference is which
entities/relationships are fed in:

- **Candidate Graph**: every candidate entity/relationship that hasn't been
  rejected (`NEW`, `PENDING_REVIEW`, `APPROVED`), with `MERGED` entities
  resolved to their canonical survivor.
- **Production Graph**: `APPROVED` entities/relationships only (via
  `ontology_generator.load_approved_for_graph()`), same merge resolution.

The merge-resolution logic (`build_merge_map`/`resolve_entity_id`) is shared
by both paths via `src/review/merge_resolution.py`, so the two graphs always
resolve `MERGED` entities identically.

## Gating invariant

**Candidate Graph must never be treated as production knowledge.**
Structurally enforced, not just documented: `build_candidate_graph()` writes
only through `StorageProvider.write_candidate_graph()` and holds no
reference to any `GraphProvider`. The only code path that ever calls
`GraphProvider.publish()` is `GraphStage`, which is fed exclusively by
`ontology_generator.load_approved_for_graph()` (approved-only). There is no
shared function, no shared object, and no configuration flag connecting the
two - a bug in the Candidate Graph path cannot leak into Neo4j/Cosmos
because there is nothing to route through.

## Live-ness ("approving an entity must automatically update...")

The Streamlit **Candidate Graph**, **Graph Impact Analysis**, and **Graph
Difference View** pages do not read a persisted snapshot on load - each
calls `build_candidate_graph(repo)` / `compute_graph_diff(repo, storage)`
directly, exactly like the existing **Ontology Preview** page already
recomputes from the repository on every page load. Streamlit reruns
top-to-bottom on every interaction, so an approval on **Entity Review**
is reflected the next time any of these pages render, with no event bus or
cache-invalidation logic required. The persisted
`lakehouse/silver/candidate_graph/candidate_graph.json` snapshot (written by
`CandidateGraphStage` on every `ingest`) exists for auditability and a future
Delta/Unity Catalog migration, not as the UI's source of truth.

## Graph Change Analysis (diff algorithm)

`review.graph_diff.compute_graph_diff(repository, storage)` returns a
`GraphDiff`:

- **Baseline** = `storage.read_graph_export()` - the last published Gold
  Production Graph (empty if never published).
- **Proposed** = candidates with status in `{APPROVED, PENDING_REVIEW, NEW}`
  (excludes `REJECTED`), `MERGED` entities resolved via the shared
  `merge_resolution` helpers.
- `entities_added` = ids in Proposed not in Baseline.
- `entities_removed` = ids in Baseline not in Proposed, excluding ids already
  accounted for in `entities_merged` (avoids double-counting an entity as
  both "removed" and "merged").
- `entities_modified` = ids in both where name/type differs.
- `entities_merged` = candidates with `status == MERGED` whose `merged_into`
  resolves to an approved survivor and which were present in the Baseline
  (i.e. newly merged since the last publish, not already-reflected merges).
- Relationships are diffed the same way, keyed by
  `(source, relationship, target)` after merge resolution, with
  self-relationships and dangling endpoints dropped.

One `GraphDiff` instance backs both the **Graph Impact Analysis** page
(summary `st.metric` counts and net deltas) and the **Graph Difference
View** page (the same object's full added/removed/modified/merged lists) -
no duplicated diff logic between the two screens.

## UI language

Consistent with the existing `app/common.py` convention, none of the new
screens use the words "Node", "Edge", "Cypher", or "Ontology Class" - graphs
are rendered as entity/relationship tables and metrics (`st.dataframe`/
`st.metric`), matching the pre-existing **Ontology Preview** page's style.
No graph-visualization dependency was added.
