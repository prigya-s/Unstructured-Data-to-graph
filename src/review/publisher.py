"""
Publish stage: turns approved concepts into the ontology artifact and,
separately, into a live Neo4j graph.

This is the only module in src/review that imports Neo4jLoader - the rest
of the review package has no knowledge of Neo4j. It reuses the existing,
unmodified graph_builder.build_graph() and Neo4jLoader.load_graph(); the
only thing that changes versus the old pipeline is that entities/mentions/
relationships are filtered down to approved concepts first (see
ontology_generator.load_approved_for_graph).

Known limitation: publishing is additive (Neo4jLoader MERGEs everything),
so a concept that was previously published and later rejected is not
automatically removed from Neo4j. Deleting graph data is a destructive,
shared-system operation and should require an explicit, separately
confirmed action rather than happening implicitly as a side effect of
rejecting a concept in the review UI - that pruning step is intentionally
left as a follow-up, not built here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from graph import graph_builder  # noqa: E402
from graph.neo4j_loader import Neo4jLoader  # noqa: E402

from .ontology_generator import generate_approved_ontology, load_approved_for_graph  # noqa: E402
from .repository import OntologyRepository  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CHUNKS_DIR = _PROJECT_ROOT / "output" / "chunks"
_DEFAULT_DOCUMENTS_PATH = _PROJECT_ROOT / "output" / "graph" / "documents.json"
_DEFAULT_MENTIONS_PATH = _PROJECT_ROOT / "output" / "graph" / "mentions.json"
_DEFAULT_GRAPH_OUTPUT_PATH = _PROJECT_ROOT / "output" / "graph" / "approved_graph.json"


def publish_ontology(repository: OntologyRepository, output_path: Path | None = None) -> dict:
    approved_count = len(repository.get_approved_entities())
    if approved_count == 0:
        raise ValueError("No approved concepts found. Review and approve candidates first.")
    return generate_approved_ontology(repository, output_path=output_path)


def publish_graph(
    repository: OntologyRepository,
    chunks_dir: Path | None = None,
    documents_path: Path | None = None,
    mentions_path: Path | None = None,
    graph_output_path: Path | None = None,
) -> dict:
    chunks_dir = chunks_dir or _DEFAULT_CHUNKS_DIR
    documents_path = documents_path or _DEFAULT_DOCUMENTS_PATH
    mentions_path = mentions_path or _DEFAULT_MENTIONS_PATH
    graph_output_path = graph_output_path or _DEFAULT_GRAPH_OUTPUT_PATH

    if not documents_path.exists() or not mentions_path.exists():
        raise FileNotFoundError(
            f"Missing {documents_path.name}/{mentions_path.name} under output/graph/. "
            "Run 'python src/main.py ingest ./docs' first."
        )

    documents = json.loads(documents_path.read_text(encoding="utf-8"))

    all_chunks: list[dict] = []
    for chunk_file in sorted(chunks_dir.glob("*.json")):
        all_chunks.extend(json.loads(chunk_file.read_text(encoding="utf-8")))

    all_mentions = json.loads(mentions_path.read_text(encoding="utf-8"))

    entities, mentions, relationships = load_approved_for_graph(repository, all_mentions)
    if not entities:
        raise ValueError("No approved concepts found. Review and approve candidates first.")

    graph = graph_builder.build_graph(documents, all_chunks, entities, mentions, relationships)

    graph_output_path.parent.mkdir(parents=True, exist_ok=True)
    graph_output_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")

    with Neo4jLoader() as loader:
        loader.verify_connectivity()
        stats = loader.load_graph(graph)

    return stats
