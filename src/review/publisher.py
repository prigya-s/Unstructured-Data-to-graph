"""
Publish stage: turns approved concepts into the ontology artifact.

Historically this module also published directly to Neo4j via a
publish_graph() function that constructed its own unconfigured
Neo4jLoader(). That function had zero callers - GraphStage
(src/pipeline/stages/graph_stage.py) is the only live path from approved
concepts to Neo4j, and it goes through GraphProvider/config routing instead
- so it was removed.
"""

from __future__ import annotations

from pathlib import Path

from .ontology_generator import generate_approved_ontology
from .repository import OntologyRepository


def publish_ontology(repository: OntologyRepository, output_path: Path | None = None) -> dict:
    approved_count = len(repository.get_approved_entities())
    if approved_count == 0:
        raise ValueError("No approved concepts found. Review and approve candidates first.")
    return generate_approved_ontology(repository, output_path=output_path)
