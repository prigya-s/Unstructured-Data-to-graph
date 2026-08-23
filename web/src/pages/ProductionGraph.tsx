import { useEffect, useState } from "react";

import { GraphPayload, getProductionGraph } from "../api/client";
import EmptyState from "../components/EmptyState";
import MetricTile from "../components/MetricTile";
import RelationshipTable from "../components/RelationshipTable";

export default function ProductionGraph() {
  const [data, setData] = useState<GraphPayload | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProductionGraph()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <div className="page">
      <h1>Production Graph</h1>
      <p className="muted">
        Approved-only - this is the Gold-layer graph that is (or will be) live in Neo4j. Candidate
        entities and relationships that are still pending review never appear here.
      </p>

      {error && <p className="error">{error}</p>}
      {data === undefined && !error && <p className="muted">Loading...</p>}

      {data === null && (
        <EmptyState>
          No Production Graph has been published yet. Approve entities on the Entity Review page,
          then use the Publish page to generate and load it.
        </EmptyState>
      )}

      {data && (
        <>
          <div className="metric-grid">
            <MetricTile label="Approved entities" value={data.stats.entities} />
            <MetricTile label="Approved relationships" value={data.stats.entity_relationships} />
          </div>

          <h2>Entities</h2>
          {data.nodes.entities.length === 0 ? (
            <EmptyState>No approved entities yet.</EmptyState>
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
            <EmptyState>No approved relationships yet.</EmptyState>
          ) : (
            <RelationshipTable graph={data} />
          )}
        </>
      )}
    </div>
  );
}
