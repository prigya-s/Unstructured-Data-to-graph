"""
LocalOntologyProvider: calls the existing, unmodified review.publisher /
review.ontology_generator functions. publish_ontology() wraps
generate_approved_ontology() with the "no approved concepts" guard, and
already accepts an optional output_path - we point its side-effect write at
a scratch file under the lakehouse root's gold/ontology directory (distinct
from the canonical ontology.json contract file, which OntologyStage writes
via StorageProvider.write_ontology()) rather than editing either function.
"""

from __future__ import annotations

from config.app_config import AppConfig
from review.ontology_generator import load_approved_for_graph
from review.publisher import publish_ontology

from .approval_provider import ApprovalProvider
from .ontology_provider import OntologyProvider


class LocalOntologyProvider(OntologyProvider):
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def generate(self, approval_provider: ApprovalProvider) -> dict:
        scratch_path = self.config.storage_root / "gold" / "ontology" / "_generated_ontology.json"
        return publish_ontology(approval_provider, output_path=scratch_path)

    def load_for_graph(
        self, approval_provider: ApprovalProvider, all_mentions: list[dict]
    ) -> tuple[list[dict], list[dict], list[dict]]:
        return load_approved_for_graph(approval_provider, all_mentions)
