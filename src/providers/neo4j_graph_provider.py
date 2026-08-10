"""
Neo4jGraphProvider: wraps the existing, unmodified graph.neo4j_loader.Neo4jLoader.

Neo4jLoader itself keeps reading NEO4J_* from os.environ as a fallback -
that's unchanged, and is legitimate for direct no-args construction of that
class. This provider routes *which* secret names are read through
config.graph.options (graph.neo4j.uri_env/user_env/password_env/
database_env), and resolves those names via SecretsProvider - so a
Databricks/Azure deployment only changes secrets.provider in config.yaml
(env vars vs. Azure Key Vault), never this code.
"""

from __future__ import annotations

from config.app_config import AppConfig
from graph.neo4j_loader import Neo4jLoader

from .graph_provider import GraphProvider
from .secrets_provider import get_secrets_provider


class Neo4jGraphProvider(GraphProvider):
    def __init__(self, config: AppConfig) -> None:
        neo4j_options = config.graph.options.get("neo4j", {})
        secrets = get_secrets_provider(config)
        self.uri = secrets.get(neo4j_options.get("uri_env", "NEO4J_URI"))
        self.user = secrets.get(neo4j_options.get("user_env", "NEO4J_USER"))
        self.password = secrets.get(neo4j_options.get("password_env", "NEO4J_PASSWORD"))
        self.database = secrets.get(neo4j_options.get("database_env", "NEO4J_DATABASE"))

        missing = [
            label
            for label, value in (("uri", self.uri), ("user", self.user), ("password", self.password))
            if not value
        ]
        if missing:
            raise ValueError(
                f"Neo4j connection is missing required secret(s): {', '.join(missing)}. "
                "Check graph.neo4j.*_env in config.yaml and that secrets.provider can resolve them."
            )

    def publish(self, graph: dict) -> dict:
        with Neo4jLoader(
            uri=self.uri, user=self.user, password=self.password, database=self.database
        ) as loader:
            loader.verify_connectivity()
            return loader.load_graph(graph)
