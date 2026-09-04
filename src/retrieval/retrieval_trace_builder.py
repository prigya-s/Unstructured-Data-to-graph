"""
Turns a set of retrieved chunk_ids back into (a) a ready-to-paste Neo4j
Browser query and (b) a connectivity/snapshot view of what that query would
show - the same logic verified live against the graph in
demo_coa_vector_vs_graph.py, made importable so api/routers/retrieval_trace.py
can serve it per chat turn instead of only via a standalone script.

Every hop's relationship is bound to its own variable (h, m, r, l) and
returned explicitly - Neo4j Browser only draws an edge for a relationship
that comes back in the result, so a query that only returns node variables
(even when a path clearly connects them) renders as disconnected dots.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ClusterInfo:
    chunk_ids: list[str]
    document_names: list[str]


@dataclass
class ConnectivityResult:
    cluster_count: int
    clusters: list[ClusterInfo] = field(default_factory=list)
    largest_cluster_chunk_ids: list[str] = field(default_factory=list)


def browser_query(chunk_ids: list[str], graph_expansion_hops: int, page_link_hops: int) -> str:
    return (
        "MATCH (c:Chunk) WHERE c.id IN " + repr(chunk_ids) + "\n"
        "OPTIONAL MATCH (d:Document)-[h:HAS_CHUNK]->(c)\n"
        "OPTIONAL MATCH (c)-[m:MENTIONS]->(e:Entity)\n"
        "OPTIONAL MATCH (e)-[r*1..%d]-(n:Entity)\n"
        "OPTIONAL MATCH (d)-[l:LEADS_TO*1..%d]->(nd:Document)\n"
        "RETURN c, d, h, e, m, n, r, nd, l" % (graph_expansion_hops, page_link_hops)
    )


def _probe_rows(graph_provider, chunk_ids: list[str], graph_expansion_hops: int, page_link_hops: int) -> list[dict]:
    return graph_provider.query_graph(
        "MATCH (c:Chunk) WHERE c.id IN $chunk_ids\n"
        "OPTIONAL MATCH (d:Document)-[:HAS_CHUNK]->(c)\n"
        "OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)\n"
        "OPTIONAL MATCH (e)-[*1..%d]-(n:Entity)\n"
        "OPTIONAL MATCH (d)-[:LEADS_TO*1..%d]->(nd:Document)\n"
        "RETURN c.id AS c, d.name AS d, e.name AS e, n.name AS n, nd.name AS nd"
        % (graph_expansion_hops, page_link_hops),
        {"chunk_ids": chunk_ids},
    )


def compute_connectivity(
    graph_provider, chunk_ids: list[str], graph_expansion_hops: int, page_link_hops: int
) -> ConnectivityResult:
    if not chunk_ids:
        return ConnectivityResult(cluster_count=0)

    rows = _probe_rows(graph_provider, chunk_ids, graph_expansion_hops, page_link_hops)

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    chunk_to_doc: dict[str, str] = {}
    for row in rows:
        c_node, d_node = "C:" + row["c"], ("D:" + row["d"] if row["d"] else None)
        e_node, n_node = ("E:" + row["e"] if row["e"] else None), ("E:" + row["n"] if row["n"] else None)
        nd_node = "D:" + row["nd"] if row["nd"] else None
        find(c_node)
        if d_node:
            union(c_node, d_node)
            chunk_to_doc[row["c"]] = row["d"]
        if e_node:
            union(c_node, e_node)
        if e_node and n_node:
            union(e_node, n_node)
        if d_node and nd_node:
            union(d_node, nd_node)

    grouped: dict[str, list[str]] = {}
    for chunk_id in chunk_ids:
        grouped.setdefault(find("C:" + chunk_id), []).append(chunk_id)

    clusters = [
        ClusterInfo(
            chunk_ids=members,
            document_names=sorted({chunk_to_doc.get(cid, "?") for cid in members}),
        )
        for members in sorted(grouped.values(), key=len, reverse=True)
    ]

    return ConnectivityResult(
        cluster_count=len(clusters),
        clusters=clusters,
        largest_cluster_chunk_ids=clusters[0].chunk_ids if clusters else [],
    )


def graph_snapshot(
    graph_provider, chunk_ids: list[str], graph_expansion_hops: int, page_link_hops: int
) -> dict:
    """Reshapes the same probe rows used for connectivity into a deduped
    {"nodes": [...], "edges": [...]} shape for an embedded graph view.
    Entity-entity edges are undirected (get_neighbors itself traverses
    Entity<->Entity without a fixed direction), so they're labeled RELATED
    rather than a specific relationship type."""
    if not chunk_ids:
        return {"nodes": [], "edges": []}

    rows = _probe_rows(graph_provider, chunk_ids, graph_expansion_hops, page_link_hops)

    nodes: dict[str, dict] = {}
    edges: set[tuple[str, str, str]] = set()

    def add_node(node_id: str, label: str, name: str) -> None:
        nodes.setdefault(node_id, {"id": node_id, "label": label, "name": name})

    for row in rows:
        chunk_node = f"chunk:{row['c']}"
        add_node(chunk_node, "Chunk", row["c"])

        doc_node = f"doc:{row['d']}" if row["d"] else None
        if doc_node:
            add_node(doc_node, "Document", row["d"])
            edges.add((doc_node, chunk_node, "HAS_CHUNK"))

        entity_node = f"entity:{row['e']}" if row["e"] else None
        if entity_node:
            add_node(entity_node, "Entity", row["e"])
            edges.add((chunk_node, entity_node, "MENTIONS"))

        neighbor_node = f"entity:{row['n']}" if row["n"] else None
        if neighbor_node:
            add_node(neighbor_node, "Entity", row["n"])
        if entity_node and neighbor_node and neighbor_node != entity_node:
            edges.add((entity_node, neighbor_node, "RELATED"))

        linked_doc_node = f"doc:{row['nd']}" if row["nd"] else None
        if doc_node and linked_doc_node and linked_doc_node != doc_node:
            add_node(linked_doc_node, "Document", row["nd"])
            edges.add((doc_node, linked_doc_node, "LEADS_TO"))

    return {
        "nodes": list(nodes.values()),
        "edges": [{"source": s, "target": t, "type": rel} for s, t, rel in sorted(edges)],
    }
