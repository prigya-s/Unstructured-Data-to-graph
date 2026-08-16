"""
Shared entity-id formatting, used by both the deterministic
extraction.entity_extractor and providers.ollama_extraction_provider so
every ExtractionProvider implementation produces identically-shaped entity
ids (entity_{type}_{name}, both slugified) regardless of which one ran.
"""

from __future__ import annotations

import hashlib
import re


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or hashlib.md5(text.encode("utf-8")).hexdigest()[:8]


def build_entity_id(entity_type: str, name: str) -> str:
    return f"entity_{slugify(entity_type)}_{slugify(name)}"
