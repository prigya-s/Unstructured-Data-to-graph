"""
Startup graph initialization: connect, then idempotently ensure constraints
and indexes exist. Called once from src/main.py's CLI entry and once per
process from app/common.py (guarded there the same way
configure_streamlit_logging guards itself, so Streamlit reruns don't repeat
it) - never inside a per-request/per-page code path.

Safe to call against any GraphProvider, including MockGraphProvider (whose
connect()/create_constraints()/create_indexes() are no-ops) and
CosmosGraphProvider (which isn't implemented yet and will raise
NotImplementedError, same as calling any other method on it).
"""

from __future__ import annotations

import logging

from providers.graph_provider import GraphProvider

logger = logging.getLogger("kg_local.graph.startup")


def initialize_graph(provider: GraphProvider) -> None:
    provider.connect()
    provider.create_constraints()
    provider.create_indexes()
    logger.info("graph_operation operation=initialize status=ready")
