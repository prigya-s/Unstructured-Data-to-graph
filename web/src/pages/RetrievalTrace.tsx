import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import ForceGraph2D from "react-force-graph-2d";

import {
  getRetrievalTraceGraph,
  getRetrievalTraceTurn,
  RetrievalTraceGraphResponse,
  RetrievalTraceTurnResponse,
} from "../api/client";
import EmptyState from "../components/EmptyState";
import MetricTile from "../components/MetricTile";

// Matches Neo4j Browser's default per-label palette (colors are assigned to
// labels in the order they're first returned by a query - c, d, e here).
const NODE_COLORS: Record<string, string> = {
  Chunk: "#68bdf6",
  Document: "#6dce9e",
  Entity: "#faafc2",
};

const NODE_RADIUS: Record<string, number> = {
  Chunk: 1.2,
  Document: 2,
  Entity: 1.5,
};

// Neo4j Browser doesn't color relationships by type - all edges share one
// neutral line color, with the type shown as a hover label (see linkLabel).
const EDGE_COLOR = "#a5abb6";

export default function RetrievalTrace() {
  const [searchParams] = useSearchParams();
  const threadId = searchParams.get("thread");
  const turnIndex = Number(searchParams.get("turn") ?? "0");

  const [turn, setTurn] = useState<RetrievalTraceTurnResponse | null>(null);
  const [graph, setGraph] = useState<RetrievalTraceGraphResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!threadId) return;
    setLoading(true);
    setError(null);
    setTurn(null);
    setGraph(null);
    Promise.all([getRetrievalTraceTurn(threadId, turnIndex), getRetrievalTraceGraph(threadId, turnIndex)])
      .then(([turnData, graphData]) => {
        setTurn(turnData);
        setGraph(graphData);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [threadId, turnIndex]);

  if (!threadId) {
    return (
      <div className="page">
        <h1>Retrieval Trace</h1>
        <EmptyState>
          Ask a question on the "Ask the Knowledge Graph" page, then click "View retrieval trace" under its sources
          to inspect the Cypher query and graph traversal behind that answer.
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page__header">
        <h1>Retrieval Trace</h1>
      </div>

      {error && <p className="error">{error}</p>}
      {loading && <p className="muted">Loading...</p>}

      {turn && (
        <>
          <div className="trace-question">
            Turn {turn.turn_index}: <strong>{turn.question}</strong>
          </div>

          <div className="metric-grid">
            <MetricTile label="Chunks" value={turn.chunk_count} />
            <MetricTile label="Entities" value={turn.entity_count} />
            <MetricTile label="Documents" value={turn.document_count} />
            <MetricTile label="Clusters" value={turn.connectivity.cluster_count} />
          </div>

          <CollapsibleSection title="Retrieved chunks breakdown">
            <ConnectivityCallout connectivity={turn.connectivity} />
          </CollapsibleSection>

          <CollapsibleSection title="Cypher">
            <p className="muted">
              Paste either query directly into Neo4j Browser (hops: {turn.graph_expansion_hops} entity, {" "}
              {turn.page_link_hops} document link).
            </p>
            <CypherBlock title="All retrieved chunks" cypher={turn.cypher_full} />
            <CypherBlock title="Largest connected cluster" cypher={turn.cypher_largest_cluster} />
          </CollapsibleSection>

          <h2>Graph snapshot</h2>
          <p className="muted">Shows the largest connected cluster only - see the connectivity breakdown above for islands.</p>
          {graph && <GraphCanvas graph={graph} />}
        </>
      )}
    </div>
  );
}

function CollapsibleSection({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="collapsible">
      <button type="button" className="collapsible__toggle" onClick={() => setOpen((prev) => !prev)}>
        <span className="collapsible__caret">{open ? "▾" : "▸"}</span>
        {title}
      </button>
      {open && <div className="collapsible__content">{children}</div>}
    </div>
  );
}

function ConnectivityCallout({ connectivity }: { connectivity: RetrievalTraceTurnResponse["connectivity"] }) {
  if (connectivity.cluster_count <= 1) {
    return <p className="success">All retrieved chunks form a single connected graph.</p>;
  }
  return (
    <div className="warning">
      <p>
        Retrieved chunks split into {connectivity.cluster_count} disconnected clusters - the graph traversal
        below only shows the largest one.
      </p>
      <ul>
        {connectivity.clusters.map((cluster, index) => (
          <li key={index}>
            {cluster.chunk_count} chunk(s) from {cluster.document_names.join(", ")}
          </li>
        ))}
      </ul>
    </div>
  );
}

function CypherBlock({ title, cypher }: { title: string; cypher: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard
      .writeText(cypher)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      })
      .catch(() => setCopied(false));
  }

  return (
    <div className="cypher-block">
      <div className="cypher-block__header">
        <span>{title}</span>
        <button type="button" className="cypher-block__copy" onClick={handleCopy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="cypher-block__pre">{cypher}</pre>
    </div>
  );
}

function truncateName(name: string, max: number): string {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name;
}

function GraphCanvas({ graph }: { graph: RetrievalTraceGraphResponse }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);

  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setWidth(entry.contentRect.width);
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  if (graph.nodes.length === 0) {
    return <EmptyState>No graph data for this turn.</EmptyState>;
  }

  return (
    <>
      <GraphLegend />
      <div className="graph-canvas" ref={containerRef}>
        <ForceGraph2D
          graphData={{
            nodes: graph.nodes.map((node) => ({ ...node })),
            links: graph.edges.map((edge) => ({ ...edge })),
          }}
          width={width}
          height={460}
          nodeId="id"
          nodeLabel={(node) => `${node.label}: ${node.name}`}
          nodeColor={(node) => NODE_COLORS[node.label as string] ?? "#9aa7bd"}
          nodeVal={(node) => NODE_RADIUS[node.label as string] ?? 3}
          nodeCanvasObjectMode={() => "after"}
          nodeCanvasObject={(node: any, ctx, globalScale) => {
            const radius = NODE_RADIUS[node.label as string] ?? 3;
            const fontSize = Math.max(4, 5 / globalScale);
            ctx.font = `${fontSize}px sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillStyle = "#1a2634";
            ctx.fillText(truncateName(node.name ?? "", 20), node.x, node.y + radius + 2);
          }}
          linkLabel={(link) => link.type as string}
          linkColor={() => EDGE_COLOR}
          linkWidth={1}
          linkDirectionalArrowLength={4}
          linkDirectionalArrowRelPos={1}
        />
      </div>
    </>
  );
}

function GraphLegend() {
  return (
    <div className="graph-legend">
      <div className="graph-legend__group">
        <span className="graph-legend__title">Nodes</span>
        {Object.entries(NODE_COLORS).map(([label, color]) => (
          <span className="graph-legend__item" key={label}>
            <span className="graph-legend__swatch" style={{ background: color }} />
            {label}
          </span>
        ))}
      </div>
      <div className="graph-legend__group">
        <span className="graph-legend__title">Relationships</span>
        <span className="graph-legend__item">
          <span className="graph-legend__line" style={{ background: EDGE_COLOR }} />
          HAS_CHUNK / MENTIONS / RELATED / LEADS_TO (hover an edge for its type)
        </span>
      </div>
    </div>
  );
}
