# Dependency Diagram: Stage → Provider → Business Logic

This diagram exists to make one property visually checkable: **business
logic has zero inbound edges from config or environment.** Every arrow
into a business-logic module comes from a Stage passing it plain dicts/
dataclasses; every arrow into `config.yaml`/`os.environ` terminates at a
provider factory or a provider constructor, never at a business-logic
module directly.

```mermaid
flowchart LR
    CFG["config.yaml / AppConfig"]
    ENV["os.environ (.env)"]

    subgraph Factories["src/providers/__init__.py factories"]
        F1["get_storage_provider"]
        F2["get_document_source"]
        F3["get_embedding_provider"]
        F4["get_approval_provider"]
        F5["get_ontology_provider"]
        F6["get_graph_provider"]
    end

    CFG --> F1 & F2 & F3 & F4 & F5 & F6

    subgraph Providers["Provider implementations"]
        P1["LocalStorageProvider / *stub*"]
        P2["LocalFolderSource / *stub*"]
        P3["LocalEmbeddingProvider / *stub*"]
        P4["LocalOntologyRepository / FutureOntoBricksRepository"]
        P5["LocalOntologyProvider"]
        P6["Neo4jGraphProvider / *stub*"]
    end

    F1 --> P1
    F2 --> P2
    F3 --> P3
    F4 --> P4
    F5 --> P5
    F6 --> P6
    ENV --> P6

    subgraph Stages["src/pipeline/stages/*.py"]
        S1["IngestionStage"]
        S2["ExtractionStage"]
        S3["ChunkingStage"]
        S4["EmbeddingStage"]
        S5["EntityExtractionStage"]
        S6["RelationshipExtractionStage"]
        S7["ApprovalStage"]
        S8["OntologyStage"]
        S9["GraphStage"]
    end

    P1 -.reads/writes via.-> S1 & S2 & S3 & S4 & S5 & S6 & S8 & S9
    P2 -.reads via.-> S1 & S2
    P3 -.calls.-> S4
    P4 -.reads/writes via.-> S7 & S8 & S9
    P5 -.calls.-> S8 & S9
    P6 -.calls.-> S9

    subgraph BusinessLogic["Business logic - UNCHANGED by this refactor"]
        B1["extract/docling_parser.py"]
        B2["chunking/semantic_chunker.py"]
        B3["extraction/entity_extractor.py"]
        B4["extraction/relationship_extractor.py"]
        B5["review/candidate_builder.py"]
        B6["review/ontology_generator.py + publisher.py"]
        B7["graph/graph_builder.py"]
        B8["graph/neo4j_loader.py"]
    end

    S2 -->|"convert_to_markdown(path)"| B1
    S3 -->|"chunk_markdown(markdown, doc_id)"| B2
    S5 -->|"extract_entities(chunks, ontology)"| B3
    S6 -->|"extract_relationships(chunks, entities, mentions, ontology)"| B4
    S7 -->|"build_candidates(entities, mentions, rels, chunks, repo)"| B5
    S8 -->|"publish_ontology(repo, output_path)"| B6
    S9 -->|"load_approved_for_graph(repo, mentions)"| B6
    S9 -->|"build_graph(docs, chunks, entities, mentions, rels)"| B7
    P6 -->|"Neo4jLoader(uri, user, password, database)"| B8
```

## What to check when reviewing this diagram

- No arrow goes from `CFG`/`ENV` directly into the `BusinessLogic` subgraph -
  every path into it passes through a Stage, which only ever hands the
  business-logic function plain data (dicts, lists, an `OntologyRepository`
  instance) - never a `Path`, an env var, or a config value.
- `Neo4jGraphProvider` is the one provider that reads `ENV` directly (it
  always did, via `Neo4jLoader`) - it now also reads `CFG` for *which* env
  var names to use, but the values themselves still flow through
  `os.environ`, same as before.
