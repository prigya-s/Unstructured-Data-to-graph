"""
OntologyRepository: the abstraction boundary between the review workflow
and its storage backend.

The rest of the application (candidate_builder, ontology_generator,
publisher, the Streamlit pages) depends only on this interface - never on
LocalOntologyRepository or FutureOntoBricksRepository directly. Swapping to
a real OntoBricks-backed store later means implementing FutureOntoBricksRepository
and nothing else changes.

save_candidate_entity()/save_candidate_relationship() are upserts keyed by
id. The repository does not enforce workflow-state transitions or touch
history - callers mutate the object (including appending a HistoryEntry)
and then save it.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

from .models import CandidateEntity, CandidateRelationship


class OntologyRepository(ABC):
    @abstractmethod
    def save_candidate_entity(self, entity: CandidateEntity) -> None:
        ...

    @abstractmethod
    def save_candidate_relationship(self, relationship: CandidateRelationship) -> None:
        ...

    def save_candidate_entities(self, entities: list[CandidateEntity]) -> None:
        """Default: one save_candidate_entity() call per row. Backends that
        can batch (LocalOntologyRepository, FutureOntoBricksRepository)
        override this with a true single read/write - this default just
        guarantees any future backend that doesn't override still works."""
        for entity in entities:
            self.save_candidate_entity(entity)

    def save_candidate_relationships(self, relationships: list[CandidateRelationship]) -> None:
        for relationship in relationships:
            self.save_candidate_relationship(relationship)

    @abstractmethod
    def get_candidate_entities(self) -> list[CandidateEntity]:
        """All entities regardless of status."""
        ...

    @abstractmethod
    def get_candidate_relationships(self) -> list[CandidateRelationship]:
        """All relationships regardless of status."""
        ...

    @abstractmethod
    def get_approved_entities(self) -> list[CandidateEntity]:
        """Entities with status == APPROVED only."""
        ...

    @abstractmethod
    def get_approved_relationships(self) -> list[CandidateRelationship]:
        """Relationships with status == APPROVED only."""
        ...


def get_repository(
    backend: str | None = None,
    review_dir: Path | None = None,
    options: dict | None = None,
    secrets=None,
) -> OntologyRepository:
    """Factory. backend overrides env var ONTOLOGY_REPOSITORY_BACKEND
    (default "local"). Valid values: "local", "ontobricks". review_dir is
    forwarded to LocalOntologyRepository (which already accepts an optional
    directory override) - defaults to its own output/review/ path when not
    given, so existing callers are unaffected. options/secrets are forwarded
    to FutureOntoBricksRepository (SQL Warehouse connection details and a
    SecretsProvider to resolve them with) - unused by the local backend."""
    resolved = (backend or os.environ.get("ONTOLOGY_REPOSITORY_BACKEND") or "local").strip().lower()

    if resolved == "local":
        from .local_repository import LocalOntologyRepository
        return LocalOntologyRepository(review_dir)

    if resolved == "ontobricks":
        from .ontobricks_stub import FutureOntoBricksRepository
        return FutureOntoBricksRepository(options or {}, secrets)

    raise ValueError(
        f"Unknown ONTOLOGY_REPOSITORY_BACKEND '{resolved}'. Valid values: 'local', 'ontobricks'."
    )
