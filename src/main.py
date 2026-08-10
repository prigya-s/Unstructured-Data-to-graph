"""
CLI entry point for the local Knowledge Graph pipeline.

Thin orchestration only: load config.yaml -> AppConfig, build the six
providers via src/providers/__init__.py factories, build a PipelineRunner
over the nine stages, and dispatch to the same CLI surface as before this
refactor. No function here computes a Path from a project root except
through AppConfig/StorageProvider - see
src/providers/local_storage_provider.py for the one place bronze/silver/gold
paths actually get built.

Usage:
    python src/main.py ingest ./docs
    python src/main.py publish-ontology
    python src/main.py publish-graph
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
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
from pipeline.context import PipelineContext  # noqa: E402
from pipeline.runner import PipelineRunner  # noqa: E402
from pipeline.stages.approval_stage import ApprovalStage  # noqa: E402
from pipeline.stages.chunking_stage import ChunkingStage  # noqa: E402
from pipeline.stages.embedding_stage import EmbeddingStage  # noqa: E402
from pipeline.stages.entity_extraction_stage import EntityExtractionStage  # noqa: E402
from pipeline.stages.extraction_stage import ExtractionStage  # noqa: E402
from pipeline.stages.graph_stage import GraphStage  # noqa: E402
from pipeline.stages.ingestion_stage import IngestionStage  # noqa: E402
from pipeline.stages.ontology_stage import OntologyStage  # noqa: E402
from pipeline.stages.relationship_extraction_stage import RelationshipExtractionStage  # noqa: E402

logger = logging.getLogger("kg_local")


class _RunIdFilter(logging.Filter):
    """Stamps every log record with the run_id of the CLI invocation that
    produced it, so a Workflow task's JSON log lines can be correlated back
    to a single run the same way this CLI's file logs can."""

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = self.run_id
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "run_id": getattr(record, "run_id", None),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(config: AppConfig, run_id: str) -> Path:
    log_dir = config.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"ingest_{time.strftime('%Y%m%d_%H%M%S')}.log"

    run_id_filter = _RunIdFilter(run_id)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(_JsonFormatter())
    file_handler.addFilter(run_id_filter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    console_handler.addFilter(run_id_filter)

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler], force=True)
    return log_path


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
    ctx = build_runner().run_all(ctx, through="approval")

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
    logger.info("=== Knowledge Graph ingestion completed ===")

    review_dir = ctx.config.storage_root / "gold" / "review"
    print("\n=== Ingestion Summary ===")
    print(f"Files processed:                 {len(ctx.documents)}")
    print(f"Chunks created:                  {len(ctx.chunks)}")
    print(f"Entities extracted (raw):        {len(ctx.entities)}")
    print(f"Relationships extracted (raw):   {len(ctx.relationships)}")
    print(f"New candidate concepts saved:    {ctx.entities_saved}")
    print(f"New candidate relationships saved: {ctx.relationships_saved}")
    print(f"\nCandidates are ready for business review at: {review_dir}")
    print(f"  streamlit run app/streamlit_app.py")
    print(f"\nAfter concepts are approved:")
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
        "Approved ontology generated: %d concepts, %d relationships",
        ontology["stats"]["total_entities"],
        ontology["stats"]["total_relationships"],
    )
    print("\n=== Ontology Generated ===")
    print(f"Approved concepts:       {ontology['stats']['total_entities']}")
    print(f"Approved relationships:  {ontology['stats']['total_relationships']}")
    print(f"Written to: {ctx.config.storage_root / 'gold' / 'ontology' / 'ontology.json'}")
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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description="Local Knowledge Graph pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser(
        "ingest", help="Extract documents into reviewable candidate concepts"
    )
    ingest_parser.add_argument("docs_dir", help="Directory containing source documents")

    subparsers.add_parser(
        "publish-ontology", help="Generate the approved ontology JSON from approved candidates"
    )
    subparsers.add_parser(
        "publish-graph", help="Load the approved ontology into Neo4j"
    )

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    run_id = str(uuid.uuid4())

    if args.command == "ingest":
        run_ingest(args.docs_dir, run_id)
    elif args.command == "publish-ontology":
        run_publish_ontology(run_id)
    elif args.command == "publish-graph":
        run_publish_graph(run_id)


if __name__ == "__main__":
    main()
