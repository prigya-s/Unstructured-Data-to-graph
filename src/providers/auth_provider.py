"""
AuthProvider: the abstraction boundary for resolving the identity of the
person using the Streamlit review app.

LocalAuthProvider preserves today's free-text "Your name" sidebar box -
explicitly dev-only, since it never verifies the name typed in. Roles are
fixed (any local user can approve/reject any candidate), matching today's
behavior exactly. AzureADAuthProvider is a stub: Databricks Apps and Azure
App Service both authenticate the caller and inject their identity at the
platform layer before a request reaches this code, so there is no login UI
to build here - only an identity header to read, once a real deployment
exists to validate that against.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from config.app_config import AppConfig


@dataclass
class AuthenticatedUser:
    id: str
    display_name: str
    roles: list[str] = field(default_factory=list)


class AuthProvider(ABC):
    @abstractmethod
    def current_user(self) -> AuthenticatedUser:
        ...


class LocalAuthProvider(AuthProvider):
    def current_user(self) -> AuthenticatedUser:
        import streamlit as st

        with st.sidebar:
            st.text_input(
                "Your name",
                key="reviewer_name",
                value=st.session_state.get("reviewer_name", "Reviewer"),
            )
        name = st.session_state.get("reviewer_name") or "Reviewer"
        return AuthenticatedUser(id=name, display_name=name, roles=["reviewer", "approver"])


class AzureADAuthProvider(AuthProvider):
    def current_user(self) -> AuthenticatedUser:
        raise NotImplementedError(
            "AzureADAuthProvider is not implemented. Set auth.provider: local in "
            "config.yaml for local/dev use, or implement this class to read the "
            "identity Databricks Apps or your Azure AD auth proxy injects into the request."
        )


def get_auth_provider(config: AppConfig) -> AuthProvider:
    provider = config.auth.provider
    if provider == "local":
        return LocalAuthProvider()
    if provider == "azure_ad":
        return AzureADAuthProvider()
    raise ValueError(f"Unknown auth.provider '{provider}'. Valid values: local, azure_ad.")
