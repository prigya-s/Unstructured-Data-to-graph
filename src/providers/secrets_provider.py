"""
SecretsProvider: the abstraction boundary for resolving a secret's *value*
given the *name* of the secret (today, an env var name - see e.g.
graph.neo4j.uri_env in config.yaml).

Every credential-consuming provider (Neo4jGraphProvider, DeltaSqlTableStore,
DatabricksEmbeddingProvider) already reads config for the *name* of a
secret, never the value itself. SecretsProvider adds one more indirection on
top of that existing pattern: where the value actually comes from is now
itself provider-driven, so swapping plain env vars for Azure Key Vault is a
config change (secrets.provider: azure_key_vault), not a code change.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

from config.app_config import AppConfig


class SecretsProvider(ABC):
    @abstractmethod
    def get(self, name: str) -> str | None:
        """name: the name of the secret (an env var name, or - when backed
        by Key Vault - a Key Vault secret name). Returns the resolved value,
        or None if it isn't set."""


class EnvSecretsProvider(SecretsProvider):
    """Default: today's os.environ.get(name) behavior, unchanged."""

    def get(self, name: str) -> str | None:
        return os.environ.get(name)


class AzureKeyVaultSecretsProvider(SecretsProvider):
    """Resolves secrets from Azure Key Vault via DefaultAzureCredential -
    Managed Identity when running on Azure/Databricks, falling back to
    az-cli/VS Code/environment credentials locally. Deferred import of
    azure-identity/azure-keyvault-secrets (see requirements-azure.txt) -
    not exercised by local dev, and not executable without a real Key Vault
    and identity."""

    def __init__(self, vault_url: str) -> None:
        self.vault_url = vault_url
        self._client = None

    def _connect(self):
        if self._client is None:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient

            self._client = SecretClient(vault_url=self.vault_url, credential=DefaultAzureCredential())
        return self._client

    def get(self, name: str) -> str | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self._connect().get_secret(name).value
        except ResourceNotFoundError:
            return None


def get_secrets_provider(config: AppConfig) -> SecretsProvider:
    provider = config.secrets.provider
    if provider == "env":
        return EnvSecretsProvider()
    if provider == "azure_key_vault":
        vault_url = config.secrets.options.get("vault_url")
        if not vault_url:
            raise ValueError(
                "secrets.options.vault_url is required when secrets.provider is 'azure_key_vault'."
            )
        return AzureKeyVaultSecretsProvider(vault_url)
    raise ValueError(f"Unknown secrets.provider '{provider}'. Valid values: env, azure_key_vault.")
