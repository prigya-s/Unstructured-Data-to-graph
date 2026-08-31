# Neo4j RDF-Native Setup (neosemantics / n10s)

## Summary

The Gold-tier Neo4j graph (Document/Chunk/Entity nodes written by
`build_production_graph()`) is RDF-native: every such node carries a `uri`
property (using the same `https://kg.local/ontology/...` IRIs as
[owl_turtle_ontology.md](owl_turtle_ontology.md)'s Turtle export) and a
`:Resource` label, and the database is configured with the
[neosemantics](https://neo4j.com/labs/neosemantics/) (n10s) plugin so that
graph can be exported to (and imported from) RDF/Turtle via Cypher
procedures.

**This does not add SPARQL.** n10s gives RDF import/export only - retrieval
stays exactly as it is today: plain, `.id`-keyed Cypher in
`neo4j_loader.py`'s `search_chunks`/`get_mentioned_entities`/`get_neighbors`/
`get_linked_documents`. Nothing about the GraphRAG retrieval path changes.

**Scope**: RDF-native applies only to the Gold (published) tier. The
Silver/review tier (`:CandidateEntity`/`:CANDIDATE_RELATIONSHIP`) is
deliberately excluded - a candidate entity and its eventual approved Entity
can share the same `.id` mid-review-cycle, and giving both a
`:Resource{uri}` would collide under n10s's required uniqueness constraint.

## One-time manual install (Neo4j Desktop)

neosemantics is not in Desktop's curated plugin list (unlike APOC), so it
has to be installed by hand into the existing local `kg-dev` database - this
is **not** a separate database or a Docker/container step.

1. In Neo4j Desktop, find the `kg-dev` database card -> "..." menu ->
   **Open Folder** -> **Plugins**. Download the `neosemantics-<version>.jar`
   that matches the running Neo4j 5.x version from the
   [neosemantics releases page](https://github.com/neo4j-labs/neosemantics/releases)
   and copy it into that folder.
2. "Open Folder" -> **Configuration** -> open `neo4j.conf` and add:
   ```
   dbms.security.procedures.unrestricted=n10s.*
   ```
3. Restart the `kg-dev` database from Desktop.
4. In Neo4j Browser, confirm the procedures resolve:
   ```cypher
   SHOW PROCEDURES WHERE name STARTS WITH "n10s"
   ```
   If this returns rows, the plugin is live. **Verify the exact procedure
   names below against whatever this lists** - they can shift between
   neosemantics releases; don't assume the names in this doc are exact for
   your installed version.

Until this is done, `create_constraints()` (called at the top of every
`build_production_graph()`/`load_graph()` run) logs a warning and continues
- the pipeline degrades gracefully rather than failing startup for anyone
who hasn't done this yet. Only the RDF import/export procedures are
unavailable; `uri`/`:Resource` are plain node properties/labels and get set
regardless.

## What the code does once the plugin is present

`Neo4jLoader.create_constraints()` (`src/graph/neo4j_loader.py`):

- creates `CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS FOR (r:Resource) REQUIRE r.uri IS UNIQUE`
  (this constraint itself needs no plugin - it's a normal uniqueness
  constraint on a label/property);
- calls `_init_rdf_config()`, which (wrapped in a try/except that only logs
  a warning on failure):
  ```cypher
  CALL n10s.graphconfig.init({handleVocabUris: 'MAP'})
  CALL n10s.nsprefixes.add('core', 'https://kg.local/ontology/core#')
  CALL n10s.nsprefixes.add('kg', 'https://kg.local/ontology/entity/')
  ```

`load_documents`/`load_chunks`/`load_entities` additionally `SET` a `uri`
(`https://kg.local/ontology/document/<id>`, `.../chunk/<id>`,
`.../entity/<id>` respectively, via the same `DOCUMENT_NS`/`CHUNK_NS`/
`ENTITY_NS` constants `owl_turtle_ontology.md` describes) and the
`:Resource` label on every Gold-tier node.

## Backfill for already-ingested demo data

Not needed as a separate step: `build_production_graph()` calls
`load_graph()`, which rebuilds Document/Chunk/Entity nodes via idempotent
`MERGE` + a full property `SET` on every run - not an additive-only write.
Re-running `publish-graph` after upgrading is sufficient to backfill `uri`/
`:Resource` onto nodes from earlier runs; no one-off Cypher script is
required.

## Verification

1. `python src/main.py` (or any command that calls `create_constraints()`)
   and confirm no exception is raised either way (plugin present or not).
2. In Neo4j Browser: `SHOW CONSTRAINTS` and confirm `n10s_unique_uri` is
   listed.
3. Run `publish-graph`, then in Browser:
   ```cypher
   MATCH (e:Entity) RETURN e.id, e.uri, labels(e) LIMIT 5
   ```
   and confirm each row has a `uri` and `Resource` in its labels.
4. Confirm RDF export works, adjusting the procedure name/signature to
   whatever `SHOW PROCEDURES WHERE name STARTS WITH "n10s"` listed in step 4
   of the install section above:
   ```cypher
   CALL n10s.rdf.export.cypher("MATCH (n:Entity) RETURN n LIMIT 5", {})
   YIELD subject, predicate, object
   RETURN subject, predicate, object
   ```
   and confirm each **subject** is our own IRI, e.g.
   `https://kg.local/ontology/entity/entity_role_...` - this is what makes a
   node's identity match `ontology.ttl`'s `kg:` IRIs.

   **Caveat, confirmed against a real export**: predicates and `rdf:type`
   objects come back under n10s's own `baseSchemaNamespace`
   (`neo4j://graph.schema#...` by default), *not* the registered `core:`
   prefix - `n10s.nsprefixes.add` populates a lookup table n10s consults
   when *importing* RDF (to recognize `core:Foo` as a known vocabulary term),
   it does not redirect what namespace `n10s.rdf.export.cypher` mints for
   property/label names on the way out. Getting predicates to read
   `core:type` instead of `n4sch:type` would mean passing
   `baseSchemaNamespace: 'https://kg.local/ontology/core#'` into
   `n10s.graphconfig.init(...)` in `_init_rdf_config()` - which, like the
   rest of graph config, only takes effect on an empty graph, so doing this
   later means another wipe-and-reload of the Gold tier. Not done here since
   subject-IRI alignment (the actual cross-artifact identity story with
   `owl_turtle_ontology.md`) is unaffected either way.
5. **`n10s.graphconfig.init()` only succeeds on an empty graph** - confirmed
   against a real, previously-populated `kg-dev`:
   `GraphConfigException: The graph is non-empty. Config cannot be changed.`
   `n10s.nsprefixes.add` still works standalone even when `graphconfig.init`
   never ran, but export then falls back entirely to n10s's default
   `neo4j://graph.individuals#<internal-id>` subjects too - not just the
   predicate/type namespace above. If you're adding this to a `kg-dev` that
   already has Gold-tier data from before this feature, wipe it first
   (`MATCH (n) DETACH DELETE n`) and re-run `publish-graph` - `load_graph()`'s
   idempotent `MERGE`+`SET` means that single re-run fully repopulates
   Documents/Chunks/Entities with `uri`/`:Resource` intact.
6. Re-run the GraphRAG chat smoke test (or the 4 retrieval Cypher queries
   directly) against the same demo data and confirm no regression - this
   layer is additive to Gold-tier nodes only and the retrieval queries never
   reference `uri`/`:Resource`.
