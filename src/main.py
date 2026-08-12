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

    return PipelineContext(
        config=config,
        storage=providers.get_storage_provider(config),
        document_source=providers.get_document_source(config),
        embedding_provider=providers.get_embedding_provider(config),
        approval_provider=providers.get_approval_provider(config),
        ontology_provider=providers.get_ontology_provider(config),
        graph_provider=providers.get_graph_provider(config),
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


def run_ingest(docs_dir: str, run_id: str) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    config = load_config()
    log_path = setup_logging(config, run_id)

    logger.info("=== Knowledge Graph ingestion started ===")
    logger.info("Docs directory: %s", docs_dir)

    ctx = build_context(config, docs_dir)
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
    print(f"  streamlit run app/streamlit_app.py")
    print(f"\nAfter entities are approved:")
    print(f"  python src/main.py publish-ontology")
    print(f"  python src/main.py publish-graph")
    print(f"\nLog file: {log_path}")


def run_publish_ontology(run_id: str) -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    config = load_config()
    log_path = setup_logging(config, run_id)

    ctx = build_context(config)
    try:
        ctx = build_runner().run_stage("ontology", ctx)
    except ValueError as exc:
        print(f"{exc} Open the Streamlit app to review candidates: streamlit run app/streamlit_app.py")
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
        print(f"{exc} Open the Streamlit app to review candidates: streamlit run app/streamlit_app.py")
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
                response = await agent.run(query, thread=thread)
            except asyncio.TimeoutError:
                print("\nAssistant: That took too long to answer - please try again.\n")
                continue
            except ValueError as exc:
                print(f"\nAssistant: {exc}\n")
                continue
            except Exception:  # noqa: BLE001 - keep the REPL alive on provider/LLM errors
                logger.exception("Chat turn failed")
                print("\nAssistant: Something went wrong answering that - check the log file.\n")
                continue
            print(f"\nAssistant: {response}\n")

            result = agent.last_result
            if result.citations:
                print("Sources:")
                for citation in result.citations:
                    print(f"  - chunk {citation['chunk_id']} (document {citation['document_id']})")
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
