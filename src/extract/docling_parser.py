"""
Phase 1: Document extraction.

Converts PDF / DOCX / PPTX / HTML source documents to Markdown using
Docling, preserving headings, tables, lists and page structure. Plain
text and Markdown files are already in (or trivially convertible to)
the target format and are passed through directly so the pipeline does
not require Docling (and its heavier optional dependencies) to be
installed just to run the local demo.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("kg_local.docling_parser")

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".html", ".htm", ".md", ".markdown"}

# Extensions that Docling itself knows how to parse (binary / rich formats).
_DOCLING_EXTENSIONS = {".pdf", ".docx", ".pptx", ".html", ".htm"}

_converter = None


def _get_converter():
    """Lazily construct a single, reusable Docling DocumentConverter."""
    global _converter
    if _converter is None:
        from docling.document_converter import DocumentConverter

        _converter = DocumentConverter()
    return _converter


def _convert_with_docling(file_path: Path) -> str:
    converter = _get_converter()
    result = converter.convert(str(file_path))
    return result.document.export_to_markdown()


def _convert_plain_text(file_path: Path) -> str:
    """Wrap a .txt file as Markdown, promoting the first line to a title
    heading if one is not already present."""
    raw = file_path.read_text(encoding="utf-8", errors="replace")
    stripped = raw.lstrip()
    if stripped.startswith("#"):
        return raw
    title = file_path.stem.replace("_", " ").replace("-", " ").title()
    return f"# {title}\n\n{raw}"


def _convert_markdown(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8", errors="replace")


def convert_to_markdown(file_path: str | Path) -> str:
    """Convert a single document to Markdown text.

    Raises ValueError for unsupported extensions.
    """
    file_path = Path(file_path)
    ext = file_path.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported document type: {ext} ({file_path.name})")

    logger.info("Extracting %s", file_path.name)

    if ext in _DOCLING_EXTENSIONS:
        return _convert_with_docling(file_path)
    if ext in (".md", ".markdown"):
        return _convert_markdown(file_path)
    if ext == ".txt":
        return _convert_plain_text(file_path)

    raise ValueError(f"Unhandled extension: {ext}")


def discover_documents(docs_dir: str | Path) -> list[Path]:
    """Return all supported document files under docs_dir, sorted by name."""
    docs_dir = Path(docs_dir)
    files = [
        p
        for p in sorted(docs_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    return files


def extract_all(docs_dir: str | Path, markdown_out_dir: str | Path) -> list[dict]:
    """Convert every supported document under docs_dir to Markdown and write
    it to markdown_out_dir.

    Returns a list of dicts: {"document_id", "document_name", "source_path",
    "markdown_path", "markdown"}.
    """
    docs_dir = Path(docs_dir)
    markdown_out_dir = Path(markdown_out_dir)
    markdown_out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for file_path in discover_documents(docs_dir):
        try:
            markdown = convert_to_markdown(file_path)
        except Exception:
            logger.exception("Failed to extract %s", file_path)
            continue

        doc_id = file_path.stem
        out_path = markdown_out_dir / f"{doc_id}.md"
        out_path.write_text(markdown, encoding="utf-8")

        results.append(
            {
                "document_id": doc_id,
                "document_name": file_path.name,
                "source_path": str(file_path),
                "markdown_path": str(out_path),
                "markdown": markdown,
            }
        )
        logger.info("Wrote markdown for %s -> %s", file_path.name, out_path)

    return results
