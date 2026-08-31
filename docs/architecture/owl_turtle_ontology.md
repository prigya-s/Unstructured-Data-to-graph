# OWL/Turtle Ontology Layer

## Summary

`src/ontology/ontology.yaml` stays the single source of truth for the
rule-based extractor's keyword matching - nothing about that changes. This
layer adds a second, generated representation of the same vocabulary as
OWL/Turtle, so that:

- new domains can declare `rdfs:subClassOf` a shared core class in their own
  namespaced `.ttl` file, without editing the shared YAML file every other
  domain's rules also depend on;
- cross-entity equivalence (`MERGED` entities) is exported as a real
  `owl:sameAs` triple instead of only living as an app-specific
  `merged_into` pointer;
- the Ollama extraction fallback can be handed a class hierarchy - core
  types plus any domain subclasses - as its allowed-entity-type vocabulary,
  instead of only the flat `ontology.yaml` dict.

This is additive and opt-in. The default `ontology.provider: local` is
unchanged; nothing below runs unless `local_turtle` is selected in
`config.yaml`.

## Namespace scheme

All namespaces live under one base IRI, `https://kg.local/ontology/`, and
are defined once in `src/ontology/rdf/namespaces.py` so the Turtle export
and (in a later phase) Neo4j node `uri` properties never drift apart:

| Namespace | IRI | Used for |
|---|---|---|
| `core:` | `.../core#` | The 17 entity types + 11 relationship types generated from `ontology.yaml` |
| `kg:` (entity instances) | `.../entity/` | Approved entities - IRI local part is the existing `.id` |
| `document:` / `chunk:` | `.../document/`, `.../chunk/` | Reserved for a future RDF-native graph export |
| one per domain module, e.g. `coa:` | `.../domain/change_of_address#` | Hand-authored domain-specific subclasses |

`domain_namespace(stem)` builds the per-domain namespace from a module's
file stem (e.g. `"change_of_address"` -> `coa:`).

## `core.ttl`: generated from `ontology.yaml`

`src/ontology/rdf/build_core_ontology.py` reads `ontology.yaml` and writes
`src/ontology/rdf/core.ttl`:

- every `entity_types` entry becomes an `owl:Class` with an `rdfs:label`
  and one `skos:altLabel` per keyword;
- every `relationship_types` entry becomes an `owl:ObjectProperty`,
  equivalently.

It's both a callable (`build_core_ontology(ontology_yaml_path=...)`) and a
script:

```bash
python src/ontology/rdf/build_core_ontology.py
```

`core.ttl` is a committed, generated artifact - regenerate and recommit it
whenever `ontology.yaml`'s entity/relationship types change. There's no
build-time check that they're in sync, so `tests/test_rdf_turtle_roundtrip.py`
asserts the two currently agree, and will fail (not silently drift) the day
someone edits one without the other.

## Domain modules: new domain, no shared-file edits

`src/ontology/rdf/domains/change_of_address.ttl` is the worked example. Each
class subclasses a `core:` class and is hand-authored directly in Turtle -
no generator, no code:

```turtle
coa:ChangeOfAddressProcess a owl:Class ; rdfs:subClassOf core:Process  ; rdfs:label "ChangeOfAddressProcess" .
coa:SAMMPlatform          a owl:Class ; rdfs:subClassOf core:System   ; rdfs:label "SAMMPlatform" .
coa:IVRChannel            a owl:Class ; rdfs:subClassOf core:Channel  ; rdfs:label "IVRChannel" .
coa:IForm                 a owl:Class ; rdfs:subClassOf core:Application ; rdfs:label "IForm" .
coa:TMWExternalPartner    a owl:Class ; rdfs:subClassOf core:ExternalPartner ; rdfs:label "TMWExternalPartner" .
```

A new domain onboards by adding a new file here and one line to
`config.yaml`'s `ontology.turtle_modules` (see below) - it never touches
`ontology.yaml` or any other domain's file.

`src/ontology/rdf/hierarchy.py` provides the plain `rdflib`
`transitive_objects(..., RDFS.subClassOf)` traversal used to work with the
merged graph - no OWL reasoner is needed at this scale:

- `allowed_classes(graph)` - every class name (core + domain), for vocabulary/validation checks.
- `class_labels_and_keywords(graph)` - class name -> its `skos:altLabel` list, for prompt-building.
- `nearest_core_ancestor(graph, class_name)` - walks up `rdfs:subClassOf` to the nearest `core:` class, for rolling a domain subclass up to its shared category.

## The `local_turtle` ontology provider

`src/providers/turtle_ontology_provider.py` implements the existing
`OntologyProvider` interface as a superset of the default `local` provider:

- `generate()` calls the same `generate_approved_ontology()` the `local`
  provider uses (unchanged JSON artifact, unchanged approval gating), then
  additionally builds an RDF graph of the approved entities/relationships
  and serializes it to `lakehouse/gold/ontology/ontology.ttl`:
  - each approved entity -> `kg:<id> a core:<Category> ; rdfs:label "<name>"`;
  - each approved relationship -> a triple using the relationship type as predicate;
  - each `MERGED` entity -> `owl:sameAs` to its canonical survivor, reusing
    `review.merge_resolution.build_merge_map()` (the same validated merge
    logic the JSON path already relies on - a `MERGED` entity whose
    `merged_into` target isn't itself `APPROVED` is dropped with a warning,
    not exported as a dangling triple).
  - the returned dict gets an added `ttl_path` key; `run_publish_ontology`
    in `src/main.py` prints it when present.
- `load_for_graph()` is unchanged - delegates to the same
  `load_approved_for_graph()` the `local` provider uses. The Turtle export
  is a side artifact of publishing, not a new input to graph building.

Enable it in `config.yaml`:

```yaml
ontology:
  provider: local_turtle
  schema_path: ontology/ontology.yaml
  turtle_modules:
    - ontology/rdf/domains/change_of_address.ttl
```

`turtle_modules` is only read when `provider: local_turtle`; it's a list of
paths (relative to `src/`) to hand-authored domain `.ttl` files, merged with
`core.ttl` by `src/ontology/rdf/graph_loader.py`'s
`load_ontology_graph(config)`. An empty list is fine - `core.ttl` alone still
provides the full core vocabulary.

## Feeding the Ollama extraction fallback

`src/providers/ollama_extraction_provider.py` loads the RDF graph (if
configured) once in `__init__`, then `_extended_ontology()` unions
`allowed_classes(graph)` into `ontology.yaml`'s flat `entity_types` dict via
`setdefault` - existing YAML-defined types are never overwritten, only
extended with domain subclasses the LLM wouldn't otherwise know about. This
runs at the top of `extract_entities()` only; `extract_relationships()` and
the rule-based extractor are untouched, matching the scope of this layer -
vocabulary extension for the LLM fallback, not a change to relationship
extraction or the deterministic rule engine.

## What this does *not* do (yet)

- No SPARQL query engine and no separate triple store - this is a files-only
  layer read by `rdflib` in-process.
- No OWL reasoning beyond `rdfs:subClassOf` traversal.
- No change to retrieval Cypher or the Silver/review tier. The Gold-tier
  Neo4j graph itself is made RDF-native separately, via neosemantics (n10s)
  - see [neo4j_n10s_setup.md](neo4j_n10s_setup.md).

## Tests

- `tests/test_rdf_hierarchy.py` - pure in-memory graph tests for `hierarchy.py`.
- `tests/test_rdf_turtle_roundtrip.py` - against the real `ontology.yaml`: full
  entity/relationship type coverage, and a serialize -> re-parse round trip.
