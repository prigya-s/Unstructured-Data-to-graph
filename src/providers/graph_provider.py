"""
GraphProvider: the abstraction boundary for loading a graph_builder.build_graph()
export into a live graph database.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class GraphProvider(ABC):
    @abstractmethod
    def publish(self, graph: dict) -> dict:
        """graph: graph_builder.build_graph() output. Returns a stats dict
        of nodes/relationships loaded."""
