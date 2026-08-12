"""Each get_*_provider(config) must resolve the class matching
config.<section>.provider, and raise ValueError for an unknown value -
the contract every provider seam promises (see src/providers/__init__.py's
docstring)."""

from __future__ import annotations

import pytest

import providers
from config.app_config import (
    AppConfig,
    ApprovalConfig,
    AuthConfig,
    DocumentSourceConfig,
    EmbeddingConfig,
    GraphConfig,
    LLMConfig,
    OntologyConfig,
    SecretsConfig,
    StorageConfig,
)
from providers.auth_provider import AzureADAuthProvider, LocalAuthProvider, get_auth_provider
from providers.azure_openai_embedding_provider import AzureOpenAIEmbeddingProvider
from providers.azure_openai_llm_provider import AzureOpenAIChatLLMProvider
from providers.local_embedding_provider import LocalEmbeddingProvider
from providers.local_folder_source import LocalFolderSource
from providers.local_ontology_provider import LocalOntologyProvider
from providers.local_storage_provider import LocalStorageProvider
from providers.neo4j_graph_provider import Neo4jGraphProvider
from providers.secrets_provider import (
    AzureKeyVaultSecretsProvider,
    EnvSecretsProvider,
    get_secrets_provider,
)
from review.local_repository import LocalOntologyRepository


def _config(tmp_path, **overrides) -> AppConfig:
    config = AppConfig(storage=StorageConfig(provider="local", root=str(tmp_path)))
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def test_storage_provider_local(tmp_path):
    assert isinstance(providers.get_storage_provider(_config(tmp_path)), LocalStorageProvider)


def test_storage_provider_unknown_raises(tmp_path):
    config = _config(tmp_path, storage=StorageConfig(provider="bogus", root=str(tmp_path)))
    with pytest.raises(ValueError):
        providers.get_storage_provider(config)


def test_document_source_local_folder(tmp_path):
    assert isinstance(providers.get_document_source(_config(tmp_path)), LocalFolderSource)


def test_document_source_unknown_raises(tmp_path):
    config = _config(tmp_path, document_source=DocumentSourceConfig(provider="bogus"))
    with pytest.raises(ValueError):
        providers.get_document_source(config)


def test_embedding_provider_local_noop(tmp_path):
    assert isinstance(providers.get_embedding_provider(_config(tmp_path)), LocalEmbeddingProvider)


def test_embedding_provider_unknown_raises(tmp_path):
    config = _config(tmp_path, embedding=EmbeddingConfig(provider="bogus"))
    with pytest.raises(ValueError):
        providers.get_embedding_provider(config)


def test_embedding_provider_azure_openai(tmp_path, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    config = _config(tmp_path, embedding=EmbeddingConfig(provider="azure_openai"))
    assert isinstance(providers.get_embedding_provider(config), AzureOpenAIEmbeddingProvider)


def test_embedding_provider_azure_openai_missing_secrets_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    config = _config(tmp_path, embedding=EmbeddingConfig(provider="azure_openai"))
    with pytest.raises(ValueError):
        providers.get_embedding_provider(config)


def test_approval_provider_local(tmp_path):
    assert isinstance(providers.get_approval_provider(_config(tmp_path)), LocalOntologyRepository)


def test_approval_provider_unknown_raises(tmp_path):
    config = _config(tmp_path, approval=ApprovalConfig(provider="bogus"))
    with pytest.raises(ValueError):
        providers.get_approval_provider(config)


def test_ontology_provider_local(tmp_path):
    assert isinstance(providers.get_ontology_provider(_config(tmp_path)), LocalOntologyProvider)


def test_ontology_provider_unknown_raises(tmp_path):
    config = _config(tmp_path, ontology=OntologyConfig(provider="bogus"))
    with pytest.raises(ValueError):
        providers.get_ontology_provider(config)


def test_graph_provider_neo4j(tmp_path, monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
    assert isinstance(providers.get_graph_provider(_config(tmp_path)), Neo4jGraphProvider)


def test_graph_provider_neo4j_missing_secret_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    with pytest.raises(ValueError):
        providers.get_graph_provider(_config(tmp_path))


def test_graph_provider_unknown_raises(tmp_path):
    config = _config(tmp_path, graph=GraphConfig(provider="bogus"))
    with pytest.raises(ValueError):
        providers.get_graph_provider(config)


def test_llm_provider_azure_openai(tmp_path, monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    assert isinstance(providers.get_llm_provider(_config(tmp_path)), AzureOpenAIChatLLMProvider)


def test_llm_provider_azure_openai_missing_secrets_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        providers.get_llm_provider(_config(tmp_path))


def test_llm_provider_unknown_raises(tmp_path):
    config = _config(tmp_path, llm=LLMConfig(provider="bogus"))
    with pytest.raises(ValueError):
        providers.get_llm_provider(config)


def test_secrets_provider_env(tmp_path):
    assert isinstance(get_secrets_provider(_config(tmp_path)), EnvSecretsProvider)


def test_secrets_provider_azure_key_vault(tmp_path):
    config = _config(
        tmp_path,
        secrets=SecretsConfig(
            provider="azure_key_vault", options={"vault_url": "https://kv.vault.azure.net/"}
        ),
    )
    assert isinstance(get_secrets_provider(config), AzureKeyVaultSecretsProvider)


def test_secrets_provider_azure_key_vault_requires_vault_url(tmp_path):
    config = _config(tmp_path, secrets=SecretsConfig(provider="azure_key_vault"))
    with pytest.raises(ValueError):
        get_secrets_provider(config)


def test_secrets_provider_unknown_raises(tmp_path):
    config = _config(tmp_path, secrets=SecretsConfig(provider="bogus"))
    with pytest.raises(ValueError):
        get_secrets_provider(config)


def test_auth_provider_local(tmp_path):
    assert isinstance(get_auth_provider(_config(tmp_path)), LocalAuthProvider)


def test_auth_provider_azure_ad(tmp_path):
    config = _config(tmp_path, auth=AuthConfig(provider="azure_ad"))
    assert isinstance(get_auth_provider(config), AzureADAuthProvider)


def test_auth_provider_unknown_raises(tmp_path):
    config = _config(tmp_path, auth=AuthConfig(provider="bogus"))
    with pytest.raises(ValueError):
        get_auth_provider(config)
