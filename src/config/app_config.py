"""
AppConfig: the single schema for both local and Databricks execution modes.

Loaded once at startup from config.yaml (path overridable via the
KGLOCAL_CONFIG env var). Everything downstream - the provider factories in
src/providers/__init__.py, the pipeline stages, main.py - reads AppConfig
values, never raw environment variables or hardcoded paths directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _PROJECT_ROOT / "src"
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"


@dataclass
class StorageConfig:
    provider: str = "local"
    root: str = "./lakehouse"
    options: dict = field(default_factory=dict)


@dataclass
class DocumentSourceConfig:
    provider: str = "local_folder"
    options: dict = field(default_factory=dict)


@dataclass
class EmbeddingConfig:
    provider: str = "local_noop"
    options: dict = field(default_factory=dict)


@dataclass
class ApprovalConfig:
    provider: str = "local"
    options: dict = field(default_factory=dict)


@dataclass
class OntologyConfig:
    provider: str = "local"
    schema_path: str = "ontology/ontology.yaml"


@dataclass
class GraphConfig:
    provider: str = "neo4j"
    options: dict = field(default_factory=dict)


@dataclass
class SecretsConfig:
    provider: str = "env"
    options: dict = field(default_factory=dict)


@dataclass
class AuthConfig:
    provider: str = "local"
    options: dict = field(default_factory=dict)


@dataclass
class ObservabilityConfig:
    log_dir: str = "./logs"


@dataclass
class LLMConfig:
    """Chat-completion backend for the GraphRAG conversational layer -
    resolves to a Microsoft Agent Framework chat client. See
    src/providers/llm_provider.py."""

    provider: str = "azure_openai"
    options: dict = field(default_factory=dict)


@dataclass
class RetrievalConfig:
    """Tunables for src/retrieval/graphrag_service.py. Not a provider
    section (no swappable backend today - Neo4j-only) so it has no
    `provider` key, just options with defaults."""

    top_k_chunks: int = 8
    graph_expansion_hops: int = 1
    max_neighbors: int = 20
    agent_timeout_seconds: int = 60
    max_query_length: int = 4000


@dataclass
class AppConfig:
    storage: StorageConfig = field(default_factory=StorageConfig)
    document_source: DocumentSourceConfig = field(default_factory=DocumentSourceConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    approval: ApprovalConfig = field(default_factory=ApprovalConfig)
    ontology: OntologyConfig = field(default_factory=OntologyConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    secrets: SecretsConfig = field(default_factory=SecretsConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)

    @property
    def storage_root(self) -> Path:
        root = Path(self.storage.root)
        if root.is_absolute():
            return root
        return (_PROJECT_ROOT / root).resolve()

    @property
    def ontology_schema_path(self) -> Path:
        path = Path(self.ontology.schema_path)
        if path.is_absolute():
            return path
        return (_SRC_DIR / path).resolve()

    @property
    def log_dir(self) -> Path:
        path = Path(self.observability.log_dir)
        if path.is_absolute():
            return path
        return (_PROJECT_ROOT / path).resolve()


def _config_path() -> Path:
    override = os.environ.get("KGLOCAL_CONFIG")
    return Path(override) if override else _DEFAULT_CONFIG_PATH


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path else _config_path()
    if not config_path.exists():
        return AppConfig()

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    storage_raw = dict(raw.get("storage") or {})
    storage_provider = storage_raw.pop("provider", "local")
    storage_root = storage_raw.pop("root", "./lakehouse")

    document_source_raw = dict(raw.get("document_source") or {})
    document_source_provider = document_source_raw.pop("provider", "local_folder")

    embedding_raw = dict(raw.get("embedding") or {})
    embedding_provider = embedding_raw.pop("provider", "local_noop")

    graph_raw = dict(raw.get("graph") or {})
    graph_provider = graph_raw.pop("provider", "neo4j")

    approval_raw = dict(raw.get("approval") or {})
    approval_provider = approval_raw.pop("provider", "local")

    secrets_raw = dict(raw.get("secrets") or {})
    secrets_provider = secrets_raw.pop("provider", "env")

    auth_raw = dict(raw.get("auth") or {})
    auth_provider = auth_raw.pop("provider", "local")

    llm_raw = dict(raw.get("llm") or {})
    llm_provider = llm_raw.pop("provider", "azure_openai")

    retrieval_raw = dict(raw.get("retrieval") or {})

    return AppConfig(
        storage=StorageConfig(
            provider=storage_provider, root=storage_root, options=storage_raw
        ),
        document_source=DocumentSourceConfig(
            provider=document_source_provider, options=document_source_raw
        ),
        embedding=EmbeddingConfig(provider=embedding_provider, options=embedding_raw),
        approval=ApprovalConfig(provider=approval_provider, options=approval_raw),
        ontology=OntologyConfig(**(raw.get("ontology") or {})),
        graph=GraphConfig(provider=graph_provider, options=graph_raw),
        secrets=SecretsConfig(provider=secrets_provider, options=secrets_raw),
        auth=AuthConfig(provider=auth_provider, options=auth_raw),
        observability=ObservabilityConfig(**(raw.get("observability") or {})),
        llm=LLMConfig(provider=llm_provider, options=llm_raw),
        retrieval=RetrievalConfig(**retrieval_raw),
    )
