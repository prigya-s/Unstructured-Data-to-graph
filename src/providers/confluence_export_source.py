"""
ConfluenceExportSource: DocumentSource backed by a pre-exported, flattened
Confluence page tree (one JSON file per page, nested directories mirroring
Confluence's parent/child page structure - e.g. docs/MYDET). Distinct from
the ConfluenceSource stub (that one is for the live Confluence REST API;
this is a static dump on disk).

Each page JSON carries: page_id, title, space_key, version, content_hash,
sanitized_text, metadata{has_images,has_tables,has_code_blocks,link_count,
heading_count,paragraph_count,headings:[{level,text}]}, stored_at,
is_deleted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .document_source import DocumentSource

_MACRO_ARTIFACT_RE = re.compile(r"MAC\d+(?:true|false)")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_text(text: str, title: str) -> str:
    text = _MACRO_ARTIFACT_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    if title and text.endswith(title):
        text = text[: -len(title)].rstrip()
    return text


def _reconstruct_headings(text: str, headings: list[dict]) -> str:
    """sanitized_text has almost no real line breaks - Confluence's plain-text
    extraction concatenates paragraphs/macros directly against each other. A
    heading marker inserted without surrounding newlines would sit mid-line,
    so semantic_chunker's per-line heading regex swallows everything after it
    (up to the next real \\n) into the heading's own title instead of body
    text, collapsing the whole section to zero content. Blank lines on both
    sides isolate the marker on its own line and push whatever follows onto a
    new line, so it lands in the section body instead."""
    for heading in headings:
        heading_text = heading.get("text")
        if not heading_text or heading_text not in text:
            continue
        level = heading.get("level") or 1
        marker = f"\n\n{'#' * level} {heading_text}\n\n"
        text = text.replace(heading_text, marker, 1)
    return text


class ConfluenceExportSource(DocumentSource):
    def __init__(self, path: str | Path, cache_dir: str | Path | None = None) -> None:
        self.path = Path(path)
        self.cache_dir = Path(cache_dir) if cache_dir else self.path / ".markdown_cache"

    def list_documents(self) -> list[dict]:
        documents = []
        for file_path in sorted(self.path.glob("pages/**/*.json")):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if data.get("is_deleted"):
                continue

            parent_name = file_path.parent.name
            parent_page_id = None if parent_name == "pages" else parent_name

            documents.append(
                {
                    "document_id": data["page_id"],
                    "document_name": data["title"],
                    "source_path": str(file_path),
                    "parent_page_id": parent_page_id,
                    "space_key": data.get("space_key"),
                    "version": data.get("version"),
                    "content_hash": data.get("content_hash"),
                }
            )
        return documents

    def read_document(self, doc_ref: dict) -> Path:
        data = json.loads(Path(doc_ref["source_path"]).read_text(encoding="utf-8"))
        title = data["title"]
        cleaned = _clean_text(data.get("sanitized_text", ""), title)
        headings = data.get("metadata", {}).get("headings", [])
        cleaned = _reconstruct_headings(cleaned, headings)
        markdown = f"# {title}\n\n{cleaned}"

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.cache_dir / f"{doc_ref['document_id']}.md"
        out_path.write_text(markdown, encoding="utf-8")
        return out_path
