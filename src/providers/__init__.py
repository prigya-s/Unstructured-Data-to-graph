"""
Provider factories, keyed off AppConfig. Mirrors review/repository.py's
existing get_repository() pattern for every other seam in the pipeline:
each get_*() function reads one AppConfig section and returns the local
implementation today, raising NotImplementedError (or ValueError for an
unknown provider name) via a stub class for any provider value that isn't
implemented yet. Every stage/provider reads AppConfig values only - nothing
downstream of this module ever reads a raw environment variable or branches
on an execution mode.
"""

from __future__ import annotations

from config.app_config import AppConfig

from .approval_provider import ApprovalProvider, get_approval_provider
from .auth_provider import AuthProvider, get_auth_provider
from .document_source import DocumentSource
from .embedding_provider import EmbeddingProvider
from .graph_provider import GraphProvider
from .ontology_provider import OntologyProvider
from .secrets_provider import SecretsProvider, get_secrets_provider
from .storage_provider import StorageProvider


def get_storage_provider(config: AppConfig) -> StorageProvider:
    provider = config.storage.provider
    if provider == "local":
        from .local_storage_provider import LocalStorageProvider

        return LocalStorageProvider(config.storage_root)
    if provider == "databricks_volumes":
        from .databricks_volumes_provider import DatabricksVolumesProvider

        return DatabricksVolumesProvider(config)
    if provider == "unity_catalog":
        from .unity_catalog_provider import UnityCatalogProvider

        return UnityCatalogProvider(config)
    raise ValueError(f"Unknown storage.provider '{provider}'. Valid values: local, databricks_volumes, unity_catalog.")


def get_document_source(config: AppConfig) -> DocumentSource:
    provider = config.document_source.provider
    if provider == "local_folder":
        from .local_folder_source import LocalFolderSource

        path = config.document_source.options.get("local_folder", {}).get("path", "./docs")
        return LocalFolderSource(path)
    if provider == "confluence":
        from .confluence_source import ConfluenceSource

        return ConfluenceSource(config)
    if provider == "sharepoint":
        from .sharepoint_source import SharePointSource

        return SharePointSource(config)
    raise ValueError(f"Unknown document_source.provider '{provider}'. Valid values: local_folder, confluence, sharepoint.")


def get_embedding_provider(config: AppConfig) -> EmbeddingProvider:
    provider = config.embedding.provider
    if provider == "local_noop":
        from .local_embedding_provider import LocalEmbeddingProvider

        return LocalEmbeddingProvider()
    if provider == "databricks":
        from .databricks_embedding_provider import DatabricksEmbeddingProvider

        return DatabricksEmbeddingProvider(config)
    raise ValueError(f"Unknown embedding.provider '{provider}'. Valid values: local_noop, databricks.")


def get_ontology_provider(config: AppConfig) -> OntologyProvider:
    provider = config.ontology.provider
    if provider == "local":
        from .local_ontology_provider import LocalOntologyProvider

        return LocalOntologyProvider(config)
    raise ValueError(f"Unknown ontology.provider '{provider}'. Valid values: local.")


def get_graph_provider(config: AppConfig) -> GraphProvider:
    provider = config.graph.provider
    if provider == "neo4j":
        from .neo4j_graph_provider import Neo4jGraphProvider

        return Neo4jGraphProvider(config)
    if provider == "cosmos":
        from .cosmos_graph_provider import CosmosGraphProvider

        return CosmosGraphProvider(config)
    raise ValueError(f"Unknown graph.provider '{provider}'. Valid values: neo4j, cosmos.")


__all__ = [
    "StorageProvider",
    "DocumentSource",
    "EmbeddingProvider",
    "ApprovalProvider",
    "OntologyProvider",
    "GraphProvider",
    "SecretsProvider",
    "AuthProvider",
    "get_storage_provider",
    "get_document_source",
    "get_embedding_provider",
    "get_approval_provider",
    "get_ontology_provider",
    "get_graph_provider",
    "get_secrets_provider",
    "get_auth_provider",
]
