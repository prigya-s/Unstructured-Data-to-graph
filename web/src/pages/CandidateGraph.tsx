import { useCallback, useEffect, useState } from "react";

import { GraphPayload, getCandidateGraph } from "../api/client";
import EmptyState from "../components/EmptyState";
import GraphDiffSection from "../components/GraphDiffSection";
import MetricTile from "../components/MetricTile";
import RelationshipTable from "../components/RelationshipTable";

export default function CandidateGraph() {
  const [data, setData] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    getCandidateGraph()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="page">
      <div className="page__header">
        <h1>Candidate Graph</h1>
        <button type="button" onClick={load} disabled={loading}>
          Refresh
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {!data && !error && <p className="muted">Loading...</p>}

      {data && (
        <>
          <div className="metric-grid">
            <MetricTile label="Entities" value={data.stats.entities} />
            <MetricTile label="Relationships" value={data.stats.entity_relationships} />
          </div>

          <h2>Entities</h2>
          {data.nodes.entities.length === 0 ? (
            <EmptyState>No candidate entities extracted yet.</EmptyState>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {data.nodes.entities.map((entity) => (
                  <tr key={entity.id}>
                    <td>{entity.name}</td>
                    <td>{entity.type}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2>Relationships</h2>
          {data.relationships.entity_relationships.length === 0 ? (
            <EmptyState>No candidate relationships extracted yet.</EmptyState>
          ) : (
            <RelationshipTable graph={data} />
          )}

          <GraphDiffSection />
        </>
      )}
    </div>
  );
}
