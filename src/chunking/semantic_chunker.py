"""
Phase 2: Semantic chunking.

Splits a Markdown document into 500-800 token chunks with 100-token
overlap, preserving heading hierarchy as a "section_path" and keeping
list/table blocks intact (never split mid-block).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MIN_TOKENS = 500
MAX_TOKENS = 800
OVERLAP_TOKENS = 100

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

try:
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_ENCODING.encode(text))

except Exception:  # pragma: no cover - fallback when tiktoken/model unavailable

    def count_tokens(text: str) -> int:
        # Rough approximation: ~0.75 words per token on average English text.
        words = text.split()
        return max(1, int(len(words) / 0.75))


@dataclass
class _Section:
    path: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)


def _split_blocks(section_text: str) -> list[str]:
    """Split a section's body text into paragraph/list/table blocks,
    never breaking a table or list item across blocks."""
    lines = section_text.split("\n")
    blocks: list[str] = []
    current: list[str] = []
    in_table = False
    in_list = False

    def flush():
        if current:
            block = "\n".join(current).strip()
            if block:
                blocks.append(block)
            current.clear()

    for line in lines:
        stripped = line.strip()
        is_table_line = stripped.startswith("|")
        is_list_line = bool(re.match(r"^(\s*[-*+]\s+|\s*\d+[.)]\s+)", line))
        is_blank = stripped == ""

        if is_blank:
            if not in_table and not in_list:
                flush()
            else:
                current.append(line)
            in_table = False
            in_list = False
            continue

        if is_table_line:
            if not in_table and current and not in_list:
                flush()
            in_table = True
            in_list = False
            current.append(line)
            continue

        if is_list_line:
            in_list = True
            in_table = False
            current.append(line)
            continue

        if in_table or in_list:
            # continuation line inside a list item (indented) - keep together
            if line.startswith((" ", "\t")):
                current.append(line)
                continue
            flush()
            in_table = False
            in_list = False

        current.append(line)

    flush()
    return blocks


def _parse_sections(markdown: str) -> list[_Section]:
    """Walk the Markdown document and produce one _Section per heading,
    carrying the full heading-path from the document root."""
    lines = markdown.split("\n")
    sections: list[_Section] = []
    stack: list[str] = []
    body_lines: list[str] = []

    def close_section():
        if body_lines or stack:
            text = "\n".join(body_lines)
            blocks = _split_blocks(text)
            if blocks:
                sections.append(_Section(path=list(stack), blocks=blocks))
        body_lines.clear()

    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            close_section()
            level = len(match.group(1))
            title = match.group(2).strip()
            stack[:] = stack[: level - 1]
            while len(stack) < level - 1:
                stack.append("")
            if len(stack) == level - 1:
                stack.append(title)
            else:
                stack[level - 1] = title
                del stack[level:]
        else:
            body_lines.append(line)

    close_section()
    return [s for s in sections if any(b.strip() for b in s.blocks)]


def _blocks_to_chunks(document_id: str, section_path: str, blocks: list[str], start_index: int):
    """Greedily pack blocks into MIN..MAX token chunks with token overlap
    carried forward from the tail of the previous chunk."""
    chunks = []
    current_blocks: list[str] = []
    current_tokens = 0
    index = start_index

    def make_chunk(block_list: list[str]) -> dict:
        nonlocal index
        content = "\n\n".join(block_list).strip()
        chunk = {
            "chunk_id": f"{document_id}_chunk_{index:04d}",
            "document": document_id,
            "section_path": section_path,
            "content": content,
            "token_count": count_tokens(content),
        }
        index += 1
        return chunk

    def overlap_tail(block_list: list[str]) -> list[str]:
        """Return the trailing blocks of block_list worth ~OVERLAP_TOKENS."""
        tail: list[str] = []
        tokens = 0
        for block in reversed(block_list):
            tokens += count_tokens(block)
            tail.insert(0, block)
            if tokens >= OVERLAP_TOKENS:
                break
        return tail

    for block in blocks:
        block_tokens = count_tokens(block)

        if current_tokens + block_tokens > MAX_TOKENS and current_blocks:
            chunks.append(make_chunk(current_blocks))
            current_blocks = overlap_tail(current_blocks)
            current_tokens = sum(count_tokens(b) for b in current_blocks)

        current_blocks.append(block)
        current_tokens += block_tokens

        if current_tokens >= MAX_TOKENS:
            chunks.append(make_chunk(current_blocks))
            current_blocks = overlap_tail(current_blocks)
            current_tokens = sum(count_tokens(b) for b in current_blocks)

    if current_blocks:
        chunks.append(make_chunk(current_blocks))

    return chunks, index


def chunk_markdown(markdown: str, document_id: str) -> list[dict]:
    """Chunk a Markdown document into the chunk schema:
    {chunk_id, document, section_path, content, token_count}.
    """
    sections = _parse_sections(markdown)
    if not sections:
        return []

    all_chunks: list[dict] = []
    next_index = 0
    for section in sections:
        section_path = " > ".join(p for p in section.path if p) or document_id
        chunks, next_index = _blocks_to_chunks(
            document_id, section_path, section.blocks, next_index
        )
        all_chunks.extend(chunks)

    return all_chunks
