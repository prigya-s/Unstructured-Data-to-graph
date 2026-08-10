"""
OntologyProvider: the abstraction boundary for turning approved candidates
into the business ontology artifact and the graph_builder-ready tuple.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .approval_provider import ApprovalProvider


class OntologyProvider(ABC):
    @abstractmethod
    def generate(self, approval_provider: ApprovalProvider) -> dict:
        """Returns an OntologyRecord-shaped dict of approved concepts/relationships."""

    @abstractmethod
    def load_for_graph(
        self, approval_provider: ApprovalProvider, all_mentions: list[dict]
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """Returns (entities, mentions, relationships) shaped for
        graph.graph_builder.build_graph - approved-only."""
