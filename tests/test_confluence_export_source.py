"""ConfluenceExportSource walks a pre-exported Confluence page tree (one
JSON file per page, nested dirs mirroring parent/child pages). Coverage:
list_documents() excludes soft-deleted pages and resolves parent_page_id
for nested vs. top-level pages; read_document() strips the MAC\\d+(true|
false) macro-artifact noise and a trailing duplicated title that show up
in the real corpus, and emits a '# Title' first line."""

from __future__ import annotations

import json

from chunking import semantic_chunker
from providers.confluence_export_source import ConfluenceExportSource


def _write_page(tmp_path, rel_path, **fields):
    file_path = tmp_path / "pages" / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "page_id": file_path.stem,
        "title": "Untitled",
        "space_key": "MYDET",
        "version": 1,
        "content_hash": "abc123",
        "sanitized_text": "",
        "metadata": {"headings": []},
        "stored_at": "2026-01-01T00:00:00Z",
        "is_deleted": False,
        **fields,
    }
    file_path.write_text(json.dumps(payload), encoding="utf-8")
    return file_path


def test_list_documents_resolves_top_level_parent_page_id(tmp_path):
    _write_page(tmp_path, "100.json", title="Top Level")

    source = ConfluenceExportSource(tmp_path)
    docs = source.list_documents()

    assert len(docs) == 1
    assert docs[0]["document_id"] == "100"
    assert docs[0]["parent_page_id"] is None


def test_list_documents_resolves_nested_parent_page_id(tmp_path):
    _write_page(tmp_path, "100.json", title="Parent")
    _write_page(tmp_path, "100/200.json", title="Child")

    source = ConfluenceExportSource(tmp_path)
    docs = {d["document_id"]: d for d in source.list_documents()}

    assert docs["200"]["parent_page_id"] == "100"
    assert docs["100"]["parent_page_id"] is None


def test_list_documents_excludes_deleted_pages(tmp_path):
    _write_page(tmp_path, "100.json", title="Live")
    _write_page(tmp_path, "101.json", title="Gone", is_deleted=True)

    source = ConfluenceExportSource(tmp_path)
    docs = source.list_documents()

    assert [d["document_id"] for d in docs] == ["100"]


def test_list_documents_carries_provenance_fields(tmp_path):
    _write_page(tmp_path, "100.json", title="Top", space_key="MYDET", version=3, content_hash="deadbeef")

    source = ConfluenceExportSource(tmp_path)
    doc = source.list_documents()[0]

    assert doc["space_key"] == "MYDET"
    assert doc["version"] == 3
    assert doc["content_hash"] == "deadbeef"


def test_read_document_strips_macro_artifacts_and_duplicate_title(tmp_path):
    file_path = _write_page(
        tmp_path,
        "100.json",
        title="Change of Address",
        sanitized_text="Some MAC123true instructions here.MAC456false Change of Address",
    )
    source = ConfluenceExportSource(tmp_path)
    doc_ref = {"document_id": "100", "source_path": str(file_path)}

    markdown_path = source.read_document(doc_ref)
    markdown = markdown_path.read_text(encoding="utf-8")

    assert "MAC123true" not in markdown
    assert "MAC456false" not in markdown
    assert markdown.startswith("# Change of Address")
    assert markdown.count("Change of Address") == 1


def test_read_document_reconstructs_headings(tmp_path):
    file_path = _write_page(
        tmp_path,
        "100.json",
        title="Top",
        sanitized_text="Intro text. Submitting a Form more details follow.",
        metadata={"headings": [{"level": 2, "text": "Submitting a Form"}]},
    )
    source = ConfluenceExportSource(tmp_path)
    doc_ref = {"document_id": "100", "source_path": str(file_path)}

    markdown = source.read_document(doc_ref).read_text(encoding="utf-8")

    assert "## Submitting a Form" in markdown


def test_read_document_heading_reconstruction_does_not_swallow_following_text(tmp_path):
    """Real MYDET pages have no line breaks between a heading's text and the
    prose that immediately follows it in sanitized_text (e.g. "Is the
    customer present?smallblueYeshttps://..."). If the inserted heading
    marker isn't isolated on its own line, semantic_chunker's per-line
    heading regex swallows that trailing prose into the heading's own title
    capture, leaving the section body empty - which is exactly what produced
    only 4 real chunks out of 176 MYDET documents before this fix."""
    file_path = _write_page(
        tmp_path,
        "100.json",
        title="Top",
        sanitized_text="Is the customer present?smallblueYeshttps://example.com/next-page",
        metadata={"headings": [{"level": 2, "text": "Is the customer present?"}]},
    )
    source = ConfluenceExportSource(tmp_path)
    doc_ref = {"document_id": "100", "source_path": str(file_path)}

    markdown = source.read_document(doc_ref).read_text(encoding="utf-8")
    lines = markdown.split("\n")
    heading_line_index = next(i for i, line in enumerate(lines) if line.startswith("##"))

    assert lines[heading_line_index] == "## Is the customer present?"
    assert "smallblueYeshttps" not in lines[heading_line_index]

    sections = semantic_chunker._parse_sections(markdown)
    assert any("smallblueYeshttps" in block for section in sections for block in section.blocks)
