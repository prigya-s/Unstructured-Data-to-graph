"""
Query cache for the GraphRAG chat agent: repeated or rephrased-but-equivalent
questions - common across demo rehearsals and the live run itself - skip
retrieval and LLM generation entirely, returning a previously computed
answer instead.

Exact-normalized-text matches are found without embedding the incoming
query. Near-duplicate matches are found via cosine similarity against the
embeddings of previously cached queries, reusing the same EmbeddingProvider
already wired into GraphRAG retrieval (src/retrieval/graphrag_service.py) -
no new dependency.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from retrieval.graphrag_service import RetrievalResult, embed_query


def _normalize(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class CacheHit:
    answer: str
    result: RetrievalResult


class QueryCache:
    """In-memory cache of (query, answer, RetrievalResult), keyed by
    normalized query text with a cosine-similarity fallback for
    rephrased questions. Bounded FIFO eviction keeps memory flat across a
    long demo session."""

    def __init__(self, embedding_provider, *, similarity_threshold: float, max_entries: int) -> None:
        self._embedding_provider = embedding_provider
        self._similarity_threshold = similarity_threshold
        self._max_entries = max_entries
        self._entries: list[dict] = []

    def lookup(self, query: str) -> tuple[CacheHit | None, list[float] | None]:
        """Returns `(hit, query_vector)`. `hit` is None on a miss. On a
        miss where an embedding was already computed for the similarity
        check, `query_vector` is returned too so the caller's later
        `store()` call doesn't have to embed the same query twice."""
        normalized = _normalize(query)
        for entry in self._entries:
            if entry["query"] == normalized:
                return CacheHit(entry["answer"], entry["result"]), None

        if not self._entries:
            return None, None

        query_vector = embed_query(self._embedding_provider, query)
        best_entry = None
        best_score = 0.0
        for entry in self._entries:
            score = _cosine_similarity(query_vector, entry["vector"])
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry is not None and best_score >= self._similarity_threshold:
            return CacheHit(best_entry["answer"], best_entry["result"]), query_vector
        return None, query_vector

    def store(self, query: str, query_vector: list[float] | None, answer: str, result: RetrievalResult) -> None:
        vector = query_vector if query_vector is not None else embed_query(self._embedding_provider, query)
        self._entries.append(
            {"query": _normalize(query), "vector": vector, "answer": answer, "result": result}
        )
        if len(self._entries) > self._max_entries:
            self._entries.pop(0)
