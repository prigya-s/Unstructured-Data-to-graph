"""
Per-chat-turn retrieval trace endpoints: given a thread_id + turn_index
already recorded in api/routers/chat.py's _retrieval_trace_history,
regenerates the Cypher query and connectivity/snapshot view for that turn's
retrieval, reusing src/retrieval/retrieval_trace_builder.py (the same logic
verified live against the graph in demo_coa_vector_vs_graph.py).

Read-only and debug/demo-only: 404s once a thread/turn is no longer in the
in-memory _retrieval_trace_history (e.g. the backend restarted since that
answer was generated) rather than trying to reconstruct anything.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api import deps
from api.routers.chat import _retrieval_trace_history
from retrieval.retrieval_trace_builder import browser_query, compute_connectivity, graph_snapshot

router = APIRouter()


def _get_entry(thread_id: str, turn_index: int):
    entries = _retrieval_trace_history.get(thread_id)
    if entries is None or turn_index < 0 or turn_index >= len(entries):
        raise HTTPException(
            status_code=404,
            detail="Retrieval trace data is no longer available for that turn - it may predate the current backend session.",
        )
    return entries[turn_index]


@router.get("/api/retrieval-trace/threads/{thread_id}/turns/{turn_index}")
def get_retrieval_trace_turn(thread_id: str, turn_index: int, graph_provider=Depends(deps.get_graph_provider)) -> dict:
    entry = _get_entry(thread_id, turn_index)

    connectivity = compute_connectivity(
        graph_provider, entry.chunk_ids, entry.graph_expansion_hops, entry.page_link_hops
    )

    return {
        "question": entry.question,
        "turn_index": turn_index,
        "chunk_count": len(entry.chunk_ids),
        "entity_count": len(entry.entity_ids),
        "document_count": len(entry.document_ids),
        "graph_expansion_hops": entry.graph_expansion_hops,
        "page_link_hops": entry.page_link_hops,
        "cypher_full": browser_query(entry.chunk_ids, entry.graph_expansion_hops, entry.page_link_hops),
        "cypher_largest_cluster": browser_query(
            connectivity.largest_cluster_chunk_ids, entry.graph_expansion_hops, entry.page_link_hops
        ),
        "connectivity": {
            "cluster_count": connectivity.cluster_count,
            "clusters": [
                {"chunk_count": len(cluster.chunk_ids), "document_names": cluster.document_names}
                for cluster in connectivity.clusters
            ],
        },
    }


@router.get("/api/retrieval-trace/threads/{thread_id}/turns/{turn_index}/graph")
def get_retrieval_trace_graph(thread_id: str, turn_index: int, graph_provider=Depends(deps.get_graph_provider)) -> dict:
    entry = _get_entry(thread_id, turn_index)

    connectivity = compute_connectivity(
        graph_provider, entry.chunk_ids, entry.graph_expansion_hops, entry.page_link_hops
    )
    return graph_snapshot(
        graph_provider, connectivity.largest_cluster_chunk_ids, entry.graph_expansion_hops, entry.page_link_hops
    )
