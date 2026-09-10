"""QueryCache must partition every entry by requester_groups (see
_group_key in src/retrieval/query_cache.py) - two requesters with different
document access must never share a cache hit, even for the exact same
question, or a permission-filtered RetrievalResult (its citations/entities)
would leak from one requester to another via the cache."""

from __future__ import annotations

from retrieval.graphrag_service import RetrievalResult
from retrieval.query_cache import QueryCache


class FakeEmbeddingProvider:
    def embed_chunks(self, chunks):
        return [
            {"chunk_id": chunk["chunk_id"], "document": chunk["document"], "embedding_vector": [0.1, 0.2]}
            for chunk in chunks
        ]


def _cache() -> QueryCache:
    return QueryCache(FakeEmbeddingProvider(), similarity_threshold=0.9, max_entries=10)


def test_lookup_misses_on_an_empty_cache():
    cache = _cache()
    hit, _ = cache.lookup("what is billing?", requester_groups=["finance"])
    assert hit is None


def test_lookup_hits_for_the_same_query_and_same_requester_groups():
    cache = _cache()
    result = RetrievalResult(chunks=[{"chunk_id": "c1"}])
    cache.store("what is billing?", None, "Billing is a process.", result, requester_groups=["finance"])

    hit, _ = cache.lookup("what is billing?", requester_groups=["finance"])

    assert hit is not None
    assert hit.answer == "Billing is a process."
    assert hit.result is result


def test_lookup_does_not_hit_across_different_requester_groups():
    cache = _cache()
    result = RetrievalResult(chunks=[{"chunk_id": "c1"}])
    cache.store("what is billing?", None, "Billing is a process.", result, requester_groups=["finance"])

    hit, _ = cache.lookup("what is billing?", requester_groups=["engineering"])

    assert hit is None


def test_lookup_treats_unfiltered_none_as_its_own_partition():
    cache = _cache()
    result = RetrievalResult(chunks=[{"chunk_id": "c1"}])
    cache.store("what is billing?", None, "Billing is a process.", result, requester_groups=None)

    hit, _ = cache.lookup("what is billing?", requester_groups=[])

    assert hit is None


def test_lookup_is_insensitive_to_requester_group_order():
    cache = _cache()
    result = RetrievalResult(chunks=[{"chunk_id": "c1"}])
    cache.store("what is billing?", None, "Billing is a process.", result, requester_groups=["a", "b"])

    hit, _ = cache.lookup("what is billing?", requester_groups=["b", "a"])

    assert hit is not None
