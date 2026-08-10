"""
LocalStorageProvider: JSON-file backed StorageProvider implementing the
bronze/silver/gold layout under a configurable root (default ./lakehouse).

Uses the same read/write-a-JSON-array-file pattern review/local_repository.py
already uses for the approval workflow - no new persistence pattern
invented. Each write_* call overwrites the full manifest for that table
(mirroring how the pre-refactor main.py wrote entities.json/relationships.json
fresh on every ingest run), not an upsert - upsert-by-id semantics stay
where they already live, inside the approval workflow.
"""

from __future__ import annotations

import json
from pathlib import Path

from .storage_provider import StorageProvider


class LocalStorageProvider(StorageProvider):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.bronze = self.root / "bronze"
        self.silver = self.root / "silver"
        self.gold = self.root / "gold"
        for directory in (self.bronze, self.silver, self.gold):
            directory.mkdir(parents=True, exist_ok=True)

    # -- generic JSON manifest helpers ---------------------------------------

    def _write_json(self, path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _read_json(self, path: Path, default):
        if not path.exists():
            return default
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return default
        return json.loads(text)

    # -- bronze ---------------------------------------------------------------

    def write_documents(self, records: list[dict]) -> None:
        self._write_json(self.bronze / "raw_documents" / "documents.json", records)

    def read_documents(self) -> list[dict]:
        return self._read_json(self.bronze / "raw_documents" / "documents.json", [])

    # -- silver -----------------------------------------------------------------

    def write_markdown(self, records: list[dict]) -> None:
        """Writes a per-document .md text file (for human readability,
        mirroring the pre-refactor output/markdown/ layout) plus the
        manifest. markdown_path is filled in here, not by the caller, since
        this is the only place under LocalStorageProvider that owns the
        on-disk layout."""
        markdown_dir = self.silver / "markdown"
        markdown_dir.mkdir(parents=True, exist_ok=True)
        resolved_records = []
        for record in records:
            md_path = markdown_dir / f"{record['document_id']}.md"
            md_path.write_text(record["markdown"], encoding="utf-8")
            resolved_records.append({**record, "markdown_path": str(md_path)})
        self._write_json(markdown_dir / "markdown.json", resolved_records)

    def read_markdown(self) -> list[dict]:
        return self._read_json(self.silver / "markdown" / "markdown.json", [])

    def write_chunks(self, records: list[dict]) -> None:
        self._write_json(self.silver / "chunks" / "chunks.json", records)

    def read_chunks(self) -> list[dict]:
        return self._read_json(self.silver / "chunks" / "chunks.json", [])

    def write_embeddings(self, records: list[dict]) -> None:
        self._write_json(self.silver / "embeddings" / "embeddings.json", records)

    def read_embeddings(self) -> list[dict]:
        return self._read_json(self.silver / "embeddings" / "embeddings.json", [])

    # -- gold -------------------------------------------------------------------

    def write_entities(self, entities: list[dict], mentions: list[dict]) -> None:
        self._write_json(self.gold / "entities" / "entities.json", entities)
        self._write_json(self.gold / "entities" / "mentions.json", mentions)

    def read_entities(self) -> tuple[list[dict], list[dict]]:
        entities = self._read_json(self.gold / "entities" / "entities.json", [])
        mentions = self._read_json(self.gold / "entities" / "mentions.json", [])
        return entities, mentions

    def write_relationships(self, records: list[dict]) -> None:
        self._write_json(self.gold / "relationships" / "relationships.json", records)

    def read_relationships(self) -> list[dict]:
        return self._read_json(self.gold / "relationships" / "relationships.json", [])

    def write_approved_entities(self, records: list[dict]) -> None:
        self._write_json(self.gold / "approved_entities" / "approved_entities.json", records)

    def read_approved_entities(self) -> list[dict]:
        return self._read_json(self.gold / "approved_entities" / "approved_entities.json", [])

    def write_approved_relationships(self, records: list[dict]) -> None:
        self._write_json(
            self.gold / "approved_relationships" / "approved_relationships.json", records
        )

    def read_approved_relationships(self) -> list[dict]:
        return self._read_json(
            self.gold / "approved_relationships" / "approved_relationships.json", []
        )

    def write_ontology(self, record: dict) -> None:
        self._write_json(self.gold / "ontology" / "ontology.json", record)

    def read_ontology(self) -> dict | None:
        return self._read_json(self.gold / "ontology" / "ontology.json", None)

    def write_graph_export(self, record: dict) -> None:
        self._write_json(self.gold / "graph_exports" / "graph_export.json", record)

    def read_graph_export(self) -> dict | None:
        return self._read_json(self.gold / "graph_exports" / "graph_export.json", None)
