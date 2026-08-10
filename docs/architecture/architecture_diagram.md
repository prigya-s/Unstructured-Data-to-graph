# Target Architecture

Each box below is annotated with whether its local implementation is
working today (●) or its Databricks/cloud implementation is a documented
stub (○). Switching from ● to ○ for a given seam is a `config.yaml` change
plus implementing that one stub class - no other box changes.

```mermaid
flowchart TB
    subgraph Sources["Document Sources"]
        LF["● Local Folder\n(LocalFolderSource)"]
        CF["○ Confluence\n(ConfluenceSource - stub)"]
        SP["○ SharePoint\n(SharePointSource - stub)"]
    end

    subgraph Ingest["Ingestion / Extraction"]
        ING["IngestionStage"]
        EXT["ExtractionStage\n-> docling_parser (unchanged)"]
    end

    subgraph Bronze["Bronze"]
        BRZ["● Local JSON\n○ Unity Catalog / Volumes\n(StorageProvider)"]
    end

    subgraph Silver["Silver"]
        CHK["ChunkingStage\n-> semantic_chunker (unchanged)"]
        EMB["EmbeddingStage\n● local_noop (pass-through)\n○ databricks (stub)"]
        SLV["● Local JSON\n○ Delta Table\n(StorageProvider)"]
    end

    subgraph GoldExtract["Gold: Extraction"]
        EE["EntityExtractionStage\n-> entity_extractor (unchanged)"]
        RE["RelationshipExtractionStage\n-> relationship_extractor (unchanged)"]
    end

    subgraph Review["Business Review & Approval"]
        APP["ApprovalStage\n-> candidate_builder (unchanged)"]
        UI["● Streamlit\n(local_approval_ui)\n○ OntoBricks (FutureOntoBricksRepository - stub)"]
    end

    subgraph GoldApproved["Gold: Approved"]
        ONT["OntologyStage\n-> ontology_generator/publisher (unchanged)"]
        GR["GraphStage\n-> graph_builder (unchanged)"]
    end

    subgraph GraphDB["Graph Database"]
        NEO["● Neo4j\n(Neo4jGraphProvider -> Neo4jLoader, unchanged)"]
        COS["○ Cosmos DB\n(CosmosGraphProvider - stub)"]
    end

    LF --> ING
    CF --> ING
    SP --> ING
    ING --> EXT --> BRZ
    BRZ --> CHK --> EMB --> SLV
    SLV --> EE --> RE
    RE --> APP --> UI
    UI --> ONT
    UI --> GR
    ONT --> GoldApproved
    GR --> NEO
    GR --> COS
```

## Reading the diagram

- **Solid business-logic boxes** (`docling_parser`, `semantic_chunker`,
  `entity_extractor`, `relationship_extractor`, `candidate_builder`,
  `ontology_generator`/`publisher`, `graph_builder`, `neo4j_loader`) appear
  unchanged inside their stage - they have no inbound edge from `config.yaml`
  or `os.environ`. See [dependency_diagram.md](dependency_diagram.md) for
  the explicit proof of that.
- **Every other box** is a provider interface with exactly one local (●)
  implementation and one or more Databricks/cloud (○) stubs, selected by
  `config.yaml`'s `provider:` fields.
