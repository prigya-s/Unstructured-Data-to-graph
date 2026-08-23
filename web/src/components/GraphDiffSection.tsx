import { useEffect, useState } from "react";

import { GraphDiffResponse, getGraphDiff } from "../api/client";
import EmptyState from "./EmptyState";
import MetricTile from "./MetricTile";

// Moved out of the former standalone GraphDiff.tsx page: Candidate Graph now
// renders this as extra sections instead of via separate /graph-impact and
// /graph-diff nav items, per the 2026-08-20 nav consolidation. Both "Graph
// Impact Analysis" and "Graph Difference View" already rendered from this
// one compute_graph_diff() payload, so nothing about the fetch changes.
export default function GraphDiffSection() {
  const [data, setData] = useState<GraphDiffResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getGraphDiff()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading...</p>;

  return (
    <>
      <hr className="section-divider" />
      <h2>Graph Impact Analysis</h2>
      <p className="muted">
        What changes in the Production Graph if every entity and relationship currently pending
        review were approved.
      </p>

      <div className="metric-grid">
        <MetricTile label="New entities" value={`+${data.counts.new_entities}`} />
        <MetricTile label="New relationships" value={`+${data.counts.new_relationships}`} />
        <MetricTile label="Entities merged" value={data.counts.entities_merged} />
        <MetricTile label="Entities/relationships removed" value={data.counts.removed_total} />
        <MetricTile label="Net entity count change" value={data.counts.entity_count_delta} />
        <MetricTile label="Net relationship count change" value={data.counts.relationship_count_delta} />
      </div>

      <hr className="section-divider" />
      <h2>Graph Difference View</h2>
      <p className="muted">
        Current Production Graph to proposed graph if all pending entities and relationships were
        approved.
      </p>

      <h3>Added entities</h3>
      {data.entities_added.length === 0 ? (
        <EmptyState>No new entities.</EmptyState>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
            </tr>
          </thead>
          <tbody>
            {data.entities_added.map((entity, index) => (
              <tr key={index}>
                <td>{entity.name}</td>
                <td>{entity.type}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Removed entities</h3>
      {data.entities_removed.length === 0 ? (
        <EmptyState>No removed entities.</EmptyState>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
            </tr>
          </thead>
          <tbody>
            {data.entities_removed.map((entity, index) => (
              <tr key={index}>
                <td>{entity.name}</td>
                <td>{entity.type}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Modified entities</h3>
      {data.entities_modified.length === 0 ? (
        <EmptyState>No modified entities.</EmptyState>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Previous name</th>
              <th>Type</th>
              <th>Previous type</th>
            </tr>
          </thead>
          <tbody>
            {data.entities_modified.map((entity, index) => (
              <tr key={index}>
                <td>{entity.name}</td>
                <td>{entity.previous_name}</td>
                <td>{entity.type}</td>
                <td>{entity.previous_type}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Merged entities</h3>
      {data.entities_merged.length === 0 ? (
        <EmptyState>No entities merged since the last publish.</EmptyState>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Merged into</th>
            </tr>
          </thead>
          <tbody>
            {data.entities_merged.map((entity, index) => (
              <tr key={index}>
                <td>{entity.name}</td>
                <td>{entity.merged_into_name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Added relationships</h3>
      {data.relationships_added.length === 0 ? (
        <EmptyState>No new relationships.</EmptyState>
      ) : (
        <RelDiffTable rows={data.relationships_added} />
      )}

      <h3>Removed relationships</h3>
      {data.relationships_removed.length === 0 ? (
        <EmptyState>No removed relationships.</EmptyState>
      ) : (
        <RelDiffTable rows={data.relationships_removed} />
      )}
    </>
  );
}

function RelDiffTable({ rows }: { rows: { source: string; relationship: string; target: string }[] }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Source</th>
          <th>Relationship</th>
          <th>Target</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((rel, index) => (
          <tr key={index}>
            <td>{rel.source}</td>
            <td>{rel.relationship}</td>
            <td>{rel.target}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
