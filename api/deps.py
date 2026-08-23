"""
Shared FastAPI dependencies: process-wide provider singletons plus request
identity. Mirrors app/common.py's get_repo()/get_storage()/get_graph_provider()
helpers - same factories from providers/__init__.py, built once at startup
here instead of once-per-Streamlit-rerun.

get_current_reviewer() is the one piece that is NOT a port of app/common.py's
reviewer_name(): that function calls AuthProvider.current_user(), and
LocalAuthProvider renders a Streamlit sidebar widget to ask for a name
(src/providers/auth_provider.py), which has no equivalent in an HTTP request.
A reviewer identity header takes its place here - the same identity-header
approach AzureADAuthProvider's own docstring already describes as the
intended future direction. LocalAuthProvider itself is untouched; it keeps
serving the Streamlit app until that app is retired.
"""

from __future__ import annotations

import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _API_DIR.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from fastapi import Header

import providers
from agents.graphrag_agent import GraphRAGAgent, build_agent
from config import load_config
from config.app_config import AppConfig
from graph.startup import initialize_graph
from observability.logging_setup import configure_streamlit_logging
from review.repository import OntologyRepository

_config: AppConfig | None = None
_storage = None
_graph_provider = None
_embedding_provider = None
_llm_provider = None
_repository: OntologyRepository | None = None
_agent: GraphRAGAgent | None = None


def init_providers() -> None:
    """Builds every provider singleton once, at FastAPI startup - see
    api/main.py's lifespan handler. Never called per-request."""
    global _config, _storage, _graph_provider, _embedding_provider, _llm_provider, _repository, _agent

    _config = load_config()
    configure_streamlit_logging(_config)

    _storage = providers.get_storage_provider(_config)
    _graph_provider = providers.get_graph_provider(_config)
    initialize_graph(_graph_provider)
    _embedding_provider = providers.get_embedding_provider(_config)
    _llm_provider = providers.get_llm_provider(_config)
    _repository = providers.get_approval_provider(_config)
    _agent = build_agent(_llm_provider, _embedding_provider, _graph_provider, _config)


def get_config() -> AppConfig:
    assert _config is not None, "init_providers() must run before handling requests"
    return _config


def get_storage():
    assert _storage is not None, "init_providers() must run before handling requests"
    return _storage


def get_graph_provider():
    assert _graph_provider is not None, "init_providers() must run before handling requests"
    return _graph_provider


def get_repository() -> OntologyRepository:
    assert _repository is not None, "init_providers() must run before handling requests"
    return _repository


def get_agent() -> GraphRAGAgent:
    assert _agent is not None, "init_providers() must run before handling requests"
    return _agent


def get_current_reviewer(x_reviewer_name: str | None = Header(default=None)) -> str:
    return x_reviewer_name or "Reviewer"
