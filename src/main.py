"""
CLI entry point for the local Knowledge Graph pipeline.

Thin orchestration only: load config.yaml -> AppConfig, build the six
providers via src/providers/__init__.py factories, build a PipelineRunner
over the ten stages, and dispatch to the same CLI surface as before this
refactor. No function here computes a Path from a project root except
through AppConfig/StorageProvider - see
src/providers/local_storage_provider.py for the one place bronze/silver/gold
paths actually get built.

Usage:
    python src/main.py ingest ./docs
    python src/main.py candidate-graph
    python src/main.py publish-ontology
    python src/main.py publish-graph
    python src/main.py chat
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
import uuid
from pathlib import Path

import yaml
from dotenv import load_dotenv

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent

sys.path.insert(0, str(SRC_DIR))

import providers  # noqa: E402
from config import load_config  # noqa: E402
from config.app_config import AppConfig  # noqa: E402
from graph import graph_builder  # noqa: E402
from graph.startup import initialize_graph  # noqa: E402
from observability.logging_setup import setup_logging  # noqa: E402
from pipeline.context import PipelineContext  # noqa: E402
from pipeline.runner import PipelineRunner  # noqa: E402
from pipeline.stages.approval_stage import ApprovalStage  # noqa: E402
from pipeline.stages.candidate_graph_stage import CandidateGraphStage  # noqa: E402
from pipeline.stages.chunking_stage import ChunkingStage  # noqa: E402
from pipeline.stages.embedding_stage import EmbeddingStage  # noqa: E402
from pipeline.stages.entity_extraction_stage import EntityExtractionStage  # noqa: E402
from pipeline.stages.extraction_stage import ExtractionStage  # noqa: E402
from pipeline.stages.graph_stage import GraphStage  # noqa: E402
from pipeline.stages.ingestion_stage import IngestionStage  # noqa: E402
from pipeline.stages.ontology_stage import OntologyStage  # noqa: E402
from pipeline.stages.relationship_extraction_stage import RelationshipExtractionStage  # noqa: E402

logger = logging.getLogger("kg_local")

# MYDET page titles end "... - Q<n>" (e.g. "MD1.50 - Q55"). Section/appendix
# pages legitimately don't match this - it's a data-quality signal to review,
# not a hard error.
_SOP_ID_SUFFIX_RE = re.compile(r"Q\d+$")


def load_ontology(config: AppConfig) -> dict:
    with open(config.ontology_schema_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_context(config: AppConfig, docs_dir: str | None = None) -> PipelineContext:
    if docs_dir:
        # CLI positional arg overrides config.yaml's document_source.local_folder.path
        # (only meaningful for the local_folder provider; ignored otherwise).
        config.document_source.options["local_folder"] = {
            **config.document_source.options.get("local_folder", {}),
            "path": docs_dir,
        }

    graph_provider = providers.get_graph_provider(config)
    initialize_graph(graph_provider)

    return PipelineContext(
        config=config,
        storage=providers.get_storage_provider(config),
        document_source=providers.get_document_source(config),
        embedding_provider=providers.get_embedding_provider(config),
        approval_provider=providers.get_approval_provider(config),
        ontology_provider=providers.get_ontology_provider(config),
        graph_provider=graph_provider,
        extraction_provider=providers.get_extraction_provider(config),
        ontology_schema=load_ontology(config),
    )


def build_runner() -> PipelineRunner:
    return PipelineRunner(
        [
            IngestionStage(),
            ExtractionStage(),
            ChunkingStage(),
            EmbeddingStage(),
            EntityExtractionStage(),
            RelationshipExtractionStage(),
            ApprovalStage(),
            CandidateGraphStage(),
            OntologyStage(),
            GraphStage(),
        ]
    )


def _read_previous_snapshot(storage) -> dict:
    """Reads whatever the last `ingest` run persisted, before this run's
    stages overwrite it - the baseline the diff report below compares
    against. Empty on a first-ever run (everything reports as new)."""
    documents = storage.read_documents()
    entities, _mentions = storage.read_entities()
    relationships = storage.read_relationships()
    return {
        "document_ids": {doc["document_id"] for doc in documents},
        "content_hash_by_document_id": {
            doc["document_id"]: doc.get("content_hash") for doc in documents
        },
        "entity_ids": {entity["id"] for entity in entities},
        "relationship_keys": {
            (rel["source"], rel["relationship"], rel["target"]) for rel in relationships
        },
    }


def _find_orphan_document_ids(documents: list[dict], structural_graph: dict) -> set:
    """Documents with no CHILD_OF_PAGE/LEADS_TO edge in either direction -
    disconnected from the page tree and the in-text decision links, so a
    reader has no way to reach (or leave) the page through this corpus."""
    connected: set = set()
    for edge in structural_graph["relationships"]["page_hierarchy"]:
        connected.add(edge["child_id"])
        connected.add(edge["parent_id"])
    for link in structural_graph["relationships"]["page_links"]:
        connected.add(link["source_id"])
        connected.add(link["target_id"])
    return {doc["document_id"] for doc in documents} - connected


def _log_ingestion_diff_report(previous: dict, ctx: PipelineContext) -> None:
    documents = ctx.markdown_documents
    structural_graph = graph_builder.build_graph(
        documents, ctx.chunks, ctx.entities, ctx.mentions, ctx.relationships
    )

    current_document_ids = {doc["document_id"] for doc in documents}
    added = current_document_ids - previous["document_ids"]
    removed = previous["document_ids"] - current_document_ids
    changed = {
        doc["document_id"]
        for doc in documents
        if doc["document_id"] in previous["content_hash_by_document_id"]
        and doc.get("content_hash") != previous["content_hash_by_document_id"][doc["document_id"]]
    }

    current_entity_ids = {entity["id"] for entity in ctx.entities}
    entities_gained = current_entity_ids - previous["entity_ids"]
    entities_lost = previous["entity_ids"] - current_entity_ids

    current_relationship_keys = {
        (rel["source"], rel["relationship"], rel["target"]) for rel in ctx.relationships
    }
    relationships_gained = current_relationship_keys - previous["relationship_keys"]
    relationships_lost = previous["relationship_keys"] - current_relationship_keys

    missing_sop_suffix = sorted(
        doc["document_name"]
        for doc in documents
        if not _SOP_ID_SUFFIX_RE.search(doc["document_name"].strip())
    )
    orphan_ids = _find_orphan_document_ids(documents, structural_graph)
    orphan_names = sorted(doc["document_name"] for doc in documents if doc["document_id"] in orphan_ids)

    logger.info(
        "Ingestion diff: pages +%d/-%d/~%d, entities +%d/-%d, relationships +%d/-%d, "
        "missing_sop_suffix=%d, orphan_documents=%d",
        len(added), len(removed), len(changed),
        len(entities_gained), len(entities_lost),
        len(relationships_gained), len(relationships_lost),
        len(missing_sop_suffix), len(orphan_names),
    )
    logger.info("Pages missing SOP-id suffix: %s", missing_sop_suffix)
    logger.info("Orphan pages: %s", orphan_names)

    def _print_list(label: str, names: list[str], limit: int = 20) -> None:
        print(f"  {label}: {len(names)}")
        for name in names[:limit]:
            print(f"    - {name}")
        if len(names) > limit:
            print(f"    ... and {len(names) - limit} more (see log file)")

    print("\n=== Ingestion Diff Report (vs. previous run) ===")
    print(f"Pages added:                 {len(added)}")
    print(f"Pages changed (content_hash): {len(changed)}")
    print(f"Pages removed:                {len(removed)}")
    print(f"Entities gained:              {len(entities_gained)}")
    print(f"Entities lost:                {len(entities_lost)}")
    print(f"Relationships gained:         {len(relationships_gained)}")
    print(f"Relationships lost:           {len(relationships_lost)}")
    print("\nData quality signals:")
    _print_list("Pages missing a SOP-id suffix (e.g. 'Q42')", missing_sop_suffix)
    _print_list("Orphan pages (no page-tree or in-text link in/out)", orphan_names)


def run_ingest(docs_dir: str, run_id: str) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    config = load_config()
    log_path = setup_logging(config, run_id)

    logger.info("=== Knowledge Graph ingestion started ===")
    logger.info("Docs directory: %s", docs_dir)

    ctx = build_context(config, docs_dir)
    previous_snapshot = _read_previous_snapshot(ctx.storage)
    ctx = build_runner().run_all(ctx, through="candidate_graph")

    if not ctx.documents:
        logger.warning("No documents were extracted from %s. Aborting.", docs_dir)
        print("No supported documents found in", docs_dir)
        return

    logger.info("Files processed: %d", len(ctx.documents))
    logger.info("Total chunks created: %d", len(ctx.chunks))
    logger.info("Entities extracted: %d (mentions: %d)", len(ctx.entities), len(ctx.mentions))
    logger.info("Relationships extracted: %d", len(ctx.relationships))
    logger.info(
        "Candidates saved: %d entities, %d relationships", ctx.entities_saved, ctx.relationships_saved
    )
    if ctx.candidate_graph:
        logger.info(
            "Candidate Graph (silver) built: %d entities, %d relationships",
            ctx.candidate_graph["stats"]["entities"],
            ctx.candidate_graph["stats"]["entity_relationships"],
        )
    logger.info("=== Knowledge Graph ingestion completed ===")

    review_dir = ctx.config.storage_root / "gold" / "review"
    print("\n=== Ingestion Summary ===")
    print(f"Files processed:                 {len(ctx.documents)}")
    print(f"Chunks created:                  {len(ctx.chunks)}")
    print(f"Entities extracted (raw):        {len(ctx.entities)}")
    print(f"Relationships extracted (raw):   {len(ctx.relationships)}")
    print(f"New candidate entities saved:    {ctx.entities_saved}")
    print(f"New candidate relationships saved: {ctx.relationships_saved}")
    if ctx.candidate_graph:
        print(
            f"Candidate Graph (silver) built:  {ctx.candidate_graph['stats']['entities']} entities, "
            f"{ctx.candidate_graph['stats']['entity_relationships']} relationships"
        )
    print(f"\nCandidates are ready for business review at: {review_dir}")
    print(f"  uvicorn api.main:app --port 8001  (then open the React UI, npm run dev in web/)")
    print(f"\nAfter entities are approved:")
    print(f"  python src/main.py publish-ontology")
    print(f"  python src/main.py publish-graph")

    _log_ingestion_diff_report(previous_snapshot, ctx)

    print(f"\nLog file: {log_path}")


def run_publish_ontology(run_id: str) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    config = load_config()
    log_path = setup_logging(config, run_id)

    ctx = build_context(config)
    try:
        ctx = build_runner().run_stage("ontology", ctx)
    except ValueError as exc:
        print(f"{exc} Review candidates in the React app: uvicorn api.main:app --port 8001")
        return

    ontology = ctx.ontology_result
    logger.info(
        "Approved ontology generated: %d entities, %d relationships",
        ontology["stats"]["total_entities"],
        ontology["stats"]["total_relationships"],
    )
    print("\n=== Ontology Generated ===")
    print(f"Approved entities:       {ontology['stats']['total_entities']}")
    print(f"Approved relationships:  {ontology['stats']['total_relationships']}")
    print(f"Written to: {ctx.config.storage_root / 'gold' / 'ontology' / 'ontology.json'}")
    print(f"Log file: {log_path}")


def run_candidate_graph(run_id: str) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    config = load_config()
    log_path = setup_logging(config, run_id)

    ctx = build_context(config)
    ctx = build_runner().run_stage("candidate_graph", ctx)

    stats = ctx.candidate_graph["stats"]
    logger.info(
        "Candidate Graph (silver) regenerated: %d entities, %d relationships",
        stats["entities"],
        stats["entity_relationships"],
    )
    print("\n=== Candidate Graph (Silver) Regenerated ===")
    print(f"Candidate entities:       {stats['entities']}")
    print(f"Candidate relationships:  {stats['entity_relationships']}")
    print(f"Written to: {ctx.config.storage_root / 'silver' / 'candidate_graph' / 'candidate_graph.json'}")
    print(f"Log file: {log_path}")


def run_publish_graph(run_id: str) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    config = load_config()
    log_path = setup_logging(config, run_id)

    ctx = build_context(config)
    try:
        ctx = build_runner().run_stage("graph", ctx)
    except ValueError as exc:
        print(f"{exc} Review candidates in the React app: uvicorn api.main:app --port 8001")
        return

    stats = ctx.publish_stats
    logger.info(
        "Approved graph published: %d nodes, %d relationships",
        stats["nodes_loaded"],
        stats["relationships_loaded"],
    )
    print("\n=== Graph Published to Neo4j ===")
    print(f"Nodes loaded:            {stats['nodes_loaded']}")
    print(f"  - Documents:           {stats['documents_loaded']}")
    print(f"  - Chunks:              {stats['chunks_loaded']}")
    print(f"  - Entities:            {stats['entities_loaded']}")
    print(f"Relationships loaded:    {stats['relationships_loaded']}")
    print(f"Log file: {log_path}")


def run_chat(run_id: str) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    config = load_config()
    log_path = setup_logging(config, run_id)

    from agents.graphrag_agent import build_agent

    embedding_provider = providers.get_embedding_provider(config)
    graph_provider = providers.get_graph_provider(config)
    initialize_graph(graph_provider)
    llm_provider = providers.get_llm_provider(config)
    agent = build_agent(llm_provider, embedding_provider, graph_provider, config)

    print("=== Ask the Knowledge Graph ===")
    print("Answers are grounded only in the approved Production Graph.")
    print("Type 'exit' to quit.\n")
    logger.info("Chat session started")

    async def _loop() -> None:
        thread = agent.get_new_thread()
        while True:
            try:
                query = input("You: ").strip()
            except EOFError:
                break
            if not query or query.lower() in {"exit", "quit"}:
                break

            try:
                print("\nAssistant: ", end="", flush=True)
                async for chunk in agent.run_stream(query, thread=thread):
                    print(chunk, end="", flush=True)
                print("\n")
            except asyncio.TimeoutError:
                print("\nThat took too long to answer - please try again.\n")
                continue
            except ValueError as exc:
                print(f"\n{exc}\n")
                continue
            except Exception:  # noqa: BLE001 - keep the REPL alive on provider/LLM errors
                logger.exception("Chat turn failed")
                print("\nSomething went wrong answering that - check the log file.\n")
                continue

            result = agent.last_result
            if result.citations:
                print("Sources:")
                for name in dict.fromkeys(citation["document_name"] for citation in result.citations):
                    print(f"  - {name}")
                for path in result.graph_paths:
                    print(f"  - graph path: {path}")
                print()

    asyncio.run(_loop())
    print(f"Log file: {log_path}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description="Local Knowledge Graph pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser(
        "ingest", help="Extract documents into reviewable candidate entities"
    )
    ingest_parser.add_argument("docs_dir", help="Directory containing source documents")

    subparsers.add_parser(
        "candidate-graph", help="Regenerate the silver-layer Candidate Graph from current candidates"
    )
    subparsers.add_parser(
        "publish-ontology", help="Generate the approved ontology JSON from approved candidates"
    )
    subparsers.add_parser(
        "publish-graph", help="Load the approved ontology into Neo4j"
    )
    subparsers.add_parser(
        "chat", help="Ask the Knowledge Graph a question (terminal REPL, Gold Graph only)"
    )

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    run_id = str(uuid.uuid4())

    if args.command == "ingest":
        run_ingest(args.docs_dir, run_id)
    elif args.command == "candidate-graph":
        run_candidate_graph(run_id)
    elif args.command == "publish-ontology":
        run_publish_ontology(run_id)
    elif args.command == "publish-graph":
        run_publish_graph(run_id)
    elif args.command == "chat":
        run_chat(run_id)


if __name__ == "__main__":
    main()
