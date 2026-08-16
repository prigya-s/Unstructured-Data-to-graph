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
| Silver | **Candidate Graph** (JSON) | `CandidateGraphStage` / `review.candidate_graph.build_candidate_graph()` | `StorageProvider.write_candidate_graph()` (`lakehouse/silver/candidate_graph/candidate_graph.json`) | No |
| Silver | **Candidate Graph** (Neo4j/Aura/Cosmos) | `CandidateGraphStage` / `GraphProvider.build_candidate_graph()` | `:CandidateEntity`/`:CANDIDATE_RELATIONSHIP`-labeled nodes/relationships in the same graph database as the Production Graph | No |
| Gold | Approved entities/relationships | `OntologyStage` | `StorageProvider.write_approved_entities()`/`write_approved_relationships()` | Yes |
| Gold | Approved Ontology | `OntologyStage` / `ontology_generator` | `StorageProvider.write_ontology()` (`lakehouse/gold/ontology/ontology.json`) | Yes |
| Gold | **Production Graph** (JSON) | `GraphStage` / `graph_builder` | `StorageProvider.write_graph_export()` (`lakehouse/gold/graph_exports/graph_export.json`) | Yes |
| Gold | **Production Graph** (Neo4j/Aura/Cosmos) | `GraphStage` / `GraphProvider.build_production_graph()` | Unlabeled `:Entity`/relationship nodes in Neo4j / Aura / Cosmos | Yes |
| N/A | Structural relationships (`CHILD_OF_PAGE`, `LEADS_TO`) | `graph_builder`'s page-hierarchy/page-link extraction, loaded by both `CandidateGraphStage` and `GraphStage` | Same graph database, Document-to-Document only | Never - always loaded regardless of entity/relationship approval state; not subject to `ALLOWED_RELATIONSHIP_TYPES` gating |

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

**Candidate Graph must never be treated as production knowledge, and must
never be returned as an answer.** `CandidateGraphStage` now loads the
Candidate Graph through `GraphProvider.build_candidate_graph()` in addition
to the JSON snapshot, so - unlike in an earlier version of this
document - the Candidate Graph *does* reach the same Neo4j/Aura/Cosmos
instance as the Production Graph. The invariant is enforced a different
way: by **label**, not by absence of a connection.

- `CandidateGraphStage` writes Candidate entities/relationships under
  `:CandidateEntity`/`:CANDIDATE_RELATIONSHIP` labels via
  `GraphProvider.build_candidate_graph()`.
- `GraphStage` writes Production (Gold) entities/relationships as unlabeled
  `:Entity`/typed-relationship nodes via
  `GraphProvider.build_production_graph()`, fed exclusively by
  `ontology_generator.load_approved_for_graph()` (approved-only).
- Every retrieval-facing query - `GraphProvider.search_chunks()`,
  `get_mentioned_entities()`, `get_neighbors()`, `get_linked_documents()`,
  and the Cypher the **Production Graph** Streamlit page runs - matches
  only the unlabeled Gold nodes/relationships. None of them match
  `:CandidateEntity`/`:CANDIDATE_RELATIONSHIP`.

So a bug that causes the Candidate Graph to be written incorrectly cannot,
by itself, corrupt an answer or the Production Graph page - the write paths
are still fully separate (`build_candidate_graph()` vs.
`build_production_graph()`, fed by disjoint entity sets) - but the
guarantee now rests on every read path consistently excluding the
Candidate labels, not on the Candidate Graph being unable to reach the
graph database at all. See [dependency_diagram.md](dependency_diagram.md)
for the `CandidateGraphStage`/`GraphStage` call graph.

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
