"""
ApprovalProvider: re-exports review.repository.OntologyRepository as the
provider-layer name for the approval seam. review/repository.py's
OntologyRepository ABC + get_repository() factory is already the correct
pattern this whole refactor generalizes - it is not being replaced or
renamed at its 8 existing call sites, just fulfilling the ApprovalProvider
role from here on.
"""

from __future__ import annotations

from config.app_config import AppConfig
from review.repository import OntologyRepository, get_repository

from .secrets_provider import get_secrets_provider

ApprovalProvider = OntologyRepository


def get_approval_provider(config: AppConfig) -> ApprovalProvider:
    review_dir = config.storage_root / "gold" / "review"
    ontobricks_options = config.approval.options.get("ontobricks", {})
    return get_repository(
        config.approval.provider,
        review_dir=review_dir,
        options=ontobricks_options,
        secrets=get_secrets_provider(config),
    )
