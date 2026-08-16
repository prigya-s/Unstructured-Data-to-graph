"""
Neo4jAuraGraphProvider: Neo4jGraphProvider tuned for Neo4j AuraDB.

The Neo4j driver is already URI-scheme agnostic - a neo4j+s:// URI (Aura's
required scheme, which also implies TLS) works through the base
Neo4jGraphProvider unchanged. The only Aura-specific concerns are:
- a longer default connection timeout (cloud round trips are slower and
  Aura instances can be paused/resuming on the free tier), and
- distinguishing "Aura" in connect logs, since operators reading logs need
  to know which deployment mode is active.

Selecting this provider (graph.provider: neo4j_aura) vs. the base
Neo4jGraphProvider (graph.provider: neo4j) is a config-only choice - both
remain fully supported side by side for local development.
"""

from __future__ import annotations

import logging

from .neo4j_graph_provider import Neo4jGraphProvider

logger = logging.getLogger("kg_local.neo4j_aura_graph_provider")

_AURA_DEFAULT_CONNECTION_TIMEOUT_SECONDS = 30.0


class Neo4jAuraGraphProvider(Neo4jGraphProvider):
    def _connection_timeout(self) -> float | None:
        return _AURA_DEFAULT_CONNECTION_TIMEOUT_SECONDS

    def connect(self) -> None:
        loader = self._get_loader()
        loader.connect_with_retry()
        logger.info("graph_operation operation=provider_connect target=aura uri=%s", self.uri)
